# Architecture

← [Hub: skills.md](skills.md) · Related: [Data model](data-model.md) · [Conventions](conventions.md) · [Roadmap](roadmap.md)

How the parts of the system fit together and how requests flow between them. Product decisions live in the [hub](skills.md); table details live in the [data model](data-model.md).

## Components

```
   iPhone (Safari)             iPhone (Shortcuts app)
        │                              │ daily health data
        ▼                              ▼
┌──────────────────────────────────────────────────┐
│ Vercel                                           │
│  ├── frontend/   Expo website (TypeScript)       │
│  └── backend/api FastAPI (Python): quick         │
│                  requests + adding jobs          │
└──────────────┬───────────────────────────────────┘
               │ reads / writes
               ▼
┌──────────────────────────────────────────────────┐
│ Supabase                                         │
│  ├── Postgres: all tables + jobs queue           │
│  ├── Auth: logins                                │
│  └── Storage: documents, food & progress photos  │
└──────────────┬───────────────────────────────────┘
               │ fetches pending jobs (outbound only)
               ▼
┌──────────────────────────────────────────────────┐
│ Mac: backend/worker (Python) + Ollama            │
└──────────────────────────────────────────────────┘

External services: Qwen cloud API (OpenRouter / Groq), YouTube Data API,
exercise database (imported once), nutrition databases (imported once).
```

| Component | Folder | Runs on | Job |
|---|---|---|---|
| Website | `frontend/` | Vercel | Screens only; no business logic. Talks to the API. |
| API | `backend/api/` | Vercel (Python functions) | Fast requests (< a few seconds), validation, adding jobs, trying quick cloud-LLM jobs. |
| Shared core | `backend/core/` | Imported by API and worker | Data models, database access, LLM clients, prompts, nutrition lookup, job queue logic. |
| Worker | `backend/worker/` | Mac (now); cloud host later | Processes queued jobs, including all local-only (private) jobs. |
| Database, auth, storage | `supabase/migrations/` | Supabase | Source of all data; access rules per login. |
| Health data intake | iOS Shortcut ([guide](apple-health-shortcut.md)) | Each iPhone | Sends Apple Health data to the API daily. |
| Direct connectors (M3b) | `backend/core/connectors/` | API on app open; Mac worker daily after M4 | Fetch Withings, Oura, Whoop and Polar data with each person's OAuth connection ([design](data-sources.md#connectors-design)). |

## What the frontend may talk to

- **The API** for all reading and writing of app data.
- **Supabase Auth** directly, for sign-in.
- **Supabase Storage** directly, for uploading files (documents, photos), using upload links the API hands out.
- **Supabase Realtime** directly, only to be told when a job's status changes.

Nothing else. This keeps one data contract (see [Keeping data formats in sync](#keeping-data-formats-in-sync)).

## Request flows

### Signing in and calling the API

1. The website signs in directly with Supabase Auth (email and password) and keeps the session in browser storage.
2. Every API call sends the session's access token: `Authorization: Bearer <token>`.
3. The API checks the token with Supabase (`/auth/v1/user`) to learn who is calling; a missing or invalid token gets `401`.
4. To read or change data, the API calls Supabase **with the user's own token** and the publishable key, so the database access rules decide what's allowed. The secret key is only for backend jobs that genuinely need to bypass them.
5. The website redirects signed-out visitors to `/sign-in`, but that's only convenience: the real protection is steps 3–4.

### API endpoints so far

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/me/profiles` | Household profiles, own first, with `is_own` and `onboarded` |
| `GET /api/profiles/{id}/settings` | One person's settings (one database call); `can_edit` only for your own |
| `PATCH /api/me/settings/{profile,training,diet,display}` | Save one section; only fields sent change |
| `GET /api/profiles/{id}/seventy-five-hard` | 75 Hard page state (day, today's and, until noon, yesterday's checklist); `can_edit` only for your own |
| `POST /api/me/seventy-five-hard/start` | Start a challenge (`current_day`, browser `timezone`); 409 if one is running |
| `PUT /api/me/seventy-five-hard/checks` | Tick or untick one item for today, or yesterday until noon (422 for other days) |
| `POST /api/me/seventy-five-hard/stop` | Stop the running challenge |
| `POST /api/ingest/health` | Apple Health data from the iOS Shortcut (connection token, not sign-in); replies `saved` and `skipped` |
| `GET` / `POST` / `DELETE /api/me/health-connection` | Connection status; create a token (shown once, replaces the old one); disconnect |
| `GET /api/profiles/{id}/connections` | Each service's status (available, connected, last sync, error); `can_edit` only for your own |
| `POST /api/me/connections/{service}/start` | The service's sign-in address (with a signed 10-minute `state`); 409 if its developer app isn't set up |
| `POST /api/me/connections/{service}/complete` | Swap the returned code for keys, save them encrypted, fetch the last 30 days |
| `POST /api/me/connections/sync` | Fetch new data from your connections (only those not synced for 3 hours, unless `force`; just one with `service`). Called on app open, by the header's Refresh button (`force`) and by Sync now (`force` + `service`) |
| `DELETE /api/me/connections/{service}` | Cancel access at the service where possible and delete the keys (fetched data stays) |
| `GET /api/exercises?search=&muscle=&equipment=&offset=` | The exercise library, 30 at a time; words match in any order; with no results, `suggestions` (the 5 closest names) |
| `GET /api/exercises/{id}` | One exercise with guide and video, and whether each is ready, preparing, failed or not found |
| `POST /api/exercises/{id}/video-feedback` | "Is this the right video?": `right` confirms it; `wrong` + reason searches again straight away, avoiding rejected videos (409 if the video changed meanwhile) |
| `POST /api/exercises/{id}/prepare` | Queue the guide and video jobs it still needs (once; not again within a day of a failure) |
| `GET /api/profiles/{id}/workout-plan?week_start=` | The week's active plan (and your draft preview), with muscle coverage; `generating` while the worker makes one |
| `POST /api/me/workout-plan/generate` | Make this week's plan from `today` (`new_week`: only if the week has none; `requested`: a preview if one exists) |
| `POST /api/me/workout-plans/{id}/apply`, `DELETE /api/me/workout-plans/{id}` | Use the previewed draft; or discard it |
| `GET /api/me/session-items/{id}/alternatives`, `PUT /api/me/session-items/{id}/exercise` | Swaps for an exercise in your plan; make a swap |
| `GET /api/profiles/{id}/workout-today?day=[&session_id=]` | Today's session (or an earlier undone one this week), logged sets, completion, earlier undone sessions, streak |
| `PUT /api/me/exercise-logs`, `DELETE /api/me/exercise-logs/{id}` | Save a set (again: corrects it); remove one |
| `POST` / `DELETE /api/me/sessions/{id}/complete` | Finish a workout with an effort rating (again: re-rates); undo |
| `POST /api/me/workout-plan/changes` | A change (day off, extra or shorter session, vacation, cheat meal, medical, something else): returns the week with a preview, or a message if it's for a later week |
| `POST /api/me/plan-changes/{id}/end` | "I'm back" after a medical pause: previews the rest of the week, lighter |
| `GET /api/me/core-lift-options?today=&search=` | Compound lifts you can do, for choosing core lifts |
| `GET /api/jobs/{id}` | A job's status and result (household's jobs) |
| `POST /api/me/jobs/{id}/retry` | Put your own failed job back in the queue |
| `GET /api/worker-status` | Mac worker online (seen in 3 minutes), Ollama running, household jobs waiting |
| `POST /api/me/jobs/test` | Send a `test_echo` job; with `quick`, tried on Vercel first |
| `GET /api/profiles/{id}/water?day=` | Water for a local day, with total and target; `can_edit` only for your own |
| `POST /api/me/water`, `DELETE /api/me/water/{id}?day=` | Log a glass (reaching 3.8 L ticks the 75 Hard water item); undo |
| `GET /api/profiles/{id}/weight`, `POST /api/me/weight` | Latest body weight; log today's (corrects, not duplicates) |
| `POST /api/me/onboarding/complete` | Finish the welcome; refused (422, with `missing`) until required fields are filled |

Values the database rejects come back as `422`, and an invalid sign-in as `401`.

### Reading a page (e.g. Summary)

Website → API → database → API returns data shaped for that page → website renders it.

### Logging a food photo

1. Website asks the API for an upload link and uploads the photo to Storage.
2. Website calls the API: "analyse this photo". The API creates a job.
3. The API **tries the job immediately** with the cloud Qwen vision model (usually a few seconds).
   - If it finishes: the result (suggested dish and ingredients) is returned and the confirmation questions start.
   - If it doesn't finish within Vercel's time limit: the job stays `pending` for the worker, and the website shows "analysing…" and updates when the job is done.
4. The person answers the questions; the API calculates nutrients from the food database and saves the log.

### Uploading a health document (Personal Artifacts)

1. Website uploads the file to Storage and calls the API, which creates a **local-only** job.
2. The Mac worker picks it up when it's on, reads it with Ollama, and writes back the extracted facts as `extracted` (not confirmed).
3. The person reviews and confirms the facts; only then are plans regenerated.

### Regenerating a plan

1. A new week without a plan (app open), "Make a new plan", or later a confirmed change.
2. The API reads the person's settings and the library, and tries Groq straight away (25 s budget); otherwise it queues `generate_workout_plan` and the Mac worker makes it (Groq → Ollama → rules).
3. The whole plan is saved at once (`save_workout_plan`): **active** if the week had none, otherwise a **draft** shown as a preview, which becomes active only when the person confirms.

### Daily health data

1. Each morning the iOS Shortcut sends yesterday's totals and last night's sleep to `POST /api/ingest/health`, with the person's **connection token** (`Authorization: Bearer wst_…`), not a sign-in. Build guide: [apple-health-shortcut.md](apple-health-shortcut.md).
2. The API checks each sample on its own (allowed metric, sensible range; numbers like `"8,421"` or `"78.4 kg"` are accepted). Bad or missing ones are **skipped with a reason**, so they don't lose the rest of the day.
3. The API passes the valid samples to the database function `public.ingest_health_samples`, which looks up the token's **hash**, saves the samples for that person only (replacing any already sent for the same day), and records when the token was last used. The API needs no secret key for this.
4. The reply lists `saved` and `skipped`; a wrong or replaced token gets `401`.

Direct connectors ([M3b](roadmap.md#m3b--direct-connectors)) write to the same `health_samples` table with `source` set to the service; they sync when the person opens the app, and daily on the Mac after M4. Design: [data-sources.md](data-sources.md#connectors-design).

## Job types

| Job | Triggered by | Where it runs | Uses |
|---|---|---|---|
| `analyse_food_photo` | Plan for Today | Vercel first, then worker | Cloud Qwen vision (Ollama backup) |
| `generate_workout_plan` | New week (app open), "Make a new plan"; later confirmed facts, disruptions | Vercel first (Groq, 25 s), then worker (Groq → Ollama → rules) | Cloud Qwen; rules always as the last resort ([how](pages/workout-plan.md#as-built-m6-part-1)) |
| `generate_meal_plan` | Nutrition Plan, confirmed facts, disruptions | Vercel first, then worker | Cloud Qwen |
| `extract_document_facts` | Personal Artifacts upload | **Worker only (local)** unless "Process in cloud now" | Ollama (Qwen vision) |
| `analyse_progress_photo` | Progress | Open question: local or cloud | Qwen vision |
| `find_exercise_video` | Exercise opened without a video (M5), new exercise in a plan (M6); monthly refresh | Worker | YouTube Data API + Qwen (comment rating) |
| `write_exercise_guide` | Exercise opened without a guide (M5), new exercise in a plan (M6) | Worker | Cloud Qwen on Groq, Ollama backup (form cues, precautions) |
| `compute_forecast` | Progress, new data | Vercel first, then worker | Calculations; Qwen for the explanation |

Each job's input and output are Pydantic models in `backend/core/`. **LLM calls** go through `backend/core/llm.py`: Groq (cloud Qwen, `GROQ_MODEL`, default `qwen/qwen3.8-27b`) first, then Ollama on the Mac (`qwen3:8b`); answers must be JSON matching a Pydantic model, so a bad answer fails the attempt and is retried. Jobs that write shared data (the exercise library) get the worker's database access and run on the worker only.

## Job queue and worker safeguards

All slow or LLM work goes through the `jobs` table (see [Data model: Jobs](data-model.md#jobs-and-worker)).

- **Vercel first for quick cloud jobs:** the API tries them straight away; if they don't finish within the time limit they fall back to the queue.
- **No paid cloud worker for now:** queued jobs wait for the Mac worker. See [Future enhancements](skills.md#future-enhancements).
- **Worker modes:** `--mode local` (the Mac: may take any job, including local-only ones) and `--mode cloud` (future: may not take local-only jobs).

Built in M4: job types in `backend/core/jobs/` (one file each, registered with their rules: local-only, try on Vercel, needs Ollama, attempts, time limit); the queue in `backend/core/jobs/queue.py`; the worker in `backend/worker/` (`uv run python -m worker`). The worker looks for new jobs every 3 seconds and runs up to 3 at once (e.g. an exercise's guide and video side by side); its heartbeat continues while jobs run. `test_echo` is a job that only echoes, for checking the pipeline (Settings → Mac worker → Send test job).

Safeguards, because the Mac is a single point of failure:

1. **Job status:** `pending → processing → done / failed`, with attempt count and last error. Jobs are claimed atomically so two workers can't take the same one; jobs stuck in `processing` too long go back to `pending`.
2. **Retries** with growing gaps (1, 5, 25 minutes …, at most 6 hours; 3 attempts by default); after the last attempt the job is `failed`, the error is shown in the app, and there's a **Retry** button.
3. **Heartbeat:** the worker records it's alive every minute; if it stops, the app shows e.g. "Document reader offline since 9:40 pm. Your report is queued."
4. **Auto-restart:** the worker runs as a launchd background service (`backend/worker/launchd/install.sh`) that starts at login and restarts if it stops; Ollama runs from its Mac app, which starts at login. Jobs that need Ollama wait (without using an attempt) while it isn't answering.
5. **Alert:** one ntfy push if the worker has been offline 12 hours and jobs have waited 12 hours, sent by an hourly check inside Supabase (so it works while the Mac is off); at most one every 12 hours.
6. **"Process in cloud now":** a per-document, one-off opt-out of the local-only rule.

## Privacy routing

See the [Privacy model](skills.md#privacy-model) in the hub. In code, each job type declares whether it is **local-only**; the queue refuses to hand a local-only job to a cloud worker unless the person used "Process in cloud now" for that item.

## Keeping data formats in sync

- **One Python codebase** (`backend/`) for the API and the worker; both import the same models from `backend/core/`.
- **Pydantic models are the single source of truth** for every request, response and job payload.
- **Frontend types are generated** from the API's OpenAPI description into `frontend/`; a check fails if the generated file is out of date.
- **Database schema** lives only in `supabase/migrations/`; the Python database layer is written against it and covered by tests.

## Deployment

Two Vercel projects, both built from the GitHub repo's `main` branch on every push:

| Project | Root folder | Address | Environment variables |
|---|---|---|---|
| API (`personal-workout-strategy`) | `backend` | https://personal-workout-strategy.vercel.app | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `CORS_ORIGINS` |
| Website (`personalworkoutstrategy-frontend`) | `frontend` | https://personalworkoutstrategy-frontend.vercel.app | `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `EXPO_PUBLIC_API_URL` |

- **API:** Vercel's FastAPI preset runs `api/main.py` (`[tool.vercel] entrypoint = "api.main:app"` in `pyproject.toml`) as one function; with the preset detected, files in `api/` don't become separate functions. `backend/vercel.json` keeps tests out of the bundle.
- **Website:** `frontend/vercel.json` runs `expo export -p web` and serves `dist/`, sending every path to the app (single-page app).
- **`CORS_ORIGINS`** on the API lists the websites allowed to call it: `https://personalworkoutstrategy-frontend.vercel.app,http://localhost:8081`.
- **`EXPO_PUBLIC_API_URL` must include `https://`** (the website refuses to start otherwise). `EXPO_PUBLIC_` values are built into the website's code, so the website must be **redeployed** after changing them, and in Vercel they must have type **Config**, not Secret (they're public by design).
- Any environment variable change needs a **Redeploy** (Deployments → ⋯ → Redeploy) to take effect.
- The Supabase **secret key is not on Vercel**: the API doesn't use it yet.

## Secrets and configuration

- All keys (Supabase, Qwen provider, YouTube) are environment variables, never committed. `backend/.env.example` and `frontend/.env.example` list the names without values; the real values go in `backend/.env` and `frontend/.env` (ignored by git).
- Current variables:
  - `frontend/.env`: `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (the **default** publishable key; public, protected by the access rules). Only `EXPO_PUBLIC_` variables reach the website, and everything there is visible to visitors.
  - `backend/.env`: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (a secret key named **`backend-api`** in Supabase).
- `GROQ_API_KEY` (and optional `GROQ_MODEL`) on the **API's Vercel project** too, for quick plan generation (M6). Without it, plans are made by the Mac worker.
- Direct connectors (M3b): one OAuth client ID and secret per connected service (`WITHINGS_CLIENT_ID`, `WITHINGS_CLIENT_SECRET`, and the same for `OURA_`, `WHOOP_`, `POLAR_`) and `CONNECTOR_ENCRYPTION_KEY`, in `backend/.env` and the API's Vercel settings. These are not Supabase keys.
- **One named secret key per component**, so a leaked key can be revoked without breaking the others: `backend-api` (integration tests) and `mac-worker` (`MAC_WORKER_SECRET_KEY`, the worker only; never on Vercel).
- Secret keys are never pasted into chat or logs.
- Keys that can read all data (Supabase service key) are only used by the API and worker, never by the website.
- Accounts, where each key lives, and what to do if one leaks: [setup.md](setup.md#keys-and-where-they-live).

## Folder structure

```
personal_workout_strategy/
├── CLAUDE.md           # Points Claude Code at the context files
├── context/            # Spec docs (hub, pages/, architecture, data model, conventions, roadmap)
├── frontend/           # Expo website (TypeScript): src/app (routes), src/features, src/components, src/theme; vercel.json
├── backend/            # One Python codebase
│   ├── core/           # Shared: models, database access, LLM clients, prompts, nutrition lookup, job queue
│   ├── api/            # FastAPI on Vercel
│   ├── worker/         # Job runner (Mac now; cloud mode later)
│   └── tests/
├── supabase/
│   └── migrations/     # Database tables and access rules
```

## Related

- [Hub](skills.md): product decisions, privacy model, rules for every page.
- [Data model](data-model.md): tables behind every flow above.
- [Conventions](conventions.md): how code in each folder is written.
- [Roadmap](roadmap.md): the order these components get built.
- [Setup](setup.md): accounts, keys, running locally and deploying.
