-- Direct connectors (M3b): each person's OAuth connection to Withings, Oura,
-- Whoop and Polar, the new metrics they bring, and more choices in
-- "Apps and devices you use".
-- Spec: context/data-sources.md ("Connectors design"), context/data-model.md.

-- ---------------------------------------------------------------------------
-- More apps and devices to choose from
-- ---------------------------------------------------------------------------

alter table public.profiles drop constraint profiles_data_sources_check;
alter table public.profiles add constraint profiles_data_sources_check
  check (data_sources <@ array[
    'iphone_health', 'apple_watch', 'garmin', 'fitbit', 'samsung_watch',
    'polar', 'suunto', 'coros', 'amazfit',
    'oura', 'whoop',
    'withings', 'other_scale', 'bp_monitor', 'glucose_monitor', 'dexcom',
    'strava', 'nike_run_club', 'myfitnesspal', 'cronometer', 'healthifyme'
  ]);

-- ---------------------------------------------------------------------------
-- New metrics and sources for measurements
-- ---------------------------------------------------------------------------

alter table public.health_samples drop constraint health_samples_metric_check;
alter table public.health_samples add constraint health_samples_metric_check
  check (metric in (
    'steps', 'active_energy_kcal', 'walking_running_km',
    'sleep_in_bed_minutes', 'sleep_asleep_minutes', 'bedtime', 'wake_time',
    'sleep_deep_minutes', 'sleep_rem_minutes', 'sleep_light_minutes', 'sleep_score',
    'weight_kg', 'body_fat_pct', 'muscle_mass_kg',
    'resting_hr', 'hrv_ms', 'vo2_max', 'systolic_mmhg', 'diastolic_mmhg',
    'readiness_score', 'recovery_score', 'strain'
  ));

alter table public.health_samples drop constraint health_samples_source_check;
alter table public.health_samples add constraint health_samples_source_check
  check (source in ('apple_health', 'manual', 'withings', 'oura', 'whoop', 'polar'));

-- ---------------------------------------------------------------------------
-- Connections
-- ---------------------------------------------------------------------------

-- One row per person per connected service. The service's access and refresh
-- keys are stored encrypted by the API (CONNECTOR_ENCRYPTION_KEY, which only
-- the API has) and are never readable through the table: only the status is.
create table public.service_connections (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles (id) on delete cascade,
  service text not null check (service in ('withings', 'oura', 'whoop', 'polar')),
  -- The person's id at the service (some APIs need it).
  external_user_id text,
  access_token_enc text not null,
  refresh_token_enc text,
  expires_at timestamptz,
  scopes text,
  connected_at timestamptz not null default now(),
  last_synced_at timestamptz,
  last_sync_error text check (char_length(last_sync_error) <= 300),
  -- The service refused our keys: the person has to connect again.
  needs_reconnect boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (profile_id, service)
);

create trigger set_updated_at before update on public.service_connections
  for each row execute function private.set_updated_at();

alter table public.service_connections enable row level security;
revoke all on public.service_connections from anon, authenticated;

-- Status: the household can see who is connected to what (view both). The key
-- columns are left out of the grant, so they can't be read even by the owner.
grant select (
  id, profile_id, service, connected_at, last_synced_at, last_sync_error,
  needs_reconnect, created_at, updated_at
) on public.service_connections to authenticated;
grant update (last_synced_at, last_sync_error, needs_reconnect), delete
  on public.service_connections to authenticated;

create policy "Read household connections"
  on public.service_connections for select to authenticated
  using ((select private.in_my_household(profile_id)));
create policy "Update own connection status"
  on public.service_connections for update to authenticated
  using (profile_id = (select private.my_profile_id()))
  with check (profile_id = (select private.my_profile_id()));
create policy "Disconnect own service"
  on public.service_connections for delete to authenticated
  using (profile_id = (select private.my_profile_id()));

-- ---------------------------------------------------------------------------
-- Functions the API calls as the signed-in person
-- ---------------------------------------------------------------------------

-- Save (or replace) the caller's own connection keys, already encrypted.
create function public.save_service_connection(
  p_service text,
  p_external_user_id text,
  p_access_token_enc text,
  p_refresh_token_enc text,
  p_expires_at timestamptz,
  p_scopes text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  me uuid := private.my_profile_id();
begin
  if me is null then
    raise exception 'Not signed in' using errcode = '28000';
  end if;
  insert into public.service_connections (
    profile_id, service, external_user_id, access_token_enc, refresh_token_enc,
    expires_at, scopes
  )
  values (
    me, p_service, p_external_user_id, p_access_token_enc, p_refresh_token_enc,
    p_expires_at, p_scopes
  )
  on conflict (profile_id, service) do update set
    external_user_id = coalesce(excluded.external_user_id, service_connections.external_user_id),
    access_token_enc = excluded.access_token_enc,
    -- Some services don't send a new refresh key every time: keep the old one.
    refresh_token_enc = coalesce(excluded.refresh_token_enc, service_connections.refresh_token_enc),
    expires_at = excluded.expires_at,
    scopes = coalesce(excluded.scopes, service_connections.scopes),
    needs_reconnect = false,
    last_sync_error = null;
end;
$$;

-- The caller's own connections with their (encrypted) keys, for syncing.
-- Useless without CONNECTOR_ENCRYPTION_KEY, which only the API has.
create function public.my_service_connection_keys()
returns table (
  service text,
  external_user_id text,
  access_token_enc text,
  refresh_token_enc text,
  expires_at timestamptz,
  last_synced_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
  select service, external_user_id, access_token_enc, refresh_token_enc, expires_at, last_synced_at
  from public.service_connections
  where profile_id = private.my_profile_id();
$$;

-- Save measurements fetched from a connected service for the caller, replacing
-- any already saved for the same day. Only for services the caller has connected.
create function public.save_service_samples(p_service text, p_samples jsonb)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  me uuid := private.my_profile_id();
  sample jsonb;
  saved integer := 0;
begin
  if not exists (
    select 1 from public.service_connections where profile_id = me and service = p_service
  ) then
    raise exception 'Not connected to %', p_service using errcode = '28000';
  end if;
  if jsonb_typeof(p_samples) <> 'array' or jsonb_array_length(p_samples) > 5000 then
    raise exception 'samples must be a list of at most 5000 items' using errcode = '22023';
  end if;

  for sample in select * from jsonb_array_elements(p_samples) loop
    insert into public.health_samples (profile_id, metric, recorded_on, value, recorded_at, source)
    values (
      me,
      sample ->> 'metric',
      (sample ->> 'date')::date,
      (sample ->> 'value')::numeric,
      (sample ->> 'at')::timestamptz,
      p_service
    )
    on conflict (profile_id, metric, recorded_on, source) do update
      set value = excluded.value, recorded_at = excluded.recorded_at;
    saved := saved + 1;
  end loop;
  return saved;
end;
$$;

revoke execute on function public.save_service_connection(text, text, text, text, timestamptz, text) from public;
revoke execute on function public.my_service_connection_keys() from public;
revoke execute on function public.save_service_samples(text, jsonb) from public;
grant execute on function public.save_service_connection(text, text, text, text, timestamptz, text) to authenticated;
grant execute on function public.my_service_connection_keys() to authenticated;
grant execute on function public.save_service_samples(text, jsonb) to authenticated;
