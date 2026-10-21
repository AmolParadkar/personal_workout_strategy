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

## M2 — 75 Hard ✅

Quick to build and already in use, so it comes early.

- [x] `challenges`, `challenge_checks` tables with access rules
- [x] [75 Hard](pages/75-hard.md) checklist, day counter, "What day are you on?", reset rule with noon grace, completion, stop
- [x] 75 Hard link: always on your own profile; on the other person's only while they have a challenge running

## M3 — Health data intake

- [x] `health_samples`, `ingest_tokens`, `water_logs` tables with access rules
- [x] Ingest API endpoint (connection token, per-sample checks, re-sends replace)
- [x] Connection token in Settings → Apple Health (shown once, copy buttons, status)
- [x] iOS Shortcut documented: [apple-health-shortcut.md](apple-health-shortcut.md)
- [ ] Shortcut built on both iPhones and first real data received (Amol, spouse)
- [x] Water quick-add on Plan for Today (+250 / +500 ml, Undo, per-person target; a gallon ticks 75 Hard's water item)
- [x] Body weight in Settings (latest + log today's), stored in `health_samples`
- [x] "Apps and devices you use" in Settings (`profiles.data_sources`)
- [ ] Both fill in their apps and devices (Amol, spouse)
- [x] Assess each service in [data-sources.md](data-sources.md): direct connection possible for Withings, Oura, Whoop and Polar

## M3b — Direct connectors ✅

Design: [data-sources.md](data-sources.md#connectors-design). Built and deployed; switching the services on is parked until the end: see [After development](#after-development--switch-on-the-integrations).

- [x] Add Polar, Suunto, Coros, Amazfit and Dexcom to "Apps and devices you use"
- [x] `service_connections` table (encrypted keys, status readable, keys not) and new metrics (body fat, HRV, readiness, recovery, strain, blood pressure, sleep stages)
- [x] Connect / Disconnect in Settings, `/connect/<service>` return page, signed `state`
- [x] Withings connector (weight, body fat, blood pressure, sleep, activity)
- [x] Oura connector (sleep, readiness, HRV, steps)
- [x] Whoop connector (recovery, strain, sleep, workouts)
- [x] Polar connector (steps, activity, sleep, workouts)
- [x] Sync on app open (over 3 hours since last), **Sync now** per service, and a **Refresh** button (↻) in the header for all services
- [x] Per-metric source preference when two sources send the same metric (used for body weight; other pages use it as they're built)

## M4 — Job queue and worker ✅

- [x] `jobs`, `worker_heartbeats` tables
- [x] Worker with claiming, retries, stuck-job recovery, heartbeat
- [x] launchd setup for the worker (`backend/worker/launchd/install.sh`); Ollama runs from its Mac app
- [x] Offline status in the app (Settings → Mac worker, notice on every page) and offline alert (ntfy, hourly check in Supabase)
- [x] "Vercel first, then queue" helper for quick jobs
- [x] Set up on this Mac (Amol): `mac-worker` secret key, Ollama app, `install.sh`, ntfy topic (test notification received 2026-10-21): [how](setup.md#mac-worker)

## M5 — Exercise library and Exercise Guide ✅

- [x] Import free-exercise-db into `exercises` (876 exercises; `scripts/import_exercises.py`)
- [x] Body map component (red primary / light red secondary)
- [x] Form cues and precautions job (Groq, Ollama backup)
- [x] YouTube video scoring job (under 3 min, Shorts allowed)
- [x] [Exercise Guide](pages/exercise-guide.md) pages: searchable library and exercise detail
- [x] Groq and YouTube keys in `backend/.env` (Amol; both checked 2026-10-21): [how](setup.md#mac-worker)

## M6 — Workout plans

Built in two parts. Part 1 (plans) is done; part 2 (doing the workout) is next.

- [x] Workout tables (plans, sessions, items, logs, completions); training experience in Settings
- [x] Plan generation with the five phases: rules + Groq on Vercel, Mac worker backup (Groq → Ollama → rules)
- [x] [Workout Plan](pages/workout-plan.md): weekly view, new plan with preview, swaps, muscle coverage, body weight input
- [x] Exercise Guide: this week's exercises by day and phase
- [x] `GROQ_API_KEY` on the API's Vercel project (Amol), so plans are made straight away
- [ ] Part 2: [Plan for Today](pages/plan-for-today.md) workout section: logging sets, effort feedback, streak
- [ ] Part 2: progressive overload in the next week's plan
- [ ] Part 2: change requests (add a session, mark a day unavailable) with preview of what moves

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

## After development — switch on the integrations

Parked on 2026-10-21 until the main development (M4–M10) is done. The code is live, and the encryption key is set (`CONNECTOR_ENCRYPTION_KEY`); each service shows "Not set up yet" until its developer app's keys are added.

- [x] Make `CONNECTOR_ENCRYPTION_KEY` (in `backend/.env`; also on Vercel)
- [ ] Register developer apps for Withings, Oura, Whoop, Polar; client IDs and secrets in `backend/.env` and Vercel (Amol): [how](data-sources.md#setting-up-a-services-developer-app-amol-once)
- [ ] Connect each service once with a real account and check its data (the connectors follow each API's docs but haven't met the real services yet)
- [ ] Confirm Oura and Whoop terms on AI use; set each source's "AI allowed" flag
- [ ] Daily sync of both people's connections on the Mac worker (after M4)

## Later

- [ ] Phase 2: iPhone app with direct Apple Health access ($99/year Apple account)
- [ ] Always-on cloud worker ([future enhancement](skills.md#future-enhancements))
- [ ] Parked Workout Plan suggestions ([list](pages/workout-plan.md#out-of-scope))

## Related

- [Hub](skills.md): what each page does.
- [Architecture](architecture.md) and [Data model](data-model.md): what each milestone builds.
- [Conventions](conventions.md): how it's built.
