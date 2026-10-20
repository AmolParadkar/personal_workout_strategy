# Summary Page

← [Hub: skills.md](../skills.md) · Status: **Defined**

**Purpose:** "How am I doing right now?" A **read-only dashboard** for the selected person. There are no user inputs on this page; all logging happens on [Plan for Today](plan-for-today.md) and all settings on [Settings / Profile](settings-profile.md).

## Cards

**Default cards (on for everyone):**

| Card | What it shows |
|---|---|
| **Activity** | Active minutes per week against a target. WHO guideline: 150 moderate minutes per week. |
| **Sleep / time in bed** | Average duration, plus how consistent bedtime and wake time are. Consistency often matters more than the total. |
| **Resting heart rate** | Trend against the person's own 30-day baseline. An early signal of illness, overtraining or stress. |
| **One goal metric** | Whatever the person said they care about, e.g. weight, VO₂ max or HRV. |
| **Workout day streak** | Number of consecutive days with a completed workout (completed on [Plan for Today](plan-for-today.md)). |
| **Macros and micros** | Daily targets (from the [Nutrition Plan](nutrition-plan.md)) against what was actually eaten. |
| **Water intake** | Daily water intake against a target. |

**Opt-in cards (off by default; switched on in [Settings / Profile](settings-profile.md)):**

| Card | What it shows |
|---|---|
| **Body weight** | Current weight and its change over the last week. |
| **Calorie intake** | Calories eaten per day. |
| **Calories burned** | Average calories burned per day. |

**Condition-driven cards (only when relevant):**

- **Blood pressure, glucose / HbA1c, or lipids**, for people with those conditions or risk factors. These switch on automatically from confirmed facts on [Personal Artifacts](personal-artifacts.md).
- **Medication adherence:** % of doses taken (doses are ticked off on [Plan for Today](plan-for-today.md)).

**Action items (often more useful than any metric):**

- Upcoming appointments.
- Screenings due.
- Overdue lab tests, e.g. worked out from the date of the last report on [Personal Artifacts](personal-artifacts.md).
- Upcoming planned disruptions (e.g. a vacation), added on [Progress](progress.md).

## How each metric is shown

Every card has:

1. **The current value.**
2. **A 7- or 30-day trend arrow** (e.g. for weight, calorie intake, calories burned).
3. **A comparison** to the person's baseline or goal.
4. **A one-line "so what"** explaining what the number means. Without context, a number is just decoration.

Tapping a card opens that metric's full chart on [Progress](progress.md).

## Rules

- **No full charts here**; full charts live on [Progress](progress.md).
- **No unexplained composite "health score".** Only use one if it's clear exactly what moves it.
- **Weight and calories are opt-in**, never default headline metrics (risk for anyone with disordered eating).
- **No red alerts without a next step.** Every warning comes with "here's what to do".
- **Missing data:** a card without data (e.g. no wearable) shows "Connect a wearable to track this" instead of a blank.

See also the app-wide rules in the [hub](../skills.md#rules-that-apply-to-every-page).

## Where the data comes from

See [Data sources](../skills.md#data-sources) in the hub.

## Related pages

- [Plan for Today](plan-for-today.md): where workouts, meals, water and medications are logged.
- [Progress](progress.md): full charts behind each card.
- [Settings / Profile](settings-profile.md): opt-in card switches.
- [Personal Artifacts](personal-artifacts.md): turns on condition-driven cards and action items.
- [Nutrition Plan](nutrition-plan.md): source of the macro / micro targets.
- Data: [Health data](../data-model.md#health-data), [Health records](../data-model.md#health-records), [Profiles and settings](../data-model.md#profiles-and-settings).
