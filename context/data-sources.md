# Data Sources

← [Hub: skills.md](skills.md) · Related: [Apple Health Shortcut](apple-health-shortcut.md) · [Data model](data-model.md#health-data) · [Settings / Profile](pages/settings-profile.md) · [Roadmap](roadmap.md)

Which health apps and devices can feed the app, and how. People tick what they use in **Settings → Apps and devices you use** (`profiles.data_sources`); this file is where each one is assessed and decided.

## The plan

1. **Collect (built, M3):** each person ticks the apps and devices they use. The Settings page shows how each one connects today.
2. **Assess (done 2026-10-20):** for every service someone actually uses, check the four questions below and record the answer here.
3. **Connect (built, M3b):** a **Connect** button in Settings sends the person to the service's own sign-in page (OAuth); new data then lands in `health_samples` with `source` set to the service, so Summary, Progress and plans use it with no page changes. See [Connectors design](#connectors-design).

### Questions for each service

- **Personal use allowed?** Can an individual register an app with its API, or is it business-only / approval-based?
- **Terms:** may the data be shown to the other household member ("view both") and used by the LLM when building plans?
- **Extra data:** what does it have that Apple Health doesn't already give us through the Shortcut?
- **Simpler route:** can it sync into Apple Health instead, so the Shortcut covers it with nothing to build?

## Current status

Route shown in Settings: **Shortcut** = arrives through the Apple Health Shortcut; **Direct** = connect it in Settings → Connected services; **Via Apple Health** = can usually share with Apple Health (turned on in its own app), then the Shortcut picks up the types it reads; **Not yet** = no route yet.

First assessment: 2026-10-20, from the services' docs and developer reports (sources below). **Re-check each service's current terms on its developer site before building its connector.**

| Key | Service | Route today | Direct connection (2026-10-20) | Decision |
|---|---|---|---|---|
| `iphone_health` | iPhone (Apple Health) | Shortcut | No web API exists (Health data is only readable on the device; iCloud copies are end-to-end encrypted). Phase 2 iPhone app reads it directly | Shortcut now, iPhone app later |
| `apple_watch` | Apple Watch | Shortcut | Same as iPhone | Shortcut |
| `withings` | Withings | **Direct** (or via Apple Health) | Public API: free, self-serve developer account, OAuth, no approval (free tier up to 1,000 users). Weight, body fat, muscle mass, blood pressure, sleep, activity | **Built** (M3b) |
| `oura` | Oura | **Direct** (or via Apple Health) | API v2, OAuth only (personal tokens ended Dec 2025). New apps work for ~10 users without approval. Agreement from June 2026 reportedly restricts AI processing: confirm before LLM use | **Built** (M3b) |
| `whoop` | Whoop | **Direct** (or via Apple Health) | Developer API, OAuth; needs a Whoop membership; development mode covers ~10 members with no approval. Recovery, strain, sleep, workouts | **Built** (M3b) |
| `fitbit` | Fitbit | Not yet | Old Fitbit Web API switches off 2026-10-30; replaced by the Google Health API, which needs Google OAuth app verification (restricted health data). Personal use unclear | **Wait**: reassess once the Google Health API's personal-use rules are clear |
| `strava` | Strava | Via Apple Health | OAuth works, but since Nov 2024 the terms forbid showing a person's data to anyone else (breaks "view both") and using it in AI (breaks plan building); June 2026 adds subscription requirements | **No**: use Apple Health (Strava workouts sync there) |
| `garmin` | Garmin | Via Apple Health | Business-only programme; personal applications are rejected, and new applications are reported paused | **No**: Garmin Connect → Apple Health |
| `samsung_watch` | Samsung Galaxy Watch | Not yet | Samsung Health has no web API; data is Android-only (Health Connect) | **No** route for iPhone users |
| `nike_run_club` | Nike Run Club | Via Apple Health | No public API | **No**: Apple Health |
| `myfitnesspal` | MyFitnessPal | Via Apple Health | API closed to individuals | **No**: Apple Health (needs nutrition metrics in the Shortcut) |
| `cronometer` | Cronometer | Via Apple Health | No general public API | **No**: Apple Health (as above) |
| `healthifyme` | HealthifyMe | Not yet | No public API | **No** |
| `other_scale` | Other smart scale | Not yet | Depends on the brand | Per brand: most write to Apple Health |
| `bp_monitor` | Blood pressure monitor | Not yet | Depends on the brand | Per brand: most write to Apple Health (needs a BP metric in the Shortcut) |
| `glucose_monitor` | Glucose monitor | Not yet | Depends on the brand (CGMs) | Per brand: most write to Apple Health (needs a glucose metric in the Shortcut) |
| `polar` | Polar | **Direct** (or via Apple Health) | AccessLink API: self-serve client at admin.polaraccesslink.com, OAuth. Steps, activity, sleep, heart rate, workouts | **Built** (M3b) |
| `suunto` | Suunto | Via Apple Health | API Zone is for companies only; "no API access for personal use" | **No**: Apple Health |
| `coros` | Coros | Via Apple Health | Partner-only API, nothing public found | **No**: Apple Health |
| `amazfit` | Amazfit / Zepp | Via Apple Health | No public developer API (only paid aggregators) | **No**: Apple Health |
| `dexcom` | Dexcom CGM | Via Apple Health | Developer API with OAuth; sandbox is open, real data needs Dexcom's approval | **Later**: apply only if glucose matters |

In short: **direct connectors are possible for Withings, Oura, Whoop and Polar**. Everything else either can't be connected (no API, business-only, or terms that forbid "view both" and AI use) or already reaches us through Apple Health.

## Connectors design

How a direct connection works, from the person's side and ours. Built in milestone [M3b](roadmap.md#m3b--direct-connectors) (2026-10-20). Code: `backend/core/connectors/` (one file per service), `backend/core/connections.py`, Settings → Connected services, and the `/connect/<service>` page.

**Not yet checked against the real services:** each connector follows its API's documentation and is tested with replies shaped like it, but the first real connection may show differences. Check each one when its developer app is set up.

**One-time setup (Amol):** register one developer app per service (Withings, Oura, Whoop, Polar), with the website's `/connect/<service>` page as the return address (live and `localhost:8081`). Each gives a client ID and client secret: they go in `backend/.env` and the API's Vercel settings, never in chat or git. Plus one `CONNECTOR_ENCRYPTION_KEY` (random) in the same places.

**Connecting (each person):**

1. Settings → Apps and devices you use → **Connect** next to a ticked service.
2. The API builds the service's sign-in address with a signed, 10-minute `state` (who is connecting, which service) and the website sends the person there.
3. They sign in on the service's own page and tap Allow.
4. The service sends them back to the website's `/connect/<service>` page with a one-time code. The page passes the code and `state` to the API **with the person's own sign-in**, so the usual access rules apply and no extra Supabase key is needed.
5. The API checks `state`, swaps the code for access and refresh keys, **encrypts them** and saves them in `service_connections`. The first fetch brings in the last 30 days.

**Fetching new data:**

- **On app open (now):** when someone opens the app, the website asks the API to sync *their own* connections if the last sync was over 3 hours ago. The API refreshes expired keys (storing the new refresh key each time: Oura's are single-use), fetches everything since the last sync, and upserts it into `health_samples` with `source` set to the service. **Refresh** (the ↻ button in the header, on every page) does the same for all connections straight away, ignoring the 3 hours, then reloads the page. **Sync now** on a service in Settings fetches just that one. Apple Health data can't be pulled: it arrives when the Shortcut runs.
- **Daily on the Mac (after [M4](roadmap.md#m4--job-queue-and-worker)):** the worker syncs both people's connections every morning, so data arrives even when nobody opens the app.

**Keeping the keys safe:** `service_connections` stores the keys encrypted with `CONNECTOR_ENCRYPTION_KEY`, which only the API has. The website can read a connection's status (connected, last sync, last error) but not the key columns; the API gets the encrypted keys through a function that only returns the caller's own. **Disconnect** deletes the row (and revokes access at the service where it allows it).

**Same data from two places:** steps might arrive from both Apple Health and Oura. Every source is kept; pages pick one per metric using a preference order: the specialist device first (weight: Withings; sleep, HRV, readiness/recovery: Oura or Whoop; steps: Apple Health, which merges phone and watch), then anything else.

**AI use:** each source has an "AI allowed" flag (`AI_ALLOWED` in `backend/core/connectors/__init__.py`). All four services start as **not allowed** until their terms on AI processing are checked; until then, plans use their data only through Apple Health.

**What each one fetches:**

| Service | Metrics |
|---|---|
| Withings | weight, body fat, muscle mass, blood pressure (latest reading per day); steps, active energy, distance; sleep (bedtime, wake time, in bed, asleep, deep / REM / light, sleep score) |
| Oura | steps, active energy; readiness score; sleep score; main sleep (times, stages, HRV, lowest heart rate as resting HR) |
| Whoop | recovery score, resting HR, HRV (dated to the morning of the sleep); strain and steps per day; main sleep (naps ignored) |
| Polar | steps, active energy, distance; sleep (times, stages, sleep score); overnight HRV. Only the last 28 days are available, and its access key lasts about a year with no refresh: reconnect when asked |

Whoop's body weight is a typed-in profile value, so it isn't fetched.

## Setting up a service's developer app (Amol, once)

Each service needs a developer app before anyone can connect it. Do it for the services you'll use. Menu names on the services' sites may differ slightly.

1. **Make the encryption key once:** in `backend/`, run the command in `backend/.env.example` and put the result in `backend/.env` and the API's Vercel project as `CONNECTOR_ENCRYPTION_KEY`. Don't change it later (everyone would have to reconnect).
2. **Register the app** on the service's developer site, signed in with your normal account:
   - **Withings:** [developer.withings.com](https://developer.withings.com) → Dashboard → create an application of type *Public API integration* (Withings public cloud).
   - **Oura:** [cloud.ouraring.com/oauth/applications](https://cloud.ouraring.com/oauth/applications) → New application. Tick the scopes *daily*, *heartrate*, *personal*.
   - **Whoop:** [developer-dashboard.whoop.com](https://developer-dashboard.whoop.com) → create an app. Tick *read:recovery*, *read:cycles*, *read:sleep* (offline access is asked for automatically).
   - **Polar:** [admin.polaraccesslink.com](https://admin.polaraccesslink.com) → create a client. Polar may allow only one return address: use the live one.
3. **Return addresses** (called redirect or callback URLs): `https://personalworkoutstrategy-frontend.vercel.app/connect/<service>` and, for testing on your Mac, `http://localhost:8081/connect/<service>` (e.g. `/connect/oura`). They must match exactly.
4. **Copy the client ID and secret** into `backend/.env` and the API's Vercel project as `<SERVICE>_CLIENT_ID` and `<SERVICE>_CLIENT_SECRET` (e.g. `OURA_CLIENT_ID`). Never paste the secret into chat.
5. **Redeploy the API** on Vercel. The service's **Connect** button then works in Settings.

New apps on Oura and Whoop work for up to about 10 people without the service's approval, which is enough for the household.

Sources: [Strava API agreement update](https://press.strava.com/articles/updates-to-stravas-api-agreement) · [Strava: how data appears in 3rd-party apps](https://support.strava.com/en-us/articles/15401608-api-agreement-update-how-data-appears-on-3rd-party-apps) · [Google Health API migration (Fitbit)](https://developers.google.com/health/migration) · [Oura API v2 docs](https://cloud.ouraring.com/v2/docs) · [Whoop OAuth docs](https://developer.whoop.com/docs/developing/oauth) · [Withings API reference](https://developer.withings.com/api-reference/) · [Garmin Health API](https://developer.garmin.com/gc-developer-program/health-api/) · [Garmin programme pause (Terra)](https://tryterra.co/blog/garmin-connect-developer-program-pause)

Notes:
- The Shortcut currently reads steps, active energy, walking + running distance, weight, resting heart rate and sleep ([guide](apple-health-shortcut.md)). Data a device writes to Apple Health in other types (e.g. blood pressure, glucose, nutrition) needs extra Shortcut steps and new metrics before it arrives.

## Related

- [Apple Health Shortcut](apple-health-shortcut.md): the route most sources use today.
- [Data model: Health data](data-model.md#health-data): where all sources' data lands.
- [Settings / Profile](pages/settings-profile.md): where people tick what they use.
- [Roadmap](roadmap.md): connections get added there once decided.
