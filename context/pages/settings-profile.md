# Settings / Profile Page

← [Hub: skills.md](../skills.md) · Status: **Built** (M1)

**Purpose:** each person's details and settings. Opened from the profile dropdown at the top of every page. When viewing the other person's profile, this page is read-only ("view both, change your own").

## What it holds

- **Personal details**, which are the inputs the LLM uses to build plans (fields below).
- **Switches for the opt-in [Summary](summary.md) cards:** body weight, calorie intake, calories burned. Off by default. The same switches apply to those charts on [Progress](progress.md).

## Personal details

Not collected up front; each person fills them in here once the app exists.

- **Both:** date of birth, sex, height, goals (+ notes), goal metric, injuries / limitations. (Weight comes in M3.)
  - For the [Workout Plan](workout-plan.md): equipment, available days, time per session, training location (home / gym / travel).
  - For the [Nutrition Plan](nutrition-plan.md): diet type (vegetarian / eggetarian / non-vegetarian), cuisine preferences, allergies / dislikes, meals per day, cooking time.
- **75 Hard:** the current day is asked on the [75 Hard](75-hard.md) page when starting, not here.

## Layout

Sections, each saved on its own (saving one never touches unsaved changes in another):

1. **About you:** name, date of birth, sex, height, goals (choose from a list) plus goal notes, the one metric you care about most, injuries or limitations.
2. **Training:** days you can train, minutes per session, where you train, training experience (beginner / intermediate / advanced; optional, beginner if not set), equipment, **core lifts** (up to 8 compound lifts kept in every plan for progressive overload; searchable, only lifts doable with the saved equipment are offered).
3. **Food:** diet type, meals per day, cooking time, cuisines, allergies, foods you dislike (comma-separated).
4. **Body weight:** latest weight and date (manual or Apple Health), plus "Today's weight (kg)" to log one. Logging again the same day corrects it.
5. **Water:** daily target in ml (default 3000; 75 Hard's gallon is 3785).
6. **Summary cards:** switches for weight, calories eaten and calories burned (off by default).
7. **Apps and devices you use** (optional): tick the health apps and devices you use, grouped (phone and watch, rings and bands, scales and health devices, apps), plus "Anything else?". Under the ticked ones, a note says how each connects today (through the Shortcut, directly, via Apple Health, or not yet). Used to decide which connections to build: [data-sources.md](../data-sources.md).
8. **Connected services:** Withings, Oura, Whoop and Polar, each with what it sends and its status (not connected / connected and last sync / needs connecting again). On your own profile: **Connect** (opens the service's sign-in; it returns to `/connect/<service>`, which finishes connecting and fetches the last 30 days), **Sync now** (fetches just that service), **Disconnect** (asks to confirm; data already fetched stays). On the other person's profile it's view-only. A service whose developer app isn't set up shows "Not set up yet". Design: [data-sources.md](../data-sources.md#connectors-design).
9. **Apple Health** (own profile only): create a connection token for the iOS Shortcut (shown once, with Copy buttons for the token and the address), see when data last arrived, make a new token (stops the old one) or disconnect. Guide: [apple-health-shortcut.md](../apple-health-shortcut.md).
10. **Mac worker:** online, or offline since when; whether the local AI (Ollama) is running; jobs waiting. On your own profile: **Send test job** (queued for the Mac) and **Quick test (Vercel first)**, with the job's progress and a **Retry** button if it fails. When the worker is offline and jobs are waiting, a notice also shows on every page.

When viewing the other person's profile, every field is disabled and there are no Save buttons.

## First sign-in

- Until a person has finished the welcome, the app shows a **3-step welcome** instead of the pages: About you → Training → Food, with a progress bar and Back / Next / Finish.
- Each step is saved as you go, so closing the page halfway loses nothing.
- **Required** (marked *): date of birth, sex, height, at least one goal, goal metric, at least one training day, minutes per session, location, diet type, meals per day. Everything else is optional.
- The backend refuses to mark the welcome as done until the required fields are filled.
- **Body weight is not asked here:** it's recorded as dated measurements from M3 (health data intake).

## Related pages

- [Workout Plan](workout-plan.md) and [Nutrition Plan](nutrition-plan.md): use these details as plan inputs.
- [Summary](summary.md) and [Progress](progress.md): obey the opt-in switches.
- [Personal Artifacts](personal-artifacts.md): the other source of plan inputs (health facts).
- Data: [Profiles and settings](../data-model.md#profiles-and-settings).
