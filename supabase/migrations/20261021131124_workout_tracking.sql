-- Workout tracking (M6 part 2): core lifts, 6-week blocks, plan changes
-- (days off, vacation, medical pause, cheat meal, …), and keeping what was
-- done when a plan is replaced mid-week.
-- Spec: context/pages/workout-plan.md, context/pages/plan-for-today.md.

-- Core lifts: always in the plan and never rotated, so their loads can keep
-- going up. Ids from the exercise library (checked by the API).
alter table public.training_preferences
  add column core_exercises text[] not null default '{}'
    check (cardinality(core_exercises) <= 8);
grant update (core_exercises) on public.training_preferences to authenticated;

-- Non-core main exercises stay the same for a 6-week block, then change.
alter table public.workout_plans add column block_start date
  check (block_start is null or extract(isodow from block_start) = 1);

-- ---------------------------------------------------------------------------
-- Plan changes
-- ---------------------------------------------------------------------------

-- A change to the plan, asked for on the Workout Plan page and shown as a
-- preview (draft) before it's applied. Applied changes keep shaping later plans
-- (e.g. a vacation next week, a medical pause until "I'm back").
create table public.plan_changes (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  kind text not null check (kind in (
    'day_off', 'add_session', 'shorter', 'vacation', 'cheat_meal', 'medical', 'other'
  )),
  start_date date not null,
  -- Empty for a medical pause until "I'm back" (then set to that day).
  end_date date,
  -- 'shorter': minutes that day.
  minutes integer check (minutes between 10 and 300),
  -- 'vacation': 'rest' (no training) or 'travel' (short bodyweight/band sessions).
  vacation_mode text check (vacation_mode in ('rest', 'travel')),
  -- 'cheat_meal': 'spread' (a little more cardio across the week) or 'as_planned'.
  cheat_mode text check (cheat_mode in ('spread', 'as_planned')),
  -- What the person wrote (required for 'other').
  note text check (char_length(note) <= 500),
  -- 'other': the LLM's reading of the note: days_off, shorter, avoid_muscles, easier.
  details jsonb,
  status text not null default 'pending' check (status in ('pending', 'applied', 'discarded')),
  -- The preview made for it.
  draft_plan_id uuid references public.workout_plans (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date is null or end_date >= start_date),
  check (kind <> 'other' or note is not null)
);

create index plan_changes_profile_dates_idx on public.plan_changes (profile_id, start_date);

create trigger set_updated_at before update on public.plan_changes
  for each row execute function private.set_updated_at();

alter table public.plan_changes enable row level security;
revoke all on public.plan_changes from anon, authenticated;
grant select on public.plan_changes to authenticated;
grant insert (profile_id, kind, start_date, end_date, minutes, vacation_mode, cheat_mode, note,
  details, draft_plan_id),
  update (end_date, status, details, draft_plan_id), delete
  on public.plan_changes to authenticated;

create policy "Read household plan changes"
  on public.plan_changes for select to authenticated
  using ((select private.in_my_household(profile_id)));
create policy "Ask for own plan changes"
  on public.plan_changes for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
create policy "Update own plan changes"
  on public.plan_changes for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));
create policy "Remove own plan changes"
  on public.plan_changes for delete to authenticated
  using (profile_id = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- Saving and applying plans (replaces the M6 part 1 versions)
-- ---------------------------------------------------------------------------

-- As before, plus the block start ("block_start" in p_plan).
create or replace function public.save_workout_plan(
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
    delete from public.workout_plans
    where profile_id = p_profile_id and week_start = p_week_start and status = 'draft';
  end if;

  insert into public.workout_plans (
    profile_id, week_start, status, rationale, made_by, reason, block_start
  )
  values (
    p_profile_id, p_week_start, p_status, p_plan ->> 'rationale', p_plan ->> 'made_by',
    p_plan ->> 'reason', (p_plan ->> 'block_start')::date
  )
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

  if p_status = 'active' then
    perform private.move_progress(p_profile_id, p_week_start, new_plan_id);
  end if;
  return new_plan_id;
end;
$$;

-- When a plan replaces another for the same week, what was already done moves
-- with it: completions follow the session on the same day, and logged sets the
-- item with the same day, phase, position and exercise.
create function private.move_progress(p_profile_id uuid, p_week_start date, p_new_plan_id uuid)
returns void
language sql
security definer
set search_path = ''
as $$
  update public.session_completions c
  set session_id = ns.id
  from public.workout_sessions os
  join public.workout_plans op on op.id = os.plan_id
  join public.workout_sessions ns on ns.plan_id = p_new_plan_id and ns.day = os.day
  where c.session_id = os.id
    and op.profile_id = p_profile_id
    and op.week_start = p_week_start
    and op.id <> p_new_plan_id;

  update public.exercise_logs l
  set session_item_id = ni.id
  from public.session_items oi
  join public.workout_sessions os on os.id = oi.session_id
  join public.workout_plans op on op.id = os.plan_id
  join public.workout_sessions ns on ns.plan_id = p_new_plan_id and ns.day = os.day
  join public.session_items ni on ni.session_id = ns.id
    and ni.phase = oi.phase and ni.position = oi.position and ni.exercise_id = oi.exercise_id
  where l.session_item_id = oi.id
    and op.profile_id = p_profile_id
    and op.week_start = p_week_start
    and op.id <> p_new_plan_id;
$$;

revoke execute on function private.move_progress(uuid, date, uuid) from public;

create or replace function public.apply_workout_plan(p_plan_id uuid)
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
  perform private.move_progress(draft.profile_id, draft.week_start, draft.id);
  -- The change this preview was made for is now in effect.
  update public.plan_changes set status = 'applied'
  where draft_plan_id = draft.id and status = 'pending';
end;
$$;
