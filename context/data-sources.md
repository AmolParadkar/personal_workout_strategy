# Data Sources

← [Hub: skills.md](skills.md) · Related: [Apple Health Shortcut](apple-health-shortcut.md) · [Data model](data-model.md#health-data) · [Settings / Profile](pages/settings-profile.md) · [Roadmap](roadmap.md)

Which health apps and devices can feed the app, and how. People tick what they use in **Settings → Apps and devices you use** (`profiles.data_sources`); this file is where each one is assessed and decided.

## The plan

1. **Collect (built, M3):** each person ticks the apps and devices they use. The Settings page shows how each one connects today.
2. **Assess (next):** for every service someone actually uses, check the four questions below and record the answer here.
3. **Connect (per approved service):** a **Connect** button in Settings sends the person to the service's own login page (OAuth), they approve access, and the service's access key is stored in a backend-only table (never readable by the website). A daily scheduled job fetches new data into `health_samples` with `source` set to the service (e.g. `strava`), so Summary, Progress and plans use it with no page changes. **Disconnect** deletes the key.

### Questions for each service

- **Personal use allowed?** Can an individual register an app with its API, or is it business-only / approval-based?
- **Terms:** may the data be shown to the other household member ("view both") and used by the LLM when building plans?
- **Extra data:** what does it have that Apple Health doesn't already give us through the Shortcut?
- **Simpler route:** can it sync into Apple Health instead, so the Shortcut covers it with nothing to build?

## Current status

Route shown in Settings: **Shortcut** = arrives through the Apple Health Shortcut; **Via Apple Health** = can usually share with Apple Health (turned on in its own app), then the Shortcut picks up the types it reads; **Not yet** = no route yet.

| Key | Service | Route today | Direct connection: what's known | Decision |
|---|---|---|---|---|
| `iphone_health` | iPhone (Apple Health) | Shortcut | No web API exists (Health data is only readable on the device; iCloud copies are end-to-end encrypted). Phase 2 iPhone app reads it directly | Shortcut now, iPhone app later |
| `apple_watch` | Apple Watch | Shortcut | Same as iPhone | Shortcut |
| `garmin` | Garmin | Via Apple Health | Garmin's Health API requires applying to Garmin's developer programme (aimed at businesses) | To assess |
| `fitbit` | Fitbit | Not yet | Fitbit Web API (OAuth, personal apps allowed) | To assess |
| `samsung_watch` | Samsung Galaxy Watch | Not yet | Mostly Android-side (Samsung Health / Health Connect); limited for iPhone users | To assess |
| `oura` | Oura | Via Apple Health | Oura API (OAuth / personal token) | To assess |
| `whoop` | Whoop | Via Apple Health | Whoop developer API (OAuth) | To assess |
| `withings` | Withings | Via Apple Health | Withings Public API (OAuth) | To assess |
| `other_scale` | Other smart scale | Not yet | Depends on the brand | To assess |
| `bp_monitor` | Blood pressure monitor | Not yet | Depends on the brand; many write to Apple Health | To assess |
| `glucose_monitor` | Glucose monitor | Not yet | Depends on the brand (e.g. CGMs); many write glucose to Apple Health | To assess |
| `strava` | Strava | Via Apple Health | Strava API (OAuth, personal apps allowed); terms tightened in late 2024 around showing data to other users and AI use: **check carefully** before building | To assess |
| `nike_run_club` | Nike Run Club | Via Apple Health | No public API known | To assess |
| `myfitnesspal` | MyFitnessPal | Via Apple Health | API not open to individuals | To assess |
| `cronometer` | Cronometer | Via Apple Health | No general public API known | To assess |
| `healthifyme` | HealthifyMe | Not yet | Not known | To assess |

Notes:

- "What's known" is a starting point, not a verified assessment: each service's current API access and terms must be checked at assessment time.
- The Shortcut currently reads steps, active energy, walking + running distance, weight, resting heart rate and sleep ([guide](apple-health-shortcut.md)). Data a device writes to Apple Health in other types (e.g. blood pressure, glucose, nutrition) needs extra Shortcut steps and new metrics before it arrives.

## Related

- [Apple Health Shortcut](apple-health-shortcut.md): the route most sources use today.
- [Data model: Health data](data-model.md#health-data): where all sources' data lands.
- [Settings / Profile](pages/settings-profile.md): where people tick what they use.
- [Roadmap](roadmap.md): connections get added there once decided.
