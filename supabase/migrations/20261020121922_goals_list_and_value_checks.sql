-- Goals become a list of fixed choices plus optional notes; allowed-value
-- checks for goal metric and equipment. Spec: context/pages/settings-profile.md.
-- Safe to drop the old free-text goals column: it was empty for every profile.

alter table public.profiles drop column goals;

alter table public.profiles
  add column goals text[] not null default '{}'
    check (goals <@ array['lose_fat', 'build_muscle', 'get_stronger', 'endurance',
                          'general_health', 'mobility']),
  add column goals_notes text check (char_length(goals_notes) <= 500),
  add constraint profiles_goal_metric_check
    check (goal_metric in ('weight', 'body_fat', 'vo2_max', 'resting_hr', 'hrv',
                           'strength', 'steps', 'sleep')),
  add constraint profiles_injuries_notes_length_check
    check (char_length(injuries_notes) <= 1000);

alter table public.training_preferences
  add constraint training_preferences_equipment_check
    check (equipment <@ array['bodyweight', 'dumbbells', 'barbell', 'kettlebell',
                              'resistance_bands', 'pull_up_bar', 'bench', 'cable_machine',
                              'treadmill', 'exercise_bike', 'rowing_machine', 'full_gym']);

-- Dropping the column removed its update permission; grant the new columns.
grant update (goals, goals_notes) on public.profiles to authenticated;
