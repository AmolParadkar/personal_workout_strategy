# Data Model

← [Hub: skills.md](skills.md) · Related: [Architecture](architecture.md) · [Conventions](conventions.md) · [Roadmap](roadmap.md)

Status: **Draft.** Tables are listed with their key fields and what they're for. Exact column types are decided in the migrations (`supabase/migrations/`), and this file is updated to match.

**General rules** (see also [Conventions: Database](conventions.md#database)):

- Every person-owned table has a `profile_id` and access rules (see [Access rules](#access-rules)).
- Every table has `id`, `created_at`, `updated_at`.
- Anything the LLM produces has a status (e.g. `draft` / `extracted`) until the person confirms it.

## Profiles and settings

Used by: [Settings / Profile](pages/settings-profile.md), every page via the profile dropdown.

Status: **Built** (migrations `20261020115531_profiles_and_settings.sql`, `20261020121922_goals_list_and_value_checks.sql`).

- A trigger on new logins creates the person's `profiles`, `training_preferences`, `diet_preferences` and `display_settings` rows and puts them in the household (created as "Home" for the first login). The website never inserts or deletes these rows.
- Signed-in users may only update the listed detail columns; ids, `user_id`, `household_id` and `profile_id` can't be changed, so rows can't be moved to another person or household.
- Allowed values: `goals` lose_fat / build_muscle / get_stronger / endurance / general_health / mobility (plus free-text `goals_notes`, up to 500 characters); `goal_metric` weight / body_fat / vo2_max / resting_hr / hrv / strength / steps / sleep; `equipment` bodyweight / dumbbells / barbell / kettlebell / resistance_bands / pull_up_bar / bench / cable_machine / treadmill / exercise_bike / rowing_machine / full_gym; `sex` female / male / other; `height_cm` 50–260; `available_days` mon–sun; `location` home / gym / travel; `diet_type` vegetarian / eggetarian / non_vegetarian; `minutes_per_session` 5–300; `meals_per_day` 1–8; `cooking_minutes` 0–240. The API checks the same values (`backend/core/models/settings.py`) and also requires an age of 13–100.
- Body weight is **not** on the profile: it's a dated measurement in `health_samples` (M3).

| Table | Key fields | Purpose |
|---|---|---|
| `households` | `name` | Groups the two profiles for the "view both" rule. |
| `profiles` | `user_id` (Supabase login), `household_id`, `data_sources[]` + `data_sources_other` (apps and devices used, see [data-sources.md](data-sources.md)), `display_name`, `date_of_birth`, `sex`, `height_cm`, `goals[]`, `goals_notes`, `goal_metric`, `injuries_notes`, `onboarded_at` | One row per person. `onboarded_at` is empty until the first-sign-in questions are answered. |
| `training_preferences` | `profile_id`, `equipment[]`, `available_days[]`, `minutes_per_session`, `location` (home / gym / travel) | Inputs to the [Workout Plan](pages/workout-plan.md). |
| `diet_preferences` | `profile_id`, `diet_type`, `cuisines[]`, `allergies[]`, `dislikes[]`, `meals_per_day`, `cooking_minutes` | Inputs to the [Nutrition Plan](pages/nutrition-plan.md). |
| `display_settings` | `profile_id`, `show_weight`, `show_calorie_intake`, `show_calories_burned` (all default false) | Opt-in cards on [Summary](pages/summary.md) and [Progress](pages/progress.md). |

## Health data

Used by: [Summary](pages/summary.md), [Progress](pages/progress.md), [Settings / Profile](pages/settings-profile.md) (body weight). Sources: the iOS Shortcut ([apple-health-shortcut.md](apple-health-shortcut.md)), manual entry, and direct connections to Withings, Oura, Whoop and Polar ([data-sources.md](data-sources.md#connectors-design)).

Status: **Built** (migrations `20261020162050_health_data_water_and_tokens.sql`, `20261020173625_service_connections.sql`).

| Table | Key fields | Purpose |
|---|---|---|
| `health_samples` | `profile_id`, `metric`, `recorded_on` (local day), `value`, `recorded_at` (exact time, for bedtime / wake time / weigh-ins), `source` (apple_health / manual / withings / oura / whoop / polar); unique per person, metric, day and source | One generic table for every measurement. **One value per metric per day per source**: re-sending a day replaces it. New metrics or wearables need no new tables. |
| `ingest_tokens` | `profile_id` (one per person), `token_hash` (SHA-256), `last_used_at` | The iOS Shortcut's connection token. Only the hash is stored; the token is shown once. Private even within the household; the hash column is never readable. |
| `service_connections` | `profile_id`, `service` (withings / oura / whoop / polar; one row per person per service), `access_token_enc`, `refresh_token_enc`, `expires_at`, `external_user_id`, `connected_at`, `last_synced_at`, `last_sync_error`, `needs_reconnect` | A direct connection. The service's keys are **encrypted by the API** (`CONNECTOR_ENCRYPTION_KEY`) and the key columns are never readable through the table; the household can read the status. |

- **Metrics:** `steps`, `active_energy_kcal`, `walking_running_km`, `sleep_in_bed_minutes`, `sleep_asleep_minutes`, `sleep_deep_minutes`, `sleep_rem_minutes`, `sleep_light_minutes`, `sleep_score`, `bedtime`, `wake_time` (time only, in `recorded_at`), `weight_kg`, `body_fat_pct`, `muscle_mass_kg`, `resting_hr`, `hrv_ms`, `vo2_max`, `systolic_mmhg`, `diastolic_mmhg`, `readiness_score` (Oura), `recovery_score` and `strain` (Whoop). Units are fixed per metric (in the name). Allowed ranges are in `backend/core/models/health_data.py`.
- **For sleep, `recorded_on` is the morning you woke up**; for daily totals it's the day they happened.
- Access: the household can read measurements; each person can add or correct only their own (manual weigh-ins). Shortcut data goes through the database function `public.ingest_health_samples(token, samples)`, which checks the token hash and saves only for that token's profile, so the API needs no secret key.
- **Connected services** write through `public.save_service_samples(service, samples)`, which saves only for the caller and only for a service they've connected. Keys are saved with `public.save_service_connection(...)` and read back (still encrypted) with `public.my_service_connection_keys()`, both limited to the caller's own connections.
- **Same metric from several sources:** every source is kept; pages pick one per metric with the preference order in `backend/core/connectors/__init__.py` (`SOURCE_PREFERENCE`): the specialist device first. `AI_ALLOWED` there says which sources' data may go to the LLM.

Daily and weekly figures (averages, trends, baselines) are calculated from `health_samples`, not stored separately, unless performance later requires it.

## Workouts

Used by: [Workout Plan](pages/workout-plan.md), [Plan for Today](pages/plan-for-today.md), [Exercise Guide](pages/exercise-guide.md).

| Table | Key fields | Purpose |
|---|---|---|
| `exercises` | `id` (the source's id, e.g. `Barbell_Squat`), `name`, `source`, `category`, `level`, `force`, `mechanic`, `equipment`, `primary_muscles[]`, `secondary_muscles[]`, `instructions[]`, `images[]` (CDN addresses), `about`, `form_cues[]`, `precautions[]`, `guide_model`, `guide_written_at`, `video_id`, `video_title`, `video_channel`, `video_duration_seconds`, `video_views`, `video_score`, `video_checked_at` | Shared exercise library (not per person), **built in M5** (migration `20261021052715_exercises.sql`): 876 exercises from free-exercise-db. Everyone signed in reads it; only the importer and the worker (secret keys) write. Guide text written once by the LLM; video chosen by the scoring job. |
| `workout_plans` | `profile_id`, `week_start`, `status` (draft / active / superseded), `rationale`, `job_id` | One plan per person per week. A draft is the preview shown before a change is applied. |
| `workout_sessions` | `plan_id`, `date`, `title`, `focus` (e.g. legs), `explanation` | One per training day. |
| `session_items` | `session_id`, `phase` (cardio / mobility / activation / main / cooldown), `position`, `exercise_id`, `sets`, `reps`, `target_load_kg`, `duration_min` | The five-phase structure. |
| `exercise_logs` | `profile_id`, `session_item_id`, `set_number`, `reps`, `load_kg`, `logged_at` | What was actually done; drives progressive overload and load capacity. |
| `session_completions` | `profile_id`, `session_id`, `completed_at`, `effort` (easy / right / too_hard) | Workout streak and effort feedback. |

## Nutrition

Used by: [Nutrition Plan](pages/nutrition-plan.md), [Plan for Today](pages/plan-for-today.md), [Summary](pages/summary.md).

| Table | Key fields | Purpose |
|---|---|---|
| `foods` | `name`, `source` (usda / ifct), `per_100g` nutrients (calories, protein, carbs, fat, micros) | Imported nutrition database. All nutrient numbers come from here. |
| `meal_plans` | `profile_id`, `week_start`, `status` (draft / active / superseded), `job_id` | One plan per person per week. |
| `daily_targets` | `meal_plan_id`, `date`, calories, protein, carbs, fat, `micros`, `reasons` | Targets with their one-line reasons. |
| `planned_meals` | `meal_plan_id`, `date`, `slot` (breakfast / lunch / dinner / snack), `name`, `ingredients` (food_id + grams), `nutrients` | Recommended meals; also feed the grocery list. |
| `food_logs` | `profile_id`, `date`, `slot`, `method` (as_planned / photo / manual), `planned_meal_id`, `name`, `photo_path`, `nutrients` | What was actually eaten. |
| `food_log_items` | `food_log_id`, `food_id`, `grams` | Ingredient breakdown behind each log (from the photo questions or manual entry). |
| `favourite_meals` | `profile_id`, `name`, `items` (food_id + grams) | One-tap logging of repeated meals. |
| `water_logs` | `profile_id`, `ml` (1–2000), `logged_on` (the person's local date, sent by the website), `logged_at` | Quick-add buttons and Undo on Plan for Today. **Built (M3).** The daily target is `profiles.water_target_ml` (default 3000, 500–8000). |

## Health records

Used by: [Personal Artifacts](pages/personal-artifacts.md), [Summary](pages/summary.md), [Plan for Today](pages/plan-for-today.md), [Progress](pages/progress.md).

| Table | Key fields | Purpose |
|---|---|---|
| `documents` | `profile_id`, `storage_path`, `kind` (lab_report / photo / doctor_note / typed_note), `job_id`, `cloud_override` | Uploaded files. `cloud_override` records a "Process in cloud now" choice. |
| `health_facts` | `profile_id`, `document_id`, `category` (lab_marker / condition / injury / note), `name`, `value`, `unit`, `range_low`, `range_high`, `flag`, `measured_on`, `status` (extracted / confirmed / rejected) | Facts pulled from documents. Only `confirmed` facts are used by plans. |
| `medications` | `profile_id`, `name`, `dose`, `schedule`, `starts_on`, `ends_on`, `source_fact_id` | Medication list. |
| `medication_doses` | `medication_id`, `scheduled_for`, `taken_at` | Daily checkboxes; adherence %. |
| `appointments` | `profile_id`, `kind` (appointment / screening / lab_test), `title`, `due_on`, `status`, `source_fact_id` | Summary action items. |
| `progress_photos` | `profile_id`, `taken_on`, `storage_path`, `analysis`, `job_id` | Progress pictures and their analysis. |

## Progress and planning

Used by: [Progress](pages/progress.md), [Summary](pages/summary.md).

| Table | Key fields | Purpose |
|---|---|---|
| `disruptions` | `profile_id`, `starts_on`, `ends_on`, `kind` (vacation / travel / festival / illness / busy_week), `notes`, `suggestions`, `plans_applied` | Planned disruptions and their suggested actions. |
| `forecasts` | `profile_id`, `metric`, `generated_at`, `horizon_weeks`, `low`, `high`, `explanation` | Cached forecast ranges. What-if scenarios are calculated on request and not stored. |

## 75 Hard

Used by: [75 Hard](pages/75-hard.md).

Status: **Built** (migration `20261020151423_seventy_five_hard.sql`).

| Table | Key fields | Purpose |
|---|---|---|
| `challenges` | `profile_id`, `started_on`, `start_day` (1–75), `timezone`, `stopped_at` | One row per start. At most one running (not stopped) per person. Resets and completion are **not stored**; they're calculated from the ticks. |
| `challenge_checks` | `profile_id`, `date`, `item` (diet / workout_1 / workout_2_outdoor / water / reading / photo); unique per person, date and item | One row per ticked item per day; unticking deletes the row. Stored per person and date (not per challenge), so ticks never need moving when the count restarts. |

- Access: both household members can read; only the owner can start or stop their challenge and tick or untick their items (insert / delete).
- The calculation lives in `backend/core/seventy_five_hard.py` (see [75 Hard page](pages/75-hard.md#rules)).

## Jobs and worker

Used by: every LLM flow; see [Architecture: Job queue](architecture.md#job-queue-and-worker-safeguards).

Status: **Built** (migration `20261020192131_job_queue.sql`).

| Table | Key fields | Purpose |
|---|---|---|
| `jobs` | `profile_id` (empty for household-wide jobs), `type`, `payload`, `result`, `status` (pending / processing / done / failed), `local_only`, `allow_cloud` ("Process in cloud now"), `attempts`, `max_attempts`, `run_after`, `locked_by`, `locked_at`, `last_error`, `finished_at` | The queue. Job types are a fixed list (the planned ones plus `test_echo`). |
| `worker_heartbeats` | `worker_id`, `mode` (local / cloud), `version`, `ollama_ok`, `started_at`, `last_seen_at` | Shows "offline since …" and drives the offline alert. |
| `private.alert_state` | `name`, `last_sent_at` | When the offline alert was last sent (at most every 12 hours). Not reachable through the API. |

- Access: the household can read jobs and anyone signed in can read worker status; each person can add jobs only for themselves, and retry their own failed jobs with `public.retry_job(id)`. Everything else is done by the worker with the `mac-worker` secret key: `public.claim_job(worker_id, mode)` (atomic, `skip locked`; a cloud worker never gets a local-only job unless `allow_cloud`) and `public.requeue_stuck_jobs(interval)`, both for the secret key only.
- **Offline alert:** `private.check_worker_offline()` runs hourly in Supabase (`pg_cron`) and sends an ntfy push (`pg_net`) when no worker has been seen for 12 hours and jobs have waited 12 hours. The ntfy topic is a Vault secret named `ntfy_topic` ([setup](setup.md#mac-worker)).

## Access rules

Decided: **"view both, change your own".**

- A `households` table groups the two profiles; each profile has a `household_id`.
- **Read:** a login can read every row whose `profile_id` belongs to a profile in its own household.
- **Write (insert / update / delete):** a login can only write rows whose `profile_id` is its own profile.
- **Files in Storage** follow the same rule: both can view, only the owner can upload or delete.
- **Shared tables** (`exercises`, `foods`) are readable by any signed-in user and written only by the backend.
- **Worker-written tables** (`jobs`, `worker_heartbeats`): the website can read status but only the worker (secret key) changes jobs after they're added. `ingest_tokens` and `service_connections` keep their secret columns unreadable.
- These rules are switched on for every table (see [Conventions: Database](conventions.md#database)).
- **Accounts by invitation only:** public sign-ups are switched off in Supabase; both accounts are invited from the dashboard, so every account belongs to the one household.
- Verified by `backend/tests/integration/test_access_rules.py` (see [Conventions: Database](conventions.md#database)).

## Related

- [Architecture](architecture.md): how these tables are read and written.
- [Conventions](conventions.md#database): naming and migration rules.
- [Hub](skills.md): pages and product rules these tables serve.
