# Personal Workout Strategy — Hub

_Last updated: 2026-10-20_

This is the **hub** for the project's context files. It holds the app's structure, technical decisions and rules that apply to every page. Each page has its own file in [pages/](pages/), linked below; every file links back here and to its related pages.

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
| 2 | [Plan for Today](pages/plan-for-today.md) | Today's workout and meals, plus all daily logging (meals, water, medications) | Defined |
| 3 | [Workout Plan](pages/workout-plan.md) | Weekly customised workout plan the person can change | Defined |
| 4 | [Nutrition Plan](pages/nutrition-plan.md) | Weekly meal plan with macro / micro targets the person can change | Defined |
| 5 | [Progress](pages/progress.md) | Long-term trends, insights, forecasts, what-if simulator, disruption planning | Defined (1 open question) |
| 6 | [75 Hard](pages/75-hard.md) (Amol only) | Simple daily 75 Hard checklist and day counter | Defined |
| 7 | [Exercise Guide](pages/exercise-guide.md) | Diagram, body map, form cues, precautions and best short video for each exercise | Defined |
| 8 | [Personal Artifacts](pages/personal-artifacts.md) | Upload health documents; confirmed facts adjust the plans | Defined |
| 9 | [Settings / Profile](pages/settings-profile.md) | Personal details (plan inputs) and opt-in card switches | Defined |

**Profile switcher:** a simple dropdown at the top of every page switches between profiles and opens [Settings / Profile](pages/settings-profile.md).

### How the pages connect

- [Settings / Profile](pages/settings-profile.md) and [Personal Artifacts](pages/personal-artifacts.md) are the **inputs** to the LLM plans.
- [Workout Plan](pages/workout-plan.md) and [Nutrition Plan](pages/nutrition-plan.md) are the **weekly plans**; [Plan for Today](pages/plan-for-today.md) shows today's slice and is where everything is **logged**.
- [Exercise Guide](pages/exercise-guide.md) explains every exercise in the plan.
- [Summary](pages/summary.md) shows **now**; [Progress](pages/progress.md) shows **history and future**.
- [75 Hard](pages/75-hard.md) stands alone as Amol's checklist.

## Technical decisions

- **Phase 1 is a website.** It becomes an iPhone app once the features are settled. Publishing to Apple ($99/year developer account) is on hold until then.
- **Framework:** Expo, published as a website, so the same code later builds the iPhone app.
- **Code layout:** app logic (plan generation, LLM calls, data storage) lives in the backend, not the screens, so moving to the app later mostly reuses code.
- **Hosting (all free tiers):**
  - Website on **Vercel**.
  - Database, login and file storage on **Supabase** (free plan; it pauses after about a week without use).
- **LLM:**
  - **Qwen** through a free cloud API (e.g. OpenRouter, Groq) for building plans and analysing food photos.
  - **Ollama** on a local machine as a backup, and as the only model that reads health documents (see [Privacy model](#privacy-model)).
- **Split of responsibilities:** the frontend and the backend / agentic logic (LLM calls, plan generation, photo analysis) are kept separate. **Vercel** hosts the website and the backend API; **Supabase** holds the database, login and file storage.
- **Local worker:** a program on the local Mac that fetches pending jobs (e.g. documents to read) from Supabase, processes them with Ollama, and writes the results back. The Mac is never exposed to the internet, so no tunnel is needed.
- **Job queue:** all slow or LLM work goes through a job queue in the database.
  - **Quick cloud-LLM jobs first try on Vercel** (e.g. food photos via Groq, usually a few seconds). If a job doesn't finish within Vercel's time limit, it falls back to the queue.
  - **No paid cloud worker for now** ($0 budget): queued jobs are processed by the Mac worker, so slow jobs wait until the Mac is on. See [Future enhancements](#future-enhancements).
- **Mac worker safeguards** (the Mac is a single point of failure):
  1. Every job has a status (`pending → processing → done / failed`), an attempt count and the last error. Jobs are claimed so two workers can't take the same one; jobs stuck in "processing" too long return to pending.
  2. Retries with growing gaps; after the last attempt the job is marked failed, the error is shown in the app, and there's a **Retry** button.
  3. **Heartbeat:** the worker records that it's alive every minute; if it stops, the app shows e.g. "Document reader offline since 9:40 pm. Your report is queued."
  4. The worker and Ollama run as macOS background services (launchd): start at login, restart on crash; the worker checks Ollama responds before taking a job.
  5. **Alert:** one notification (email or a free push service like ntfy) if the worker has been offline for ~12 hours and jobs are waiting.
  6. **"Process in cloud now"** button per document: an explicit, one-off opt-out of the local-only privacy rule.
- **Keeping data formats in sync:** one Python codebase for the API and the worker; Pydantic models are the single source of truth; the frontend's TypeScript types are generated from the API and a check fails if they're out of date; the frontend uses only the API (plus Supabase login and file upload).
- **Login:** Supabase login, because the site holds health data. Each person's data is visible only to their own login.
- **Health data:**
  - Source is **Apple Health**.
  - Phase 1 (website): an **iOS Shortcuts automation** on each iPhone sends the data to the backend daily.
  - Phase 2 (app): the app reads Apple Health directly.
  - **Wearables:** none yet. The design must make them easy to add later; most sync into Apple Health, so they'd flow in through the same path.
- **Languages:** **TypeScript** for the Expo frontend; **Python** for everything else (FastAPI backend on Vercel, worker, scripts). The frontend's data types are generated automatically from the Python API, so the two can't drift apart.
- **Folder structure:**

  ```
  personal_workout_strategy/
  ├── context/            # Spec docs (this hub + pages/)
  ├── frontend/           # Expo website (TypeScript); types generated from the API
  ├── backend/            # One Python codebase
  │   ├── core/           # Shared: data models (Pydantic), database access, Qwen/Ollama client, prompts, nutrition lookup, job queue
  │   ├── api/            # FastAPI on Vercel: quick requests and adding jobs to the queue
  │   ├── worker/         # Job runner (on the Mac for now; cloud mode later, see Future enhancements)
  │   └── tests/
  ├── supabase/
  │   └── migrations/     # Database tables and access rules
  └── shortcuts/          # iOS Shortcut instructions + data format
  ```

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

- **2026-10-20:** Project folder structure created (empty folders with `.gitkeep`) and `.gitignore` added for secrets, Python, Node/Expo, Vercel and macOS files.
- **2026-10-20:** Job queue, Vercel-first quick jobs with Mac fallback, Mac worker safeguards, data-format sync approach, and first sign-in onboarding confirmed.
- **2026-10-20:** Languages decided (TypeScript frontend, Python everywhere else) and folder structure recorded.
- **2026-10-20:** Project defined: all 9 pages specified; stack chosen (Expo website, Vercel, Supabase, Qwen + Ollama, iOS Shortcut for Apple Health). Context split into this hub plus one file per page. Frontend and backend kept separate (Vercel for website + backend API, Supabase for data); local worker fetches jobs instead of exposing the Mac. No paid cloud worker for now; recorded as a future enhancement.
