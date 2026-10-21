# Plan for Today Page

← [Hub: skills.md](../skills.md) · Status: **Defined**

**Purpose:** one combined page for the selected person's day: today's workout, today's meals, and all daily logging (meals, water, medications).

## Today's workout

- The detailed workout for the day, taken from the [Workout Plan](workout-plan.md).
- Activities are grouped and labelled by phase: Cardio → Mobility → Activation → Main workout → Cooldown and stretching (see [Workout Plan](workout-plan.md#session-structure)).
- Each exercise links to its [Exercise Guide](exercise-guide.md) entry.
- Sets, reps and weight lifted are logged per exercise (feeds progressive overload on the [Workout Plan](workout-plan.md) and load capacity on [Progress](progress.md)).
- After the session: a quick effort rating (easy / right / too hard).
- Completing the workout counts towards the **workout day streak** on the [Summary](summary.md).

### As built (M6)

- **Today's workout card** (above water): the session's title, length and explanation, then its five phases. Main and activation exercises have a row per set: reps, and kg for main exercises, with the target as a hint (from progressive overload) and the overload note under the exercise; ✓ saves the set (saving again corrects it). Timed moves (warm-up, holds, stretches) have **Mark done**. Exercise names open the Exercise Guide.
- **Finish workout** asks "How hard was it?" (Easy / Just right / Too hard), which next week's plan uses; afterwards "✓ Workout done · felt …" with **Change rating** and **Undo**.
- **Streak**: "N planned workouts in a row": rest days don't count; a planned workout not done by the end of its week breaks it (one missed earlier this week can still be done).
- **Rest day**: says so, and offers any earlier session this week not yet done ("Do Wed: Upper body"), which can be logged today.
- On the other person's profile it's view-only (their logged sets and whether it's done).

## Today's meals

- A **recommended meal plan** for the day, taken from the [Nutrition Plan](nutrition-plan.md).
- Each meal can be logged in one of three ways:
  1. **Ate as recommended:** one tap; the recommended meal's nutrients count automatically.
  2. **Upload a photo:** runs the photo analysis flow (below).
  3. **Add your own:** enter the food and values manually.
- Running totals for the day (calories, macros, micros vs targets) update as meals are logged and feed the [Summary](summary.md).

## Water

- **Quick-add buttons** (+250 ml / +500 ml) and **Undo** (removes the last glass). They live on this page only; the [Summary](summary.md) shows the water card without buttons. **Built (M3).**
- Shows today's total against the person's target (Settings → Water, default 3 L), with a progress bar.
- For anyone doing [75 Hard](75-hard.md): shows how much is left to a gallon (3.8 L); reaching it **ticks the 75 Hard water item automatically** (only ticks, never unticks).
- The "day" is the browser's local date. View-only on the other person's profile.

## Medications

- For anyone with medications listed (from [Personal Artifacts](personal-artifacts.md)), today's doses appear as checkboxes. These feed the medication adherence card on the [Summary](summary.md).

## Photo analysis flow (always with a confirmation prompt)

1. **Upload:** take or upload a picture of the meal.
2. **Identify:** the vision LLM suggests the dish and its likely ingredients.
3. **Confirm the dish:** the app always asks first, e.g. "Is this a chicken Caesar salad?"
4. **Follow-up questions** about what a photo can't show, e.g.:
   - "How much chicken, approximately?"
   - "How much oil was used?"
   - "Are these the veggies?" (shows the detected list to edit)
   - "Anything else we missed?"
5. **Calculate:** calories, macros and micros are calculated automatically.
6. **Review:** a final, editable screen shows the totals before saving.

## Food logging rules

- **Numbers come from a food database, not LLM guesses.** The LLM identifies ingredients and amounts; nutrients come from a nutrition database (e.g. USDA FoodData Central, or the Indian Food Composition Tables for Indian dishes).
- **Quick-pick answers** instead of typing grams, e.g. oil: none / 1 tsp / 1 tbsp / 2 tbsp; chicken: palm-size / 100 g / 150 g / 200 g.
- **Always ask about hidden calories:** oil, butter / ghee, dressings, sugar.
- **Favourites:** a repeated meal can be saved and logged in one tap.
- **Privacy:** food photos aren't medical documents, so they go to a cloud Qwen vision model (local Ollama as backup). See [Privacy model](../skills.md#privacy-model).

## Related pages

- [Workout Plan](workout-plan.md) and [Nutrition Plan](nutrition-plan.md): the weekly plans this page shows today's slice of.
- [Exercise Guide](exercise-guide.md): how to do each exercise.
- [Summary](summary.md): reads everything logged here.
- [Progress](progress.md): long-term trends of everything logged here.
- [75 Hard](75-hard.md): Amol's separate daily checklist.
- Data: [Workouts](../data-model.md#workouts), [Nutrition](../data-model.md#nutrition), [Health records](../data-model.md#health-records). Flow: [Logging a food photo](../architecture.md#logging-a-food-photo).
