# Personal Workout Strategy — Hub

_Last updated: 2026-10-20_

This is the **hub** for the project's context files. It holds the app's structure, technical decisions and rules that apply to every page. Each page has its own file in [pages/](pages/), linked below; every file links back here and to its related pages.

## Project docs

| File | What it holds |
|---|---|
| [architecture.md](architecture.md) | Components, request flows, job types, job queue and worker safeguards, privacy routing, folder structure |
| [data-model.md](data-model.md) | Every database table, grouped by area, with the pages that use it |
| [conventions.md](conventions.md) | How code and docs are written: Python, TypeScript, database, LLM, testing, git, docs |
| [roadmap.md](roadmap.md) | Build milestones with checkboxes |
| [apple-health-shortcut.md](apple-health-shortcut.md) | Step-by-step guide to the iOS Shortcut that sends Apple Health data daily, and the message format |
| [data-sources.md](data-sources.md) | Which health apps and devices can feed the app, how, and the plan for direct connections |
| [setup.md](setup.md) | Accounts, keys, first-time setup, running locally, checks, database changes, deploying, troubleshooting |
| [pages/](pages/) | One spec file per page (table below) |
| `../CLAUDE.md` | Root file Claude Code reads every session; points here |

**How these files are kept up to date:**

- Changes to functionality, app structure or technical decisions are recorded in this file.
- Details specific to one page go in that page's file.
- All Markdown files live in `context/`. Page files live in `context/pages/`.
- Every file links to related files so the set can be navigated like a graph.

## App overview

A personalised health app for two users: **Amol** and **his spouse**. Both use iPhones.

## Pages

| # | Page | Purpose | Status |
|---|---|---|---|
| 1 | [Summary](pages/summary.md) | Read-only dashboard: "How am I doing right now?" | Defined |
| 2 | [Plan for Today](pages/plan-for-today.md) | Today's workout and meals, plus all daily logging (meals, water, medications) | Workout and water built (M3, M6); meals in M7 |
| 3 | [Workout Plan](pages/workout-plan.md) | Weekly customised workout plan the person can change | Built (M6) |
| 4 | [Nutrition Plan](pages/nutrition-plan.md) | Weekly meal plan with macro / micro targets the person can change | Built (M7 part 1) |
| 5 | [Progress](pages/progress.md) | Long-term trends, insights, forecasts, what-if simulator, disruption planning | Defined (1 open question) |
| 6 | [75 Hard](pages/75-hard.md) | Simple daily 75 Hard checklist and day counter | Built (M2) |
| 7 | [Exercise Guide](pages/exercise-guide.md) | Diagram, body map, form cues, precautions and best short video for each exercise | Built (M5; plan view in M6) |
| 8 | [Personal Artifacts](pages/personal-artifacts.md) | Upload health documents; confirmed facts adjust the plans | Defined |
| 9 | [Settings / Profile](pages/settings-profile.md) | Personal details (plan inputs) and opt-in card switches | Built (M1) |

**Profile switcher:** a simple dropdown at the top of every page switches between profiles and opens [Settings / Profile](pages/settings-profile.md).

### How the pages connect

- [Settings / Profile](pages/settings-profile.md) and [Personal Artifacts](pages/personal-artifacts.md) are the **inputs** to the LLM plans.
- [Workout Plan](pages/workout-plan.md) and [Nutrition Plan](pages/nutrition-plan.md) are the **weekly plans**; [Plan for Today](pages/plan-for-today.md) shows today's slice and is where everything is **logged**.
- [Exercise Guide](pages/exercise-guide.md) explains every exercise in the plan.
- [Summary](pages/summary.md) shows **now**; [Progress](pages/progress.md) shows **history and future**.
- [75 Hard](pages/75-hard.md) stands alone as a personal checklist.

## Technical decisions

- **Phase 1 is a website.** It becomes an iPhone app once the features are settled. Publishing to Apple ($99/year developer account) is on hold until then.
- **Framework:** Expo, published as a website, so the same code later builds the iPhone app.
- **Code layout:** app logic (plan generation, LLM calls, data storage) lives in the backend, not the screens, so moving to the app later mostly reuses code.
- **Hosting (all free tiers):**
  - Website on **Vercel**: https://personalworkoutstrategy-frontend.vercel.app
  - API on **Vercel**: https://personal-workout-strategy.vercel.app
  - Both redeploy automatically on every push to `main`. Details: [Architecture: Deployment](architecture.md#deployment).
  - Database, login and file storage on **Supabase** (free plan; it pauses after about a week without use).
- **LLM:**
  - **Qwen** through a free cloud API (e.g. OpenRouter, Groq) for building plans and analysing food photos.
  - **Ollama** on a local machine as a backup, and as the only model that reads health documents (see [Privacy model](#privacy-model)).
- **Split of responsibilities:** the frontend and the backend / agentic logic (LLM calls, plan generation, photo analysis) are kept separate. **Vercel** hosts the website and the backend API; **Supabase** holds the database, login and file storage.
- **Local worker:** a program on the local Mac that fetches pending jobs (e.g. documents to read) from Supabase, processes them with Ollama, and writes the results back. The Mac is never exposed to the internet, so no tunnel is needed.
- **Job queue:** all slow or LLM work goes through a job queue in the database. Quick cloud-LLM jobs (e.g. food photos) try on Vercel first and fall back to the queue. No paid cloud worker for now ($0 budget): queued jobs wait for the Mac worker (see [Future enhancements](#future-enhancements)). The Mac worker has safeguards: job statuses with retries, heartbeat and offline notice, auto-restart, offline alert, and a "Process in cloud now" button. Details: [Architecture: Job queue](architecture.md#job-queue-and-worker-safeguards).
- **Keeping data formats in sync:** one Python codebase for API and worker; Pydantic models as the single source of truth; frontend types generated from the API. Details: [Architecture](architecture.md#keeping-data-formats-in-sync).
- **Login and access ("view both, change your own"):** each person has their own Supabase login, needed because the site holds health data. Both logins can **view** both profiles (the profile dropdown switches between them), but each person can only **change** their own data. Nobody else can see anything. **Sign-in is by email and password**; accounts are created by Amol in the Supabase dashboard (public sign-ups are off), because Supabase's free email service is too limited for magic links or email invites. Details: [Data model: Access rules](data-model.md#access-rules), [Architecture: Signing in](architecture.md#signing-in-and-calling-the-api).
- **Health data:**
  - Source is **Apple Health**.
  - Phase 1 (website): an **iOS Shortcuts automation** on each iPhone sends the data to the backend daily ([guide](apple-health-shortcut.md)). It authenticates with a per-person **connection token** created in Settings (only its hash is stored).
  - Phase 2 (app): the app reads Apple Health directly.
  - **Wearables:** none yet. The design must make them easy to add later; most sync into Apple Health, so they'd flow in through the same path.
  - **Other apps and devices:** each person ticks what they use in Settings; each one is then assessed, and Withings, Oura, Whoop and Polar have a direct connection (OAuth "Connect" button, encrypted access keys, new data fetched on app open into `health_samples`). See [data-sources.md](data-sources.md).
- **Languages:** **TypeScript** for the Expo frontend; **Python** for everything else (FastAPI backend on Vercel, worker, scripts). The frontend's data types are generated automatically from the Python API, so the two can't drift apart.
- **Folder structure:** `frontend/`, `backend/` (`core/`, `api/`, `worker/`, `tests/`), `supabase/migrations/`, `context/`. Details: [Architecture: Folder structure](architecture.md#folder-structure).
- **Look and feel:** modelled on leading health apps (Whoop, Oura). **Dark mode by default**, with a light mode toggle in the header; the choice is remembered per device. Near-black background (not pure black), one green accent for actions and progress, and green / amber / red reserved for health signals. All text colours meet WCAG AA contrast (4.5:1) in both themes. Details: [Conventions: Theme](conventions.md#theme).
- **External content:** exercise diagrams from a free exercise database (free-exercise-db or wger); muscle body map from an open-source component (e.g. react-native-body-highlighter); videos via the YouTube Data API; nutrients from USDA FoodData Central / Indian Food Composition Tables. Details in [Exercise Guide](pages/exercise-guide.md) and [Plan for Today](pages/plan-for-today.md).

### Privacy model

| Data | Read by | Goes to cloud LLM? |
|---|---|---|
| Health documents (lab reports, doctor's notes) | Local Ollama only | No; only confirmed facts do |
| Confirmed health facts | Cloud Qwen, when building plans | Yes |
| Food photos | Cloud Qwen vision (local Ollama backup) | Yes |
| Progress photos | **Open question**, see [Progress](pages/progress.md#open-question-progress-photo-analysis-local-vs-cloud-revisit-later) | Undecided |

### Data sources

Where each metric comes from with an iPhone only (no watch yet):

| Metric | Source today | With a watch later |
|---|---|---|
| Active minutes | Not recorded by the iPhone alone; count workouts logged in the app plus brisk-walking time | Recorded automatically |
| Sleep / time in bed | Apple Health, only if Sleep / Bedtime is set up; measures time in bed, not actual sleep | Real sleep tracking |
| Resting heart rate, HRV, VO₂ max | Not available | Available |
| Calories burned | Rough estimate from steps | Much more accurate |
| Body weight | Apple Health (smart scale or app), or entered on the [Workout Plan](pages/workout-plan.md) | Same |
| Workout streak | Workouts completed on [Plan for Today](pages/plan-for-today.md) | Same, plus watch workouts |
| Macro / micro targets | [Nutrition Plan](pages/nutrition-plan.md) | Same |
| Macros / micros eaten, calorie intake | Logged on [Plan for Today](pages/plan-for-today.md) | Same |
| Water intake | Quick-add buttons on [Plan for Today](pages/plan-for-today.md) | Same |
| Appointments, medications | [Personal Artifacts](pages/personal-artifacts.md); doses ticked off on [Plan for Today](pages/plan-for-today.md) | Same |

## Rules that apply to every page

- **Confirm before changing:** anything the LLM extracts or proposes (food photo analysis, health facts, plan rebalancing, travel plans) is shown for review and only applied after the person confirms.
- **Numbers from data, words from the LLM:** nutrients come from food databases and forecasts from calculations; the LLM identifies, explains and writes.
- **No diagnoses:** out-of-range values say "discuss with your doctor"; suggestions never override prescribed treatment.
- **Weight and calories are opt-in** everywhere, switched on in [Settings / Profile](pages/settings-profile.md).
- **No alerts without a next step:** every warning comes with "here's what to do".
- **Viewing the other person's profile is read-only:** logging buttons, uploads and plan changes are hidden or disabled.
- **Missing data is explained**, e.g. "Connect a wearable to track this", never a blank.

## Open questions

- **Progress photo analysis, local vs cloud** (revisit later). See [Progress](pages/progress.md#open-question-progress-photo-analysis-local-vs-cloud-revisit-later).

## Future enhancements

- **Always-on cloud worker (~$5/month, e.g. a small VPS).**
  - *What:* run the same Python worker on an always-on host to process queued cloud-LLM jobs (plan generation, food photos, video search, forecasts).
  - *Why:* Vercel functions have time limits and aren't suited to slow LLM calls, and without a cloud worker those jobs depend on the Mac being on. A cloud worker makes them run promptly regardless of the Mac, with no time limit.
  - *Why not now:* keeping the budget at $0; slow jobs waiting for the Mac is acceptable for the time being.
  - *Upgrade path:* no code changes; start the existing worker in cloud mode on the new host.

## Change log

- **2026-10-21:** M7 part 1 built: food database (USDA FoodData Central + Indian Nutrient Databank, `scripts/import_foods.py`), daily targets with reasons (calories from weight, height, age, sex, steps and the workout plan's training, adjusted for goals; protein 1.6 g/kg for muscle and fat-loss goals), weekly meal plans (rules size portions and work out every number; the LLM only picks dishes; Vercel first, then the worker), the Nutrition Plan page (targets vs planned with reasons, vitamins and minerals, meals by day, swaps, eating out with a preview, "Make a new plan", household grocery list) and a weigh-in prompt when none is saved. Made automatically on first open in a new week, after the workout plan. See [Nutrition Plan](pages/nutrition-plan.md#as-built-m7-part-1), [data model](data-model.md#nutrition), [roadmap](roadmap.md#m7--nutrition).
- **2026-10-21:** Plan for Today: set boxes start empty (no grey target hint that looked filled in); the target stays in the line under the exercise name. See [Plan for Today](pages/plan-for-today.md).
- **2026-10-21:** M6 part 2 built: Plan for Today workout card (log sets with targets, mark timed moves done, finish with an effort rating, streak, catch up a missed session); core lifts chosen in Settings and kept in every plan; other main exercises in 6-week blocks; progressive overload from what was lifted and how hard it felt; plan changes with preview (day off, extra or shorter session, vacation with or without training, cheat meal spread or as planned, medical pause with a gentle return, something else read by the LLM). Days already done and their progress are kept when a plan is replaced.
- **2026-10-21:** M6 part 1 (workout plans) built: weekly plans made when the app opens in a new week (rules shape the week, warm-ups and cool-downs; Groq picks the main exercises from a short checked list and explains the sessions; Mac worker backup; rules alone as the last resort); Workout Plan page with day cards, swaps, muscle coverage, new plan with preview, body weight; this week's exercises on the Exercise Guide; training experience in Settings. Groq's free tier limits output to about 1,000 tokens a minute, so the plan answer is compact.
- **2026-10-21:** Exercise Guide: **Is this the right video?** Yes confirms a video (no monthly refresh); No with a reason searches again straight away: the LLM turns all reasons into a better search and requirements, rejected videos are never chosen again, and every candidate is now rated for relevance as well as comment tone. Library search matches words in any order and, when nothing matches, shows the **5 closest matches** (pg_trgm) instead of an empty page; filters fold behind a Filters button. Table `video_feedback`; function `suggest_exercises`.
- **2026-10-21:** Faster guide and video preparation: the worker looks for jobs every 3 seconds (was 10) and runs up to 3 at once, the video job fetches comments in parallel, and the exercise page checks every 2 seconds (was 5). A new exercise now fills in about 5–8 seconds after opening (was 12–15).
- **2026-10-21:** M5 (exercise library and Exercise Guide) built: 876 exercises imported from free-exercise-db (images from the jsDelivr CDN, nothing stored); searchable library page and exercise page with start/end images, front/back body map, AI-written about, form cues and precautions, and a scored YouTube video. Guide and video are prepared by the Mac worker the first time an exercise is opened (not Vercel, because only the worker writes to the shared library). LLM client: Groq (cloud Qwen) with Ollama `qwen3:8b` as backup.
- **2026-10-21:** M4 (job queue and worker) built: `jobs` and `worker_heartbeats`, atomic claiming, retries with growing gaps, stuck-job recovery, heartbeat, Ollama check; job types registered in `backend/core/jobs/` with a `test_echo` job; "Vercel first, then queue" helper; worker as a launchd service; offline notice in the app and an ntfy alert sent by an hourly check inside Supabase (pg_cron). Ollama runs from its Mac app instead of a separate launchd service (no Homebrew needed).
- **2026-10-21:** Switching on the direct connectors (developer apps, first real connections, AI-terms check, Mac daily sync) parked until after M10: moved to [roadmap → After development](roadmap.md#after-development--switch-on-the-integrations). The connector code stays live and idle.
- **2026-10-20:** M3b (direct connectors) built: Withings, Oura, Whoop and Polar connect from Settings → Connected services with their own sign-in; keys encrypted by the API (`CONNECTOR_ENCRYPTION_KEY`) in `service_connections`; new data fetched on app open (every 3 hours at most) or with Sync now; new metrics (body composition, blood pressure, sleep stages and scores, readiness, recovery, strain); per-metric source preference and an AI-allowed flag per source; more choices under "Apps and devices you use". Waiting on the developer apps to test with real accounts. A **Refresh** button (↻) in the header fetches from all connected services straight away and reloads the page.
- **2026-10-20:** Assessed every service in [data-sources.md](data-sources.md): direct connectors are possible for Withings, Oura, Whoop and Polar; Strava (terms forbid view-both and AI), Garmin, Suunto, Coros (business-only), Fitbit (old API ends 2026-10-30) and the nutrition apps go through Apple Health or wait. Connectors design added (OAuth return to the website, encrypted keys, sync on app open then daily on the Mac) and milestone [M3b](roadmap.md#m3b--direct-connectors) added to the roadmap.
- **2026-10-20:** M3 (health data intake) built: `health_samples`, connection tokens and water logs; Shortcut endpoint that skips bad samples instead of rejecting the batch; Shortcut guide; water card with per-person target (a gallon ticks 75 Hard's water item); body weight in Settings; "Apps and devices you use" in Settings, with [data-sources.md](data-sources.md) to assess which services to connect directly. The planned `shortcuts/` folder was dropped: the guide lives in `context/`.
- **2026-10-20:** M2 (75 Hard) built: checklist, day counter, restart rule with yesterday open until noon, completion and stop; anyone can start a challenge; the link shows on the other person's profile only while they're doing one. Resets are calculated, not stored, so nothing runs at midnight.
- **2026-10-20:** M1 (Foundation) complete. Added [setup.md](setup.md).
- **2026-10-20:** Website and API deployed to Vercel as two projects (root folders `frontend` and `backend`), auto-deploying from `main`. The Supabase secret key is not uploaded (the API doesn't need it yet). The website now refuses an API address without `https://` and explains non-JSON replies.
- **2026-10-20:** Settings / Profile page and 3-step first-sign-in welcome built. Goals are now chosen from a list plus notes; body weight moves to M3 as dated measurements.
- **2026-10-20:** Sign-in built (email and password via Supabase Auth). First API endpoint `GET /api/me/profiles` uses the caller's own token so database access rules apply. Frontend types now generated from the API. The 75 Hard link shows for everyone until M2.
- **2026-10-20:** First tables built: households, profiles, preferences and display settings, with "view both, change your own" access rules verified by integration tests. Decided: accounts by invitation only (public sign-ups off).
- **2026-10-20:** Supabase project created and connected; env templates added; one named secret key per component (`backend-api` now, `mac-worker` later).
- **2026-10-20:** Health-app look and feel: dark mode by default with a light mode toggle (saved per device), green accent, colours checked for WCAG AA contrast.
- **2026-10-20:** Frontend skeleton built: Expo SDK 58 website with Expo Router, 9 placeholder pages, navigation bar (75 Hard shown only for Amol) and profile dropdown with placeholder profiles; `vercel.json` for deployment. Routes live in `frontend/src/app/` (Expo's current default).
- **2026-10-20:** Backend skeleton built: uv project on Python 3.12, FastAPI with a `/api/health` endpoint, ruff and pytest.
- **2026-10-20:** Development workflow (10 steps per roadmap item) added to [conventions.md](conventions.md#development-workflow).
- **2026-10-20:** Access decided: "view both, change your own". Both logins can see both profiles; each can only change their own data.
- **2026-10-20:** Added [architecture.md](architecture.md), [data-model.md](data-model.md) (draft), [conventions.md](conventions.md), [roadmap.md](roadmap.md) and the root `CLAUDE.md`. Technical detail moved from this hub into architecture.md. Found a conflict between per-login privacy and the profile dropdown (open question).
- **2026-10-20:** Project folder structure created (empty folders with `.gitkeep`) and `.gitignore` added for secrets, Python, Node/Expo, Vercel and macOS files.
- **2026-10-20:** Job queue, Vercel-first quick jobs with Mac fallback, Mac worker safeguards, data-format sync approach, and first sign-in onboarding confirmed.
- **2026-10-20:** Languages decided (TypeScript frontend, Python everywhere else) and folder structure recorded.
- **2026-10-20:** Project defined: all 9 pages specified; stack chosen (Expo website, Vercel, Supabase, Qwen + Ollama, iOS Shortcut for Apple Health). Context split into this hub plus one file per page. Frontend and backend kept separate (Vercel for website + backend API, Supabase for data); local worker fetches jobs instead of exposing the Mac. No paid cloud worker for now; recorded as a future enhancement.
