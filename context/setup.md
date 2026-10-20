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
| Supabase database password | **Yes** | Amol's password manager | Rarely needed; the CLI login covers migrations |

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

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Site shows "Can't reach the server … Try again" | API asleep, network drop, or API not running locally | Tap **Try again**; locally, start the API (Terminal 1) |
| Site shows "The server sent an unexpected reply" | `EXPO_PUBLIC_API_URL` points at the website, not the API | Fix the variable and redeploy the website |
| Website loads but every API call fails in the browser | Website address missing from the API's `CORS_ORIGINS` | Add it on the API project and redeploy the API |
| Local website doesn't show code changes | Dev server missed the change | Stop it and run `npx expo start --web --clear` |
| Everything fails after a quiet week | Supabase free projects **pause after about a week without use** | Supabase dashboard → the project → **Restore** |
| First API call is slow | Free Vercel functions sleep when unused | Normal; later calls are fast |

## Related

- [Architecture](architecture.md): how the parts fit together and why.
- [Conventions](conventions.md): how code and docs are written.
- [Data model](data-model.md): tables and access rules.
- [Roadmap](roadmap.md): what's done and what's next.
