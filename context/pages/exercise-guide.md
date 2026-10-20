# Exercise Guide Page

← [Hub: skills.md](../skills.md) · Status: **Defined**

**Purpose:** a detailed breakdown of every exercise in the person's plan for the week, grouped by day and by phase (cardio, mobility, activation, main, cooldown). Exercises on [Plan for Today](plan-for-today.md) and the [Workout Plan](workout-plan.md) link here.

## For each exercise, in this order

1. **Diagram** of the exercise (start and end positions).
2. **Muscles targeted, shown visually:** front and back body map with targeted muscles in **red**: primary muscles dark red, secondary muscles light red.
3. **About the exercise:** what it is and what it's for.
4. **Correct-form markers:** cues that show it's being done right (e.g. "knees track over toes", "back stays neutral", "feel it in the glutes, not the lower back").
5. **Precautions** during the exercise, plus personal precautions from confirmed [Personal Artifacts](personal-artifacts.md) facts (e.g. a knee note).
6. **YouTube video link** (see below).

## Choosing the YouTube video

- **Priority:** short video first, then highest views, then positive comments.
- **Maximum length:** under 3 minutes.
- **YouTube Shorts:** allowed and recommended.
- **How:**
  - Search with the YouTube Data API (free quota: about 100 searches a day, plenty for two people).
  - For each candidate, get duration, view count and like count.
  - Read the top comments and have the LLM rate whether they're positive (e.g. "clear", "fixed my form" vs "this is wrong").
  - Combine into a score and pick the top video.
  - Save the choice per exercise, so each exercise is searched only once (refreshed monthly or on request).

## Where the content comes from

- **Diagrams and exercise data:** a free, open exercise database, e.g. free-exercise-db (public domain, ~800 exercises with images) or wger (open source). LLM-generated diagrams aren't reliable enough.
- **Body map:** an open-source muscle-map component that highlights muscles in red (e.g. react-native-body-highlighter, which works with Expo).
- **Form markers and precautions:** written by the LLM once per exercise, saved and reused, so they're consistent and can be reviewed and corrected.

## Related pages

- [Workout Plan](workout-plan.md): the weekly plan this guide covers; exercise swaps.
- [Plan for Today](plan-for-today.md): links here from each exercise.
- [Personal Artifacts](personal-artifacts.md): source of personal precautions.
- Data: [Workouts](../data-model.md#workouts) (`exercises` table). Jobs: [Job types](../architecture.md#job-types).
