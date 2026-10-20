-- Profiles and settings: households, profiles, preferences and display settings.
-- Spec: context/data-model.md ("Profiles and settings", "Access rules").
--
-- Access rule ("view both, change your own"):
--   * read:  every row belonging to a profile in your household
--   * write: only rows belonging to your own profile
-- Rows are created by the new-user trigger, never by the website directly.

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- Functions used by access rules live in a schema the API doesn't expose,
-- so they can't be called directly from the website.
create schema if not exists private;

create function private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.households (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users (id) on delete cascade,
  household_id uuid not null references public.households (id),
  display_name text not null check (char_length(display_name) between 1 and 50),
  date_of_birth date,
  sex text check (sex in ('female', 'male', 'other')),
  height_cm numeric(5, 1) check (height_cm between 50 and 260),
  goals text,
  -- The one metric the person cares about most (e.g. weight, vo2_max, hrv).
  goal_metric text,
  injuries_notes text,
  -- Empty until the first-sign-in questions are answered.
  onboarded_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index profiles_household_id_idx on public.profiles (household_id);

create table public.training_preferences (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null unique references public.profiles (id) on delete cascade,
  equipment text[] not null default '{}',
  available_days text[] not null default '{}'
    check (available_days <@ array['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']),
  minutes_per_session integer check (minutes_per_session between 5 and 300),
  location text check (location in ('home', 'gym', 'travel')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.diet_preferences (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null unique references public.profiles (id) on delete cascade,
  diet_type text check (diet_type in ('vegetarian', 'eggetarian', 'non_vegetarian')),
  cuisines text[] not null default '{}',
  allergies text[] not null default '{}',
  dislikes text[] not null default '{}',
  meals_per_day integer check (meals_per_day between 1 and 8),
  cooking_minutes integer check (cooking_minutes between 0 and 240),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Opt-in Summary / Progress cards. Off by default (disordered-eating safeguard).
create table public.display_settings (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null unique references public.profiles (id) on delete cascade,
  show_weight boolean not null default false,
  show_calorie_intake boolean not null default false,
  show_calories_burned boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger set_updated_at before update on public.households
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.profiles
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.training_preferences
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.diet_preferences
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.display_settings
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- Access-rule helpers
-- ---------------------------------------------------------------------------

-- "security definer" lets these read profiles without triggering the
-- profiles access rules again (which would loop).

create function private.my_profile_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select id from public.profiles where user_id = (select auth.uid());
$$;

create function private.my_household_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select household_id from public.profiles where user_id = (select auth.uid());
$$;

create function private.in_my_household(target_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.profiles
    where id = target_profile_id
      and household_id = (
        select household_id from public.profiles where user_id = (select auth.uid())
      )
  );
$$;

grant usage on schema private to authenticated;
revoke execute on all functions in schema private from public, anon;
grant execute on function private.my_profile_id() to authenticated;
grant execute on function private.my_household_id() to authenticated;
grant execute on function private.in_my_household(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Access rules
-- ---------------------------------------------------------------------------

alter table public.households enable row level security;
alter table public.profiles enable row level security;
alter table public.training_preferences enable row level security;
alter table public.diet_preferences enable row level security;
alter table public.display_settings enable row level security;

-- Signed-out visitors get nothing at all.
revoke all on public.households, public.profiles, public.training_preferences,
  public.diet_preferences, public.display_settings from anon;

-- Signed-in users can only read, and update the columns listed below.
-- No inserts or deletes: rows are created by the new-user trigger.
revoke all on public.households, public.profiles, public.training_preferences,
  public.diet_preferences, public.display_settings from authenticated;
grant select on public.households, public.profiles, public.training_preferences,
  public.diet_preferences, public.display_settings to authenticated;

-- Column lists leave out ids, user_id, household_id and profile_id, so nobody
-- can move a row to another person or household.
grant update (display_name, date_of_birth, sex, height_cm, goals, goal_metric,
  injuries_notes, onboarded_at) on public.profiles to authenticated;
grant update (equipment, available_days, minutes_per_session, location)
  on public.training_preferences to authenticated;
grant update (diet_type, cuisines, allergies, dislikes, meals_per_day, cooking_minutes)
  on public.diet_preferences to authenticated;
grant update (show_weight, show_calorie_intake, show_calories_burned)
  on public.display_settings to authenticated;

create policy "Read own household"
  on public.households for select to authenticated
  using (id = (select private.my_household_id()));

create policy "Read profiles in own household"
  on public.profiles for select to authenticated
  using (household_id = (select private.my_household_id()));

create policy "Update own profile"
  on public.profiles for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create policy "Read household training preferences"
  on public.training_preferences for select to authenticated
  using ((select private.in_my_household(profile_id)));

create policy "Update own training preferences"
  on public.training_preferences for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

create policy "Read household diet preferences"
  on public.diet_preferences for select to authenticated
  using ((select private.in_my_household(profile_id)));

create policy "Update own diet preferences"
  on public.diet_preferences for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

create policy "Read household display settings"
  on public.display_settings for select to authenticated
  using ((select private.in_my_household(profile_id)));

create policy "Update own display settings"
  on public.display_settings for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- New-user setup
-- ---------------------------------------------------------------------------

-- Creates the profile, preference and settings rows for a new login and puts
-- it in the household. Public sign-ups are switched off (accounts are only
-- created by invitation), so every account belongs to the one household.
create function private.set_up_user(new_user_id uuid, email text, metadata jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_household_id uuid;
  new_profile_id uuid;
begin
  select id into target_household_id from public.households order by created_at limit 1;
  if target_household_id is null then
    insert into public.households (name) values ('Home') returning id into target_household_id;
  end if;

  insert into public.profiles (user_id, household_id, display_name)
  values (
    new_user_id,
    target_household_id,
    left(coalesce(nullif(metadata ->> 'display_name', ''), split_part(email, '@', 1)), 50)
  )
  returning id into new_profile_id;

  insert into public.training_preferences (profile_id) values (new_profile_id);
  insert into public.diet_preferences (profile_id) values (new_profile_id);
  insert into public.display_settings (profile_id) values (new_profile_id);
end;
$$;

create function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.set_up_user(new.id, new.email, new.raw_user_meta_data);
  return new;
end;
$$;

revoke execute on function private.set_up_user(uuid, text, jsonb) from public, anon, authenticated;
revoke execute on function private.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function private.handle_new_user();

-- Set up anyone who already has a login (e.g. created before this migration).
do $$
declare
  existing record;
begin
  for existing in
    select u.id, u.email, u.raw_user_meta_data
    from auth.users u
    where not exists (select 1 from public.profiles p where p.user_id = u.id)
    order by u.created_at
  loop
    perform private.set_up_user(existing.id, existing.email, existing.raw_user_meta_data);
  end loop;
end;
$$;
