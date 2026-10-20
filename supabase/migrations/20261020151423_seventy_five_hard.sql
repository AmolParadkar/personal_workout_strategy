-- 75 Hard: challenge starts and daily checklist ticks.
-- Spec: context/pages/75-hard.md, context/data-model.md ("75 Hard").
--
-- The current day, resets and completion are calculated from these rows by the
-- API (backend/core/seventy_five_hard.py); nothing runs at midnight.

create table public.challenges (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  -- Date the person started tracking, and which day of 75 that date was.
  started_on date not null,
  start_day integer not null check (start_day between 1 and 75),
  -- Browser timezone at start (e.g. Asia/Kolkata): decides when midnight and noon are.
  timezone text not null check (char_length(timezone) between 1 and 64),
  -- Set when the person stops the challenge. A completed or reset challenge
  -- stays running: completion and resets are calculated, not stored.
  stopped_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- At most one challenge running per person.
create unique index challenges_one_running_per_profile
  on public.challenges (profile_id) where stopped_at is null;

create table public.challenge_checks (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  date date not null,
  item text not null check (item in ('diet', 'workout_1', 'workout_2_outdoor', 'water',
                                     'reading', 'photo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, date, item)
);

create trigger set_updated_at before update on public.challenges
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.challenge_checks
  for each row execute function private.set_updated_at();

-- Access rules: "view both, change your own".
alter table public.challenges enable row level security;
alter table public.challenge_checks enable row level security;

revoke all on public.challenges, public.challenge_checks from anon, authenticated;
grant select on public.challenges, public.challenge_checks to authenticated;
-- Starting a challenge, stopping it, and ticking / unticking items.
grant insert (profile_id, started_on, start_day, timezone) on public.challenges to authenticated;
grant update (stopped_at) on public.challenges to authenticated;
grant insert (profile_id, date, item), delete on public.challenge_checks to authenticated;

create policy "Read household challenges"
  on public.challenges for select to authenticated
  using ((select private.in_my_household(profile_id)));

create policy "Start own challenge"
  on public.challenges for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));

create policy "Stop own challenge"
  on public.challenges for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

create policy "Read household challenge checks"
  on public.challenge_checks for select to authenticated
  using ((select private.in_my_household(profile_id)));

create policy "Tick own items"
  on public.challenge_checks for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));

create policy "Untick own items"
  on public.challenge_checks for delete to authenticated
  using (profile_id = (select private.my_profile_id()));
