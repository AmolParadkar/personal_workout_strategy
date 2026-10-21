# Setup and Operations

← [Hub: skills.md](skills.md) · Related: [Architecture](architecture.md) · [Conventions](conventions.md) · [Data model](data-model.md) · [Roadmap](roadmap.md)

How to set up, run, change and deploy the app, and where every account and key lives. Commands here are the ones to copy; the reasons behind them are in [Architecture](architecture.md) and [Conventions](conventions.md).

## Accounts

| Service | What it's for | Where |
|---|---|---|
| **GitHub** | Code; Vercel deploys from it | https://github.com/AmolParadkar/personal_workout_strategy |
| **Supabase** (free plan) | Database, sign-in, file storage | Project `workout-strategy`, ref `uxacejerfabbdvufgabv`, region Singapore |
| **Vercel** (free plan) | Hosts the website and the API | Projects `personalworkoutstrategy-frontend` (website) and `personal-workout-strategy` (API) |

Live addresses:

- Website: https://personalworkoutstrategy-frontend.vercel.app
- API: https://personal-workout-strategy.vercel.app (health check: `/api/health`)

## Keys and where they live

| Key | Secret? | Lives in | Notes |
|---|---|---|---|
| Supabase Project URL | No | `backend/.env`, `frontend/.env`, both Vercel projects | |
| Supabase **publishable** key (`sb_publishable_…`, the default one) | No | `backend/.env`, `frontend/.env`, both Vercel projects | Safe in the website; access rules protect the data |
| Supabase **secret** key **`backend-api`** (`sb_secret_…`) | **Yes** | `backend/.env` only | Bypasses all access rules. Used by integration tests; **not** on Vercel |
| Supabase **secret** key **`mac-worker`** (`sb_secret_…`) | **Yes** | `backend/.env` only (`MAC_WORKER_SECRET_KEY`) | Used only by the Mac worker; **not** on Vercel |
| Groq API key (`gsk_…`) | **Yes** | `backend/.env` only (`GROQ_API_KEY`) | Used by the Mac worker for cloud Qwen |
| YouTube Data API key | **Yes** | `backend/.env` only (`YOUTUBE_API_KEY`) | Used by the Mac worker to find exercise videos; restrict it to the YouTube Data API |
| ntfy topic | Keep private | Supabase Vault (`ntfy_topic`) and the ntfy app | Anyone with the name can read the alerts |
| Supabase database password | **Yes** | Amol's password manager | Rarely needed; the CLI login covers migrations |
| `CONNECTOR_ENCRYPTION_KEY` | **Yes** | `backend/.env`, API Vercel project | Encrypts the services' access keys. Make it once (command in `backend/.env.example`). **Changing it means everyone reconnects** |
| `WITHINGS_` / `OURA_` / `WHOOP_` / `POLAR_` `CLIENT_ID` and `CLIENT_SECRET` | ID no, secret **yes** | `backend/.env`, API Vercel project | From each service's developer app ([how](data-sources.md#setting-up-a-services-developer-app-amol-once)). A service without them shows "Not set up yet" |

Rules:

- `.env` files are ignored by git. `backend/.env.example` and `frontend/.env.example` list the variable names.
- Never paste a secret key into chat, an issue, a log or the website.
- One named secret key per component (`backend-api` now, `mac-worker` in M4), so one can be revoked without breaking the others.

**If a secret key leaks:** Supabase → Project Settings → API Keys → Secret keys → create a new key with the same name, put it in `backend/.env`, then delete the leaked key.

## First-time setup on a Mac

1. **Install tools:**
   - **Node.js LTS** from https://nodejs.org (includes `npm` and `npx`).
   - **uv** (Python package manager): https://docs.astral.sh/uv/. It installs Python 3.12 for the project by itself; the Mac's own Python isn't used.
   - **git** (comes with Xcode Command Line Tools).
2. **Get the code:**
   ```
   git clone https://github.com/AmolParadkar/personal_workout_strategy.git
   cd personal_workout_strategy
   ```
3. **Create the settings files** and fill in the values from Supabase (Project Settings → Data API and → API Keys):
   ```
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```
4. **Install dependencies:**
   ```
   cd backend && uv sync && cd ..
   cd frontend && npm install && cd ..
   ```
5. **Supabase CLI login** (once per Mac; opens the browser), then link the project:
   ```
   npx supabase login
   npx supabase link --project-ref uxacejerfabbdvufgabv
   ```

## Running locally

Two terminals:

```
# Terminal 1: the API, at http://localhost:8000 (interactive docs at /docs)
cd backend
uv run uvicorn api.main:app --reload

# Terminal 2: the website, at http://localhost:8081
cd frontend
npm run web
```

The local website uses the **real** Supabase project, so you sign in with your real account.

## Checks before committing

| Where | Command | What it checks |
|---|---|---|
| `backend/` | `uv run ruff format . && uv run ruff check .` | Formatting and lint |
| `backend/` | `uv run pytest` | Unit tests (Supabase faked) |
| `backend/` | `RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v` | Access rules and API against the real project (creates and deletes temporary users). **Run after every migration or API change** |
| `frontend/` | `npm run lint && npm run typecheck` | Lint and types |
| `frontend/` | `npm run api-types:check` | Frontend types match the API. After changing backend models, run `npm run api-types` |
| `frontend/` | `npx expo-doctor` | Expo dependency problems |

## Changing the database

1. `npx supabase migration new <short_description>` (at the project root) creates a file in `supabase/migrations/`.
2. Write the SQL. Every new table needs access rules (see [Conventions: Database](conventions.md#database)).
3. `npx supabase db push --dry-run`, then `npx supabase db push`.
4. Run the integration tests (above).
5. Update [data-model.md](data-model.md) in the same change.

Never edit a migration that's already been pushed; add a new one.

## Deploying

- **Push to `main`** and Vercel redeploys both projects (1–2 minutes). Watch progress in each project's **Deployments** tab.
- **Changed an environment variable?** It only takes effect after **Redeploy** (Deployments → ⋯ → Redeploy).
- Website variables (`EXPO_PUBLIC_…`) must have type **Config**, not Secret. To change one that was saved as Secret, remove it and add it again.
- `EXPO_PUBLIC_API_URL` must start with `https://`.
- The website's address must be in the API's `CORS_ORIGINS`, or the website can't call the API.

Full details: [Architecture: Deployment](architecture.md#deployment).

## Accounts for people

- Public sign-ups are **off**. To add a person: Supabase → Authentication → Users → **Add user → Create new user**, enter email and password, tick **Auto confirm user**. They join the household automatically and see the welcome steps on first sign-in.
- **Forgotten password:** in the same Users list, open the user and set a new password (Supabase's free email service is too limited for reset emails).
- Signed-in sessions last on each device until the person signs out.

## Apple Health

Each person builds the iOS Shortcut once: [apple-health-shortcut.md](apple-health-shortcut.md). The connection token is created in **Settings → Apple Health**; making a new one stops the old one, so paste the new one into the Shortcut.

## Connected services

Withings, Oura, Whoop and Polar each need a developer app (once, Amol): [data-sources.md](data-sources.md#setting-up-a-services-developer-app-amol-once). Then each person taps **Connect** in Settings → Connected services. New data is fetched when the app opens (at most every 3 hours) or with **Sync now**.

## Exercise library

The library (876 exercises from [free-exercise-db](https://github.com/yuhonas/free-exercise-db), public domain) is imported once with `cd backend && uv run python -m scripts.import_exercises` (uses `SUPABASE_SECRET_KEY`). Running it again updates the source fields and keeps guides and videos. To take a newer version of the database, change `COMMIT` in `backend/scripts/import_exercises.py` and run it again.

## Mac worker

The worker runs slow and private jobs on this Mac ([architecture](architecture.md#job-queue-and-worker-safeguards)). One-time setup:

1. **Secret key:** Supabase → Project Settings → API Keys → Secret keys → **Add new secret key** named `mac-worker`. Paste it into `backend/.env` as `MAC_WORKER_SECRET_KEY=` (never in chat, never on Vercel).
2. **Ollama (local AI):** download the Mac app from [ollama.com/download](https://ollama.com/download), move it to Applications and open it once. It starts at login and keeps itself running. Then download the local text model (about 5 GB): `ollama pull qwen3:8b`. (The Qwen vision model is downloaded in M8.)
3. **Start the worker as a background service:** `sh backend/worker/launchd/install.sh`. It starts now, at every login, and restarts if it stops. Log: `~/Library/Logs/workout-strategy-worker.log`. Remove with `--remove`. Run it again after moving the project folder.
4. **Offline alert (ntfy):** install the **ntfy** app on your phone and subscribe to a topic with a long random name (e.g. `workout-strategy-` plus random letters; anyone who knows it can read it). Then in Supabase → SQL Editor run `select vault.create_secret('<your topic>', 'ntfy_topic');`. To change it later: `select vault.update_secret((select id from vault.secrets where name = 'ntfy_topic'), '<new topic>');`.
5. **Groq (cloud Qwen):** sign up at [console.groq.com](https://console.groq.com) (free, no card) → **API Keys** → **Create API key**. Paste it into `backend/.env` as `GROQ_API_KEY=`. If Groq retires the model, set `GROQ_MODEL=` to a current Qwen id from [console.groq.com/docs/models](https://console.groq.com/docs/models). Without a key, the worker uses Ollama.
6. **YouTube Data API key** (exercise videos): [console.cloud.google.com](https://console.cloud.google.com) → create a project → **APIs & Services → Library** → enable **YouTube Data API v3** → **Credentials → Create credentials → API key**. Restrict it to the YouTube Data API v3. Paste it into `backend/.env` as `YOUTUBE_API_KEY=`. Free quota: 10,000 units a day (about 90 exercises).
7. After changing `backend/.env`, restart the worker: `launchctl kickstart -k gui/$(id -u)/com.workoutstrategy.worker`.
8. **Check:** Settings → Mac worker shows **Online**; **Send test job** finishes with "done by the Mac worker".

Running it by hand instead (e.g. to watch the log): stop the service (`launchctl bootout gui/$(id -u)/com.workoutstrategy.worker`), then in `backend/` run `uv run python -m worker`. Install the service again afterwards.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Site shows "Can't reach the server … Try again" | API asleep, network drop, or API not running locally | Tap **Try again**; locally, start the API (Terminal 1) |
| Site shows "The server sent an unexpected reply" | `EXPO_PUBLIC_API_URL` points at the website, not the API | Fix the variable and redeploy the website |
| Website loads but every API call fails in the browser | Website address missing from the API's `CORS_ORIGINS` | Add it on the API project and redeploy the API |
| Local website doesn't show code changes | Dev server missed the change | Stop it and run `npx expo start --web --clear` |
| Everything fails after a quiet week | Supabase free projects **pause after about a week without use** | Supabase dashboard → the project → **Restore** |
| First API call is slow | Free Vercel functions sleep when unused | Normal; later calls are fast |
| "Mac worker offline since …" | The Mac is asleep, off or signed out, or the worker stopped | Wake the Mac and sign in; check the log `~/Library/Logs/workout-strategy-worker.log`; reinstall with `sh backend/worker/launchd/install.sh` |
| Settings shows "Local AI (Ollama): not running" | The Ollama app isn't open | Open Ollama from Applications |

## Related

- [Architecture](architecture.md): how the parts fit together and why.
- [Conventions](conventions.md): how code and docs are written.
- [Data model](data-model.md): tables and access rules.
- [Roadmap](roadmap.md): what's done and what's next.
