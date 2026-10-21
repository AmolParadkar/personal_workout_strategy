# Exercise Guide Page

← [Hub: skills.md](../skills.md) · Status: **Built (M5)**: library and exercise pages; the weekly-plan view arrives with [Workout Plan](workout-plan.md) (M6)

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

## Video feedback

Under each video: **Is this the right video?**

- **Yes:** the video is confirmed: kept, and skipped by the monthly refresh. "Not right after all?" can still reject it later.
- **No:** pick quick reasons (Wrong exercise, Poor form, Not in English, Hard to follow) and/or type a specific one (at least one is needed), then **Find another video**. A new search starts straight away (even if one failed earlier that day); the page shows "Finding a better video, using your feedback…".
- **How the reasons are used:** every rejection for the exercise (video title + reason) goes to the LLM, which writes a better YouTube search and a list of requirements (e.g. "bar on the upper back"). Rejected videos are never chosen again. Each shortlisted candidate (8 after a rejection, 5 otherwise) is rated by the LLM for **relevance** (does it teach exactly this exercise and meet the requirements, from title, description and comments) as well as comment tone; candidates under 0.5 relevance are dropped, and the score is multiplied by relevance. If none qualify, the old video is cleared and the page says no other video matched.
- Repeat until the right video is on; each search costs about 105 of the 10,000 daily YouTube units.
- Feedback is shared (the library is shared) and stored in `video_feedback`; anyone signed in can give it, as themselves.

## As built (M5)

- **`/exercises`:** until workout plans exist (M6), the whole library: search by name (every word must appear, in any order: "squat barbell" finds Barbell Squat), filter by primary muscle and equipment (folded behind a **Filters** button showing how many are on, so results sit right under the search box on phones), 30 at a time with **Show more**. **Closest matches:** when a search finds nothing, the 5 closest names are shown as the results under "No exact match for … Closest matches:" (trigram similarity, so typos like "sqaut", "plnk" or "dumbell pres" still work; ranked by how much of the typed text appears in the name, then how close the whole name is, then shortest name). From M6, this week's exercises appear above it, grouped by day and phase.
- **`/exercises/<id>`** (e.g. `/exercises/Barbell_Squat`): start and end images; front and back body map (primary dark red, secondary light red; the body matches the profile's sex); about, **Good form looks like**, **Precautions**; the source's step-by-step **How to do it**; a video card (thumbnail, title, channel, length, views) opening YouTube.
- **Prepared on first open:** opening an exercise without a guide or video queues `write_exercise_guide` and `find_exercise_video` for the Mac worker; the page shows "Finding…" and fills in (checking every 2 seconds). If the worker is offline it says so. A failed job shows its reason and is retried after a day. Videos are re-checked monthly; "no short video found" is remembered.
- **Video score:** candidates from YouTube's "short" search (under 4 minutes) are kept only if under 3 minutes; score = 35% shortness + 35% views (log scale) + 10% like ratio + 20% comment positivity, multiplied by relevance (LLM rating of title, description and top 15 comments of the shortlist; neutral if comments are off or no LLM answers). About 105 quota units per exercise (~90 exercises a day on the free quota).
- **Guide text:** written by Groq (cloud Qwen) or, as backup, Ollama on the Mac; checked against a fixed shape (2–3 sentence about, 3–8 cues, 2–6 precautions) and saved with the model's name. Prompt asks for current evidence-based coaching (no outdated rules).
- **Personal precautions** from Personal Artifacts: placeholder until M8.
- **Body map regions:** the map has no separate lats, middle back or hip abductors, so those show on the nearest region (upper back, upper back, glutes).

## Related pages

- [Workout Plan](workout-plan.md): the weekly plan this guide covers; exercise swaps.
- [Plan for Today](plan-for-today.md): links here from each exercise.
- [Personal Artifacts](personal-artifacts.md): source of personal precautions.
- Data: [Workouts](../data-model.md#workouts) (`exercises` table). Jobs: [Job types](../architecture.md#job-types).
