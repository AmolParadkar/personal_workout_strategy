# Data Model

← [Hub: skills.md](skills.md) · Related: [Architecture](architecture.md) · [Conventions](conventions.md) · [Roadmap](roadmap.md)

Status: **Draft.** Tables are listed with their key fields and what they're for. Exact column types are decided in the migrations (`supabase/migrations/`), and this file is updated to match.

**General rules** (see also [Conventions: Database](conventions.md#database)):

- Every person-owned table has a `profile_id` and access rules (see [Access rules](#access-rules)).
- Every table has `id`, `created_at`, `updated_at`.
- Anything the LLM produces has a status (e.g. `draft` / `extracted`) until the person confirms it.

## Profiles and settings

Used by: [Settings / Profile](pages/settings-profile.md), every page via the profile dropdown.

| Table | Key fields | Purpose |
|---|---|---|
| `households` | `name` | Groups the two profiles for the "view both" rule. |
| `profiles` | `user_id` (Supabase login), `household_id`, `display_name`, `date_of_birth`, `sex`, `height_cm`, `goals`, `goal_metric`, `injuries_notes`, `onboarded_at` | One row per person. `onboarded_at` is empty until the first-sign-in questions are answered. |
| `training_preferences` | `profile_id`, `equipment[]`, `available_days[]`, `minutes_per_session`, `location` (home / gym / travel) | Inputs to the [Workout Plan](pages/workout-plan.md). |
| `diet_preferences` | `profile_id`, `diet_type`, `cuisines[]`, `allergies[]`, `dislikes[]`, `meals_per_day`, `cooking_minutes` | Inputs to the [Nutrition Plan](pages/nutrition-plan.md). |
| `display_settings` | `profile_id`, `show_weight`, `show_calorie_intake`, `show_calories_burned` (all default false) | Opt-in cards on [Summary](pages/summary.md) and [Progress](pages/progress.md). |

## Health data

Used by: [Summary](pages/summary.md), [Progress](pages/progress.md). Sources: the iOS Shortcut, manual entry, wearables later.

| Table | Key fields | Purpose |
|---|---|---|
| `health_samples` | `profile_id`, `metric` (e.g. steps, weight_kg, sleep_minutes, bedtime, resting_hr, hrv, vo2_max, active_energy_kcal), `value`, `unit`, `recorded_at`, `source` (apple_health / manual / device name) | One generic table for every measured number. New metrics or wearables need no new tables. |
| `ingest_tokens` | `profile_id`, `token_hash`, `last_used_at` | Per-person secret for the iOS Shortcut to send data. |

Daily and weekly figures (averages, trends, baselines) are calculated from `health_samples`, not stored separately, unless performance later requires it.

## Workouts

Used by: [Workout Plan](pages/workout-plan.md), [Plan for Today](pages/plan-for-today.md), [Exercise Guide](pages/exercise-guide.md).

| Table | Key fields | Purpose |
|---|---|---|
| `exercises` | `name`, `source` (free-exercise-db / wger), `equipment`, `primary_muscles[]`, `secondary_muscles[]`, `images[]`, `form_cues`, `precautions`, `video_id`, `video_checked_at` | Shared exercise library (not per person). Form cues and precautions written once by the LLM; video chosen by the scoring job. |
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
| `water_logs` | `profile_id`, `ml`, `logged_at` | Quick-add buttons. |

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

| Table | Key fields | Purpose |
|---|---|---|
| `challenges` | `profile_id`, `started_on`, `start_day`, `status` (active / reset / completed) | One row per attempt; a reset ends the row and starts a new one at Day 1. |
| `challenge_checks` | `challenge_id`, `date`, `item` (diet / workout_1 / workout_2_outdoor / water / reading / photo), `checked_at` | Daily checklist ticks. |

## Jobs and worker

Used by: every LLM flow; see [Architecture: Job queue](architecture.md#job-queue-and-worker-safeguards).

| Table | Key fields | Purpose |
|---|---|---|
| `jobs` | `profile_id`, `type`, `payload`, `result`, `status` (pending / processing / done / failed), `local_only`, `attempts`, `max_attempts`, `run_after`, `locked_by`, `locked_at`, `last_error`, `finished_at` | The queue. |
| `worker_heartbeats` | `worker_id`, `mode` (local / cloud), `last_seen_at`, `version` | Shows "document reader offline" and drives the offline alert. |

## Access rules

Decided: **"view both, change your own".**

- A `households` table groups the two profiles; each profile has a `household_id`.
- **Read:** a login can read every row whose `profile_id` belongs to a profile in its own household.
- **Write (insert / update / delete):** a login can only write rows whose `profile_id` is its own profile.
- **Files in Storage** follow the same rule: both can view, only the owner can upload or delete.
- **Shared tables** (`exercises`, `foods`) are readable by any signed-in user and written only by the backend.
- **Backend-only tables** (`jobs`, `worker_heartbeats`, `ingest_tokens`) aren't accessible from the website; the API and worker use the service key.
- These rules are switched on for every table (see [Conventions: Database](conventions.md#database)).

## Related

- [Architecture](architecture.md): how these tables are read and written.
- [Conventions](conventions.md#database): naming and migration rules.
- [Hub](skills.md): pages and product rules these tables serve.
