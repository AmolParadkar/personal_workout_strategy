# Settings / Profile Page

← [Hub: skills.md](../skills.md) · Status: **Defined**

**Purpose:** each person's details and settings. Opened from the profile dropdown at the top of every page. When viewing the other person's profile, this page is read-only ("view both, change your own").

## What it holds

- **Personal details**, which are the inputs the LLM uses to build plans (fields below).
- **Switches for the opt-in [Summary](summary.md) cards:** body weight, calorie intake, calories burned. Off by default. The same switches apply to those charts on [Progress](progress.md).

## Personal details

Not collected up front; each person fills them in here once the app exists.

- **Both:** age, height, weight, goals, injuries / limitations.
  - For the [Workout Plan](workout-plan.md): equipment, available days, time per session, training location (home / gym / travel).
  - For the [Nutrition Plan](nutrition-plan.md): diet type (vegetarian / eggetarian / non-vegetarian), cuisine preferences, allergies / dislikes, meals per day, cooking time.
- **Amol only:** 75 Hard current day (asked on the [75 Hard](75-hard.md) page).

## First sign-in

- On first sign-in, the app asks for these details before generating any plans, so the LLM never builds a plan from a blank profile.

## Related pages

- [Workout Plan](workout-plan.md) and [Nutrition Plan](nutrition-plan.md): use these details as plan inputs.
- [Summary](summary.md) and [Progress](progress.md): obey the opt-in switches.
- [Personal Artifacts](personal-artifacts.md): the other source of plan inputs (health facts).
- Data: [Profiles and settings](../data-model.md#profiles-and-settings).
