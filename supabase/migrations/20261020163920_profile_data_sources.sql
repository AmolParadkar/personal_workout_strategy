-- "Apps and devices you use": which health apps and devices each person uses,
-- so we know which connections are worth building and can give tailored advice.
-- Spec: context/pages/settings-profile.md, context/data-sources.md.

alter table public.profiles
  add column data_sources text[] not null default '{}'
    check (data_sources <@ array[
      'iphone_health', 'apple_watch', 'garmin', 'fitbit', 'samsung_watch',
      'oura', 'whoop',
      'withings', 'other_scale', 'bp_monitor', 'glucose_monitor',
      'strava', 'nike_run_club', 'myfitnesspal', 'cronometer', 'healthifyme'
    ]),
  add column data_sources_other text check (char_length(data_sources_other) <= 200);

grant update (data_sources, data_sources_other) on public.profiles to authenticated;
