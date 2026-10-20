-- Health data intake (M3): measurements, Apple Health connection tokens,
-- water logs and the per-person water target.
-- Spec: context/data-model.md ("Health data", "Nutrition"), context/apple-health-shortcut.md.

-- ---------------------------------------------------------------------------
-- Measurements
-- ---------------------------------------------------------------------------

-- One value per metric, per day, per source. Re-sending a day replaces it, so
-- the iOS Shortcut can safely send the same data more than once.
create table public.health_samples (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  metric text not null check (metric in (
    'steps', 'active_energy_kcal', 'walking_running_km',
    'sleep_in_bed_minutes', 'sleep_asleep_minutes', 'bedtime', 'wake_time',
    'weight_kg', 'resting_hr', 'hrv_ms', 'vo2_max'
  )),
  -- The local day the value belongs to (for sleep: the morning you woke up).
  recorded_on date not null,
  -- The number; empty only for bedtime / wake time, which use recorded_at.
  value numeric check (value is null or value >= 0),
  -- Exact time, when it matters (bedtime, wake time, a weigh-in).
  recorded_at timestamptz,
  source text not null default 'apple_health' check (source in ('apple_health', 'manual')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, metric, recorded_on, source),
  check (value is not null or (metric in ('bedtime', 'wake_time') and recorded_at is not null))
);

create index health_samples_profile_metric_day_idx
  on public.health_samples (profile_id, metric, recorded_on desc);

-- ---------------------------------------------------------------------------
-- Apple Health connection tokens
-- ---------------------------------------------------------------------------

-- The iOS Shortcut sends a token instead of a password. Only a SHA-256 hash is
-- stored; the token itself is shown once, when it's created.
create table public.ingest_tokens (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null unique references public.profiles (id) on delete cascade,
  token_hash text not null unique check (char_length(token_hash) = 64),
  last_used_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Water
-- ---------------------------------------------------------------------------

create table public.water_logs (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  ml integer not null check (ml between 1 and 2000),
  -- The person's local date when they logged it.
  logged_on date not null,
  logged_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index water_logs_profile_day_idx on public.water_logs (profile_id, logged_on);

alter table public.profiles
  add column water_target_ml integer not null default 3000
    check (water_target_ml between 500 and 8000);
grant update (water_target_ml) on public.profiles to authenticated;

create trigger set_updated_at before update on public.health_samples
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.ingest_tokens
  for each row execute function private.set_updated_at();
create trigger set_updated_at before update on public.water_logs
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- Access rules: "view both, change your own"
-- ---------------------------------------------------------------------------

alter table public.health_samples enable row level security;
alter table public.ingest_tokens enable row level security;
alter table public.water_logs enable row level security;

revoke all on public.health_samples, public.ingest_tokens, public.water_logs from anon, authenticated;

-- Measurements: read the household's; add or correct your own (manual weigh-ins).
grant select on public.health_samples to authenticated;
grant insert (profile_id, metric, recorded_on, value, recorded_at, source)
  on public.health_samples to authenticated;
grant update (value, recorded_at) on public.health_samples to authenticated;

create policy "Read household health samples"
  on public.health_samples for select to authenticated
  using ((select private.in_my_household(profile_id)));
create policy "Add own health samples"
  on public.health_samples for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
create policy "Correct own health samples"
  on public.health_samples for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));

-- Tokens: private even within the household; create and revoke your own.
grant select (id, profile_id, last_used_at, created_at) on public.ingest_tokens to authenticated;
grant insert (profile_id, token_hash), delete on public.ingest_tokens to authenticated;

create policy "Read own token"
  on public.ingest_tokens for select to authenticated
  using (profile_id = (select private.my_profile_id()));
create policy "Create own token"
  on public.ingest_tokens for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
create policy "Revoke own token"
  on public.ingest_tokens for delete to authenticated
  using (profile_id = (select private.my_profile_id()));

-- Water: read the household's; add and undo your own.
grant select on public.water_logs to authenticated;
grant insert (profile_id, ml, logged_on), delete on public.water_logs to authenticated;

create policy "Read household water"
  on public.water_logs for select to authenticated
  using ((select private.in_my_household(profile_id)));
create policy "Log own water"
  on public.water_logs for insert to authenticated
  with check (profile_id = (select private.my_profile_id()));
create policy "Undo own water"
  on public.water_logs for delete to authenticated
  using (profile_id = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- Receiving data from the iOS Shortcut
-- ---------------------------------------------------------------------------

-- Called by the API with no signed-in user: the connection token identifies the
-- person. Runs with owner rights so the API needs no secret key, but it can
-- only add measurements for the token's own profile.
create function public.ingest_health_samples(token text, samples jsonb)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_profile_id uuid;
  sample jsonb;
  saved integer := 0;
begin
  select profile_id into target_profile_id
  from public.ingest_tokens
  where token_hash = encode(extensions.digest(convert_to(token, 'UTF8'), 'sha256'), 'hex');

  if target_profile_id is null then
    raise exception 'Invalid connection token' using errcode = '28000';
  end if;
  if jsonb_typeof(samples) <> 'array' or jsonb_array_length(samples) > 500 then
    raise exception 'samples must be a list of at most 500 items' using errcode = '22023';
  end if;

  for sample in select * from jsonb_array_elements(samples) loop
    insert into public.health_samples (profile_id, metric, recorded_on, value, recorded_at, source)
    values (
      target_profile_id,
      sample ->> 'metric',
      (sample ->> 'date')::date,
      (sample ->> 'value')::numeric,
      (sample ->> 'at')::timestamptz,
      'apple_health'
    )
    on conflict (profile_id, metric, recorded_on, source) do update
      set value = excluded.value, recorded_at = excluded.recorded_at;
    saved := saved + 1;
  end loop;

  update public.ingest_tokens set last_used_at = now() where profile_id = target_profile_id;
  return saved;
end;
$$;

revoke execute on function public.ingest_health_samples(text, jsonb) from public;
grant execute on function public.ingest_health_samples(text, jsonb) to anon, authenticated;
