# 75 Hard Page

← [Hub: skills.md](../skills.md) · Status: **Built** (M2)

**Purpose:** a simple daily checklist of the 75 Hard rules. Kept as simple as possible: no history grid, no reminders.

## Daily checklist (standard 75 Hard rules)

- [ ] Follow the diet: no cheat meals, no alcohol
- [ ] Workout 1: 45 minutes
- [ ] Workout 2: 45 minutes, outdoors
- [ ] Drink 1 gallon (about 3.8 L) of water
- [ ] Read 10 pages of a non-fiction book
- [ ] Take a progress photo (a tick only; photos come with [Progress](progress.md))

## Who

- **Anyone can start a challenge** from this page (decided 2026-10-20; originally "Amol only").
- **Navigation link:** always shown on your own profile, so you can start one. On the other person's profile it's shown only while they have a challenge running, and the page is view-only there.

## Rules

- **Starting:** "What day are you on?" (1–75), so a challenge already in progress can be picked up. That day is today's number; it counts up from there.
- **A day is complete** when all six items are ticked.
- **Forgot to tick? Yesterday stays open until 12:00** the next day (decided 2026-10-20), so a forgotten tick doesn't reset weeks of progress. Until then the page shows yesterday's checklist with a warning: "Tick yesterday's items before 12:00, or the count starts again at Day 1."
- **Missed day = restart:** a day that's still incomplete once it closes (noon the next day) restarts the count; the day after it is Day 1. Several days away → today is Day 1. The page notes "Restarted at Day 1 because <date> wasn't complete."
- **Completion:** reaching Day 75 with all six ticked shows "75 Hard complete" and a button to start a new challenge.
- **Stop:** a small "Stop challenge" link (with confirmation) ends the challenge; ticks are kept.
- **Midnight and noon** follow the timezone the browser reported when the challenge was started.
- **No midnight job:** the day, resets and completion are calculated from the start and the ticks each time the page loads (`backend/core/seventy_five_hard.py`, covered by unit tests).
- The workouts aren't planned here; this page only ticks them off.
- **Water ticks itself:** logging a gallon (3.8 L) on the [Plan for Today](plan-for-today.md) water card ticks "Drank a gallon of water" (if that day can still be ticked). It never unticks.

## Related pages

- [Workout Plan](workout-plan.md): the regular weekly plan (75 Hard workouts aren't planned there either).
- [Plan for Today](plan-for-today.md): the regular daily logging page.
- [Settings / Profile](settings-profile.md): profile this page belongs to.
- Data: [75 Hard](../data-model.md#75-hard).
