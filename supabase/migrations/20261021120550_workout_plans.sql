-- Workout plans (M6): weekly plans with five-phase sessions, what was actually
-- lifted, and session completions. Plus training experience in Settings.
-- Spec: context/pages/workout-plan.md, context/pages/plan-for-today.md,
-- context/data-model.md ("Workouts").

alter table public.training_preferences
  add column experience text check (experience in ('beginner', 'intermediate', 'advanced'));
grant update (experience) on public.training_preferences to authenticated;

-- ---------------------------------------------------------------------------
-- Plans, sessions and items
-- ---------------------------------------------------------------------------

-- One active plan per person per week (Monday to Sunday). A draft is a new plan
-- being previewed; applying it supersedes the active one.
create table public.workout_plans (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  -- The Monday the week starts on.
  week_start date not null check (extract(isodow from week_start) = 1),
  status text not null check (status in ('draft', 'active', 'superseded')),
  -- Why the week looks like this (written by the LLM, or a fixed note).
  rationale text check (char_length(rationale) <= 2000),
  -- e.g. 'groq:qwen/qwen3.8-27b', 'ollama:qwen3:8b' or 'rules' (no LLM answered).
  made_by text,
  -- Why it was made: 'new_week', 'requested', 'change'.
  reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index workout_plans_one_active_per_week
  on public.workout_plans (profile_id, week_start) where status = 'active';
create index workout_plans_profile_week_idx on public.workout_plans (profile_id, week_start desc);

create table public.workout_sessions (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.workout_plans (id) on delete cascade,
  -- Copied from the plan so the access rules stay simple.
  profile_id uuid not null references public.profiles (id) on delete cascade,
  day date not null,
  title text not null check (char_length(title) between 1 and 100),
  -- e.g. 'full_body', 'upper', 'lower', 'push', 'pull', 'legs'.
  focus text not null,
  minutes integer not null check (minutes between 5 and 300),
  explanation text check (char_length(explanation) <= 1000),
  unique (plan_id, day)
);

create table public.session_items (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.workout_sessions (id) on delete cascade,
  profile_id uuid not null references public.profiles (id) on delete cascade,
  phase text not null check (phase in ('cardio', 'mobility', 'activation', 'main', 'cooldown')),
  position integer not null check (position >= 0),
  exercise_id text not null references public.exercises (id),
  sets integer check (sets between 1 and 10),
  reps_min integer check (reps_min between 1 and 100),
  reps_max integer check (reps_max between 1 and 100),
  -- For timed work (cardio, holds, stretches).
  duration_seconds integer check (duration_seconds between 5 and 3600),
  rest_seconds integer check (rest_seconds between 0 and 600),
  target_load_kg numeric check (target_load_kg between 0 and 500),
  notes text check (char_length(notes) <= 300),
  unique (session_id, phase, position),
  check (reps_min is null or reps_max is null or reps_min <= reps_max)
);

create index session_items_session_idx on public.session_items (session_id);

-- ---------------------------------------------------------------------------
-- What was done (logged on Plan for Today; used in part 2)
-- ---------------------------------------------------------------------------

create table public.exercise_logs (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  session_item_id uuid not null references public.session_items (id) on delete cascade,
  -- Kept so history survives a plan being replaced.
  exercise_id text not null references public.exercises (id),
  set_number integer not null check (set_number between 1 and 20),
  reps integer check (reps between 0 and 200),
  load_kg numeric check (load_kg between 0 and 500),
  duration_seconds integer check (duration_seconds between 0 and 7200),
  logged_at timestamptz not null default now(),
  unique (session_item_id, set_number)
);

create index exercise_logs_profile_exercise_idx
  on public.exercise_logs (profile_id, exercise_id, logged_at desc);

create table public.session_completions (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  session_id uuid not null unique references public.workout_sessions (id) on delete cascade,
  -- The local day it was done.
  done_on date not null,
  effort text check (effort in ('easy', 'right', 'too_hard')),
  completed_at timestamptz not null default now()
);

create index session_completions_profile_idx on public.session_completions (profile_id, done_on desc);

create trigger set_updated_at before update on public.workout_plans
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- Access rules: "view both, change your own"
-- ---------------------------------------------------------------------------

alter table public.workout_plans enable row level security;
alter table public.workout_sessions enable row level security;
alter table public.session_items enable row level security;
alter table public.exercise_logs enable row level security;
alter table public.session_completions enable row level security;

revoke all on public.workout_plans, public.workout_sessions, public.session_items,
  public.exercise_logs, public.session_completions from anon, authenticated;

grant select on public.workout_plans, public.workout_sessions, public.session_items,
  public.exercise_logs, public.session_completions to authenticated;

-- Plans are written through public.save_workout_plan (below); afterwards a
-- person can apply or discard their draft and swap exercises.
grant update (status) on public.workout_plans to authenticated;
grant delete on public.workout_plans to authenticated;
grant update (exercise_id, notes) on public.session_items to authenticated;
grant insert (profile_id, session_item_id, exercise_id, set_number, reps, load_kg, duration_seconds),
  update (reps, load_kg, duration_seconds), delete on public.exercise_logs to authenticated;
grant insert (profile_id, session_id, done_on, effort), update (effort), delete
  on public.session_completions to authenticated;

do $$
declare
  t text;
begin
  foreach t in array array['workout_plans', 'workout_sessions', 'session_items',
                           'exercise_logs', 'session_completions'] loop
    execute format(
      'create policy "Read household %1$s" on public.%1$I for select to authenticated
         using ((select private.in_my_household(profile_id)))', t);
  end loop;
end;
$$;

create policy "Apply or discard own plan"
  on public.workout_plans for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));
create policy "Delete own draft plan"
  on public.workout_plans for delete to authenticated
  using (profile_id = (select private.my_profile_id()) and status = 'draft');
create policy "Swap own exercises"
  on public.session_items for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

create policy "Log own sets"
  on public.exercise_logs for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
create policy "Correct own sets"
  on public.exercise_logs for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));
create policy "Remove own sets"
  on public.exercise_logs for delete to authenticated
  using (profile_id = (select private.my_profile_id()));

create policy "Complete own sessions"
  on public.session_completions for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
create policy "Rate own sessions"
  on public.session_completions for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));
create policy "Undo own completions"
  on public.session_completions for delete to authenticated
  using (profile_id = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- Saving a whole plan at once
-- ---------------------------------------------------------------------------

-- Saves a plan with its sessions and items in one go (all or nothing).
-- Signed-in callers may only save their own plan; the worker (secret key) saves
-- for whoever the job is for. With status 'active', any other active plan for
-- that week becomes 'superseded'.
--
-- p_plan: {"rationale", "made_by", "reason", "sessions": [{"day", "title", "focus",
--   "minutes", "explanation", "items": [{"phase", "position", "exercise_id", "sets",
--   "reps_min", "reps_max", "duration_seconds", "rest_seconds", "target_load_kg", "notes"}]}]}
create function public.save_workout_plan(
  p_profile_id uuid, p_week_start date, p_status text, p_plan jsonb
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_plan_id uuid;
  new_session_id uuid;
  s jsonb;
  i jsonb;
begin
  if auth.role() <> 'service_role' and p_profile_id is distinct from private.my_profile_id() then
    raise exception 'You can only save your own plan' using errcode = '42501';
  end if;
  if p_status not in ('draft', 'active') then
    raise exception 'status must be draft or active' using errcode = '22023';
  end if;

  if p_status = 'active' then
    update public.workout_plans set status = 'superseded'
    where profile_id = p_profile_id and week_start = p_week_start and status = 'active';
  else
    -- Only one draft at a time: a new one replaces the old.
    delete from public.workout_plans
    where profile_id = p_profile_id and week_start = p_week_start and status = 'draft';
  end if;

  insert into public.workout_plans (profile_id, week_start, status, rationale, made_by, reason)
  values (p_profile_id, p_week_start, p_status, p_plan ->> 'rationale', p_plan ->> 'made_by',
          p_plan ->> 'reason')
  returning id into new_plan_id;

  for s in select * from jsonb_array_elements(coalesce(p_plan -> 'sessions', '[]')) loop
    insert into public.workout_sessions (plan_id, profile_id, day, title, focus, minutes, explanation)
    values (new_plan_id, p_profile_id, (s ->> 'day')::date, s ->> 'title', s ->> 'focus',
            (s ->> 'minutes')::integer, s ->> 'explanation')
    returning id into new_session_id;

    for i in select * from jsonb_array_elements(coalesce(s -> 'items', '[]')) loop
      insert into public.session_items (
        session_id, profile_id, phase, position, exercise_id, sets, reps_min, reps_max,
        duration_seconds, rest_seconds, target_load_kg, notes
      )
      values (
        new_session_id, p_profile_id, i ->> 'phase', (i ->> 'position')::integer,
        i ->> 'exercise_id', (i ->> 'sets')::integer, (i ->> 'reps_min')::integer,
        (i ->> 'reps_max')::integer, (i ->> 'duration_seconds')::integer,
        (i ->> 'rest_seconds')::integer, (i ->> 'target_load_kg')::numeric, i ->> 'notes'
      );
    end loop;
  end loop;

  return new_plan_id;
end;
$$;

-- Applying a draft: it becomes active and the old active plan is superseded.
create function public.apply_workout_plan(p_plan_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  draft public.workout_plans;
begin
  select * into draft from public.workout_plans
  where id = p_plan_id and status = 'draft' and profile_id = private.my_profile_id();
  if draft.id is null then
    raise exception 'No draft plan of yours with that id' using errcode = 'P0002';
  end if;
  update public.workout_plans set status = 'superseded'
  where profile_id = draft.profile_id and week_start = draft.week_start and status = 'active';
  update public.workout_plans set status = 'active' where id = draft.id;
end;
$$;

revoke execute on function public.save_workout_plan(uuid, date, text, jsonb) from public, anon;
revoke execute on function public.apply_workout_plan(uuid) from public, anon;
grant execute on function public.save_workout_plan(uuid, date, text, jsonb) to authenticated, service_role;
grant execute on function public.apply_workout_plan(uuid) to authenticated;
