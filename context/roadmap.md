# Roadmap

← [Hub: skills.md](skills.md) · Related: [Architecture](architecture.md) · [Data model](data-model.md) · [Conventions](conventions.md)

Build order as milestones. Tick items as they're done; each milestone links to the pages and docs it covers. The order can change; record changes in the [hub change log](skills.md#change-log).

## M0 — Spec and structure ✅

- [x] All 9 pages specified ([hub](skills.md#pages))
- [x] Stack and architecture decided ([architecture](architecture.md))
- [x] Project folders and `.gitignore` created
- [x] Context docs: hub, pages, architecture, data model, conventions, roadmap, root `CLAUDE.md`

## M1 — Foundation ✅

- [x] Decide who can see whose data: view both, change your own ([access rules](data-model.md#access-rules))
- [x] Create Supabase project (Amol) and connect it: keys in `backend/.env` and `frontend/.env`, both verified
- [x] Backend skeleton: uv project (Python 3.12), FastAPI app with `/api/health`, ruff, pytest
- [x] Frontend skeleton: Expo Router website (SDK 58) with the 9 empty pages, navigation bar and profile dropdown (placeholder profiles)
- [x] Deploy website and API to Vercel: two projects, auto-deploy on push to `main`, tested live end to end
- [x] Sign-in with Supabase Auth: email and password, sign-in page, signed-out visitors redirected, real profiles in the dropdown, sign out
- [x] Create both real accounts in Supabase (Amol)
- [x] `households`, `profiles`, `training_preferences`, `diet_preferences`, `display_settings` tables with access rules (25 access checks passing)
- [x] Switch off public sign-ups in Supabase (Amol): verified, sign-up attempts are refused
- [x] [Settings / Profile](pages/settings-profile.md) page and first sign-in questions (3-step welcome)
- [x] Type generation from API to frontend, with an up-to-date check (`npm run api-types`, `npm run api-types:check`)
- [x] Write [setup.md](setup.md) (accounts, keys, running locally, checks, database changes, deploying, troubleshooting)

## M2 — 75 Hard

- [ ] Show the 75 Hard link only for profiles with an active challenge (shown for everyone until then; `TODO(M2)` in `NavBar.tsx`)

Quick to build and already in use, so it comes early.

- [ ] `challenges`, `challenge_checks` tables
- [ ] [75 Hard](pages/75-hard.md) checklist, day counter, "What day are you on?", midnight reset

## M3 — Health data intake

- [ ] `health_samples`, `ingest_tokens` tables
- [ ] Ingest API endpoint
- [ ] iOS Shortcut built and documented in `shortcuts/`
- [ ] Water quick-add (`water_logs`)
- [ ] Ask for a starting body weight (Settings or Summary prompt), stored in `health_samples`

## M4 — Job queue and worker

- [ ] `jobs`, `worker_heartbeats` tables
- [ ] Worker with claiming, retries, stuck-job recovery, heartbeat
- [ ] launchd setup for worker and Ollama on the Mac
- [ ] Offline status in the app and offline alert
- [ ] "Vercel first, then queue" helper for quick jobs

## M5 — Exercise library and Exercise Guide

- [ ] Import free-exercise-db into `exercises`
- [ ] Body map component (red primary / light red secondary)
- [ ] Form cues and precautions job
- [ ] YouTube video scoring job (under 3 min, Shorts allowed)
- [ ] [Exercise Guide](pages/exercise-guide.md) pages

## M6 — Workout plans

- [ ] Workout tables (plans, sessions, items, logs, completions)
- [ ] Plan generation job with the five phases
- [ ] [Workout Plan](pages/workout-plan.md): weekly view, change + preview, swaps, muscle coverage, body weight input
- [ ] [Plan for Today](pages/plan-for-today.md) workout section: logging sets, effort feedback, streak
- [ ] Progressive overload in the next week's plan

## M7 — Nutrition

- [ ] Import USDA / IFCT into `foods`
- [ ] Meal plan generation job, daily targets with reasons
- [ ] [Nutrition Plan](pages/nutrition-plan.md): weekly view, change + preview, swaps, grocery list
- [ ] [Plan for Today](pages/plan-for-today.md) meals: as recommended, manual, favourites
- [ ] Food photo flow with confirmation questions

## M8 — Summary dashboard

- [ ] [Summary](pages/summary.md) cards: default, opt-in, trend arrows, baselines, "so what" lines
- [ ] Missing-data messages

## M9 — Personal Artifacts

- [ ] Ollama + Qwen vision set up on the Mac
- [ ] Upload, local extraction job, review and confirm screen
- [ ] Confirmed facts feed plan generation
- [ ] Medications, doses on Plan for Today, appointments and action items
- [ ] Condition-driven Summary cards

## M10 — Progress

- [ ] Trend charts and insights
- [ ] Forecast ranges
- [ ] What-if simulator
- [ ] Disruption planning and travel plan versions
- [ ] Progress photos (after deciding local vs cloud)

## Later

- [ ] Phase 2: iPhone app with direct Apple Health access ($99/year Apple account)
- [ ] Always-on cloud worker ([future enhancement](skills.md#future-enhancements))
- [ ] Parked Workout Plan suggestions ([list](pages/workout-plan.md#out-of-scope))

## Related

- [Hub](skills.md): what each page does.
- [Architecture](architecture.md) and [Data model](data-model.md): what each milestone builds.
- [Conventions](conventions.md): how it's built.
