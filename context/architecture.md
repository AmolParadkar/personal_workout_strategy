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
| Health data intake | `shortcuts/` | Each iPhone | Sends Apple Health data to the API daily. |

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

1. Person asks for a new plan (or a confirmed change triggers one). The API creates a job.
2. Quick attempt on Vercel; otherwise the worker processes it.
3. The result is saved as a **draft** plan, shown as a preview; it becomes active only when the person confirms.

### Daily health data

The iOS Shortcut sends a batch of readings to an API endpoint with a per-person secret token. The API validates and stores them as health samples.

## Job types

| Job | Triggered by | Where it runs | Uses |
|---|---|---|---|
| `analyse_food_photo` | Plan for Today | Vercel first, then worker | Cloud Qwen vision (Ollama backup) |
| `generate_workout_plan` | Workout Plan, confirmed facts, disruptions | Vercel first, then worker | Cloud Qwen |
| `generate_meal_plan` | Nutrition Plan, confirmed facts, disruptions | Vercel first, then worker | Cloud Qwen |
| `extract_document_facts` | Personal Artifacts upload | **Worker only (local)** unless "Process in cloud now" | Ollama (Qwen vision) |
| `analyse_progress_photo` | Progress | Open question: local or cloud | Qwen vision |
| `find_exercise_video` | New exercise in a plan; monthly refresh | Worker | YouTube Data API + Qwen (comment rating) |
| `write_exercise_guide` | New exercise in a plan | Worker | Cloud Qwen (form cues, precautions) |
| `compute_forecast` | Progress, new data | Vercel first, then worker | Calculations; Qwen for the explanation |

Each job's input and output are Pydantic models in `backend/core/`.

## Job queue and worker safeguards

All slow or LLM work goes through the `jobs` table (see [Data model: Jobs](data-model.md#jobs-and-worker)).

- **Vercel first for quick cloud jobs:** the API tries them straight away; if they don't finish within the time limit they fall back to the queue.
- **No paid cloud worker for now:** queued jobs wait for the Mac worker. See [Future enhancements](skills.md#future-enhancements).
- **Worker modes:** `--mode local` (the Mac: may take any job, including local-only ones) and `--mode cloud` (future: may not take local-only jobs).

Safeguards, because the Mac is a single point of failure:

1. **Job status:** `pending → processing → done / failed`, with attempt count and last error. Jobs are claimed atomically so two workers can't take the same one; jobs stuck in `processing` too long go back to `pending`.
2. **Retries** with growing gaps; after the last attempt the job is `failed`, the error is shown in the app, and there's a **Retry** button.
3. **Heartbeat:** the worker records it's alive every minute; if it stops, the app shows e.g. "Document reader offline since 9:40 pm. Your report is queued."
4. **Auto-restart:** the worker and Ollama run as macOS background services (launchd), start at login and restart on crash; the worker checks Ollama responds before taking a job.
5. **Alert:** one notification (email or ntfy) if the worker has been offline ~12 hours and jobs are waiting.
6. **"Process in cloud now":** a per-document, one-off opt-out of the local-only rule.

## Privacy routing

See the [Privacy model](skills.md#privacy-model) in the hub. In code, each job type declares whether it is **local-only**; the queue refuses to hand a local-only job to a cloud worker unless the person used "Process in cloud now" for that item.

## Keeping data formats in sync

- **One Python codebase** (`backend/`) for the API and the worker; both import the same models from `backend/core/`.
- **Pydantic models are the single source of truth** for every request, response and job payload.
- **Frontend types are generated** from the API's OpenAPI description into `frontend/`; a check fails if the generated file is out of date.
- **Database schema** lives only in `supabase/migrations/`; the Python database layer is written against it and covered by tests.

## Secrets and configuration

- All keys (Supabase, Qwen provider, YouTube) are environment variables, never committed. `backend/.env.example` and `frontend/.env.example` list the names without values; the real values go in `backend/.env` and `frontend/.env` (ignored by git).
- Current variables:
  - `frontend/.env`: `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (the **default** publishable key; public, protected by the access rules). Only `EXPO_PUBLIC_` variables reach the website, and everything there is visible to visitors.
  - `backend/.env`: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (a secret key named **`backend-api`** in Supabase).
- **One named secret key per component**, so a leaked key can be revoked without breaking the others: `backend-api` now; `mac-worker` for the worker in M4.
- Secret keys are never pasted into chat or logs.
- Keys that can read all data (Supabase service key) are only used by the API and worker, never by the website.
- Details of accounts and setup will go in a `setup.md` when we reach that step (see [Roadmap](roadmap.md)).

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
└── shortcuts/          # iOS Shortcut instructions + data format
```

## Related

- [Hub](skills.md): product decisions, privacy model, rules for every page.
- [Data model](data-model.md): tables behind every flow above.
- [Conventions](conventions.md): how code in each folder is written.
- [Roadmap](roadmap.md): the order these components get built.
