# Progress Page

← [Hub: skills.md](../skills.md) · Status: **Defined** (one open question)

**Purpose:** "Where have I come from, and where am I heading?" Long-term trends and insights, forecasts, a what-if simulator, and disruption planning.

## How it differs from the Summary

| | [Summary](summary.md) | Progress |
|---|---|---|
| Question it answers | "How am I doing right now?" | "Where have I come from, and where am I heading?" |
| Time span | Today, this week, 7/30-day arrows | Months: full history plus forecast |
| Depth | Glanceable cards, one-line "so what" | Full charts, insights, explanations |
| Inputs | None (read-only) | Only for what-if scenarios and planned disruptions |
| Future | No | Forecasts and what-if simulations |

- Each Summary card links to its full chart here.
- Summary shows no full charts; Progress shows no "today" statuses.

## Trends and insights over time

Trend lines and written insights for:

- **Blood work:** markers from lab reports on [Personal Artifacts](personal-artifacts.md) (e.g. haemoglobin, vitamin D, lipids), against normal ranges.
- **Body composition:** e.g. weight, body fat %, muscle mass, from uploaded reports (DEXA / InBody) or a smart scale.
- **Progress pictures:** side-by-side comparison over time, plus LLM analysis of visible changes (e.g. "visible change in shoulders"). Where the analysis runs is open (see below).
- **Load capacity:** weight lifted per exercise over time (from progressive overload on the [Workout Plan](workout-plan.md)).
- Everyday metrics: activity, sleep, nutrition adherence, water, workout consistency.

## Forecast

- Where each parameter is likely to be if the person continues the current workout and diet plan, e.g. in 4, 8 and 12 weeks.
- Based on how the person has actually been following the plan, not perfect adherence.
- Shown as a range, not a single number; only appears after 3–4 weeks of data.
- Numbers come from simple calculations (e.g. weight from calorie balance, strength from recent progression); the LLM only writes the explanation.

## What-if simulator

- Change something (e.g. calorie target, workout days per week) or add a disruption (e.g. a 10-day vacation) and see how the forecast changes compared with the current path.
- Nothing changes in the actual plans unless the person chooses to apply it (with the usual preview).

## Disruption planning

- Add a planned disruption: dates and type (vacation, travel, festival, illness, busy work week).
- The app suggests what to do, e.g. hotel / bodyweight workouts, eating-out guidelines, a minimum routine, how to get back on track afterwards.
- Can apply a travel version of the [Workout Plan](workout-plan.md) and [Nutrition Plan](nutrition-plan.md) for those dates, with a preview first.
- An upcoming disruption shows as an action item on the [Summary](summary.md).

## Rules

- Weight and calorie charts follow the same opt-in switches as the Summary (set on [Settings / Profile](settings-profile.md)).
- Blood markers are shown against normal ranges with "discuss with your doctor" where relevant; no diagnoses.

## Open question: progress photo analysis, local vs cloud (revisit later)

Decided: the LLM analyses progress photos. Open: where it runs.

- *Local Ollama only:* photos never go to a cloud LLM; but analysis waits until the local machine is on, needs a capable Mac (Apple Silicon, ~16 GB memory), the local machine needs upkeep, and smaller local models are less accurate. Reuses the pending-queue setup already needed for [Personal Artifacts](personal-artifacts.md).
- *Cloud:* instant, more accurate, simpler to build; but body photos go to a free third-party API that may keep or log them. A paid API that promises not to keep data is a later option (a few dollars a month at most).
- *Either way:* inconsistent photos (lighting, angle, clothing) give unreliable results, so add a photo guide (same spot, pose, time of day, outline overlay); word feedback carefully so "no visible change" doesn't demotivate.

## Related pages

- [Summary](summary.md): the at-a-glance view; its cards link here.
- [Personal Artifacts](personal-artifacts.md): blood work and body composition reports.
- [Workout Plan](workout-plan.md) / [Nutrition Plan](nutrition-plan.md): what forecasts are based on, and what travel versions modify.
- [Plan for Today](plan-for-today.md): source of the daily logs behind the trends.
