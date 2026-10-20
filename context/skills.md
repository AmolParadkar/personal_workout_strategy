# Personal Workout Strategy — Context Summary

_Last updated: 2026-10-20_

This file summarizes everything decided so far about the app. All context files live in the `context/` folder.

## 1. Application Overview

A personalised health app for two users: **Amol** and **his spouse**. Both use iPhones.

### Pages

| # | Page | Purpose | Spec status |
|---|---|---|---|
| 1 | **Summary** | Current health status of the selected person | Defined (section 3) |
| 2 | **Plan for Today** | One combined page: today's detailed workout (with links) and today's meal plan, plus food logging (photo upload or manual entry) | Defined (section 5) |
| 3 | **Workout Plan** | The weekly customised workout plan, which the person can change; weight logging; explanation of the plan | Defined (section 6) |
| 4 | **Nutrition Plan** | The weekly customised meal plan with daily macro and micronutrient targets, which the person can change | Defined (section 7) |
| 5 | **Progress** | Long-term trends and insights, forecasts, a what-if simulator, and disruption planning (e.g. vacations) | Defined (section 10) |
| 6 | **75 Hard (Amol only)** | A simple daily checklist of the 75 Hard rules | Defined (section 9) |
| 7 | **Exercise Guide** | Detailed guide to every exercise in the week's plan: diagram, muscles targeted (highlighted on a body map), correct-form cues, precautions, and the best short YouTube video | Defined (section 11) |
| 8 | **Personal Artifacts** | Each person uploads health documents; the LLM reads them and adjusts that person's plans | Defined (section 4) |
| 9 | **Settings / Profile** | Each person's details (age, height, goals, equipment, available days) and the switches for the opt-in Summary cards. Opened from the profile dropdown | Defined (section 8) |

**Profile switcher:** a simple dropdown at the top of every page to switch between profiles. It also opens the Settings / Profile page.

## 2. Technical Decisions

- **Phase 1 is a website.** It becomes an iPhone app once the features are settled. Publishing to Apple ($99/year developer account) is on hold until then.
- **Framework:** Expo, published as a website, so the same code later builds the iPhone app.
- **Code layout:** app logic (plan generation, LLM calls, data storage) lives in the backend, not the screens, so moving to the app later mostly reuses code.
- **Hosting (all free tiers):**
  - Website on **Vercel**.
  - Database, login and file storage on **Supabase** (free plan; it pauses after about a week without use).
- **LLM:**
  - **Qwen** through a free cloud API (e.g. OpenRouter, Groq) for building plans.
  - **Ollama** on a local machine as a backup, and as the only model that reads uploaded documents (see section 4).
- **Health data:**
  - Source is **Apple Health**.
  - Phase 1 (website): an **iOS Shortcuts automation** on each iPhone sends the data to the backend daily.
  - Phase 2 (app): the app reads Apple Health directly.
  - **Wearables:** none yet. The design must make them easy to add later. Most wearables sync into Apple Health, so they'd flow in through the same path.
- **Login:** Supabase login is needed because the site holds health data. Each person's data is visible only to their own login.

## 3. Summary Page

**The Summary page is a read-only dashboard: no user inputs on it.** All logging and settings happen on other pages.

### 3.1 Cards

**Default cards (on for everyone):**

| Card | What it shows |
|---|---|
| **Activity** | Active minutes per week against a target. WHO guideline: 150 moderate minutes per week. |
| **Sleep / time in bed** | Average duration, plus how consistent bedtime and wake time are. Consistency often matters more than the total. |
| **Resting heart rate** | Trend against the person's own 30-day baseline. An early signal of illness, overtraining or stress. |
| **One goal metric** | Whatever the person said they care about, e.g. weight, VO₂ max or HRV. |
| **Workout day streak** | Number of consecutive days with a completed workout. |
| **Macros and micros** | Daily targets (from the LLM nutrition plan) against what was actually eaten. |
| **Water intake** | Daily water intake against a target. |

**Opt-in cards (off by default; switched on in the person's profile settings, not on the Summary page):**

| Card | What it shows |
|---|---|
| **Body weight** | Current weight and its change over the last week. |
| **Calorie intake** | Calories eaten per day. |
| **Calories burned** | Average calories burned per day. |

**Condition-driven cards (only when relevant):**

- **Blood pressure, glucose / HbA1c, or lipids**, for people with those conditions or risk factors. These can switch on automatically from confirmed facts on the Personal Artifacts page.
- **Medication adherence:** % of doses taken (doses are ticked off on Plan for Today).

**Action items (often more useful than any metric):**

- Upcoming appointments.
- Screenings due.
- Overdue lab tests, e.g. worked out from the date of the last report uploaded on Personal Artifacts.

### 3.2 How each metric is shown

Every card has:

1. **The current value.**
2. **A 7- or 30-day trend arrow** (e.g. for weight, calorie intake, calories burned).
3. **A comparison** to the person's baseline or goal.
4. **A one-line "so what"** explaining what the number means. Without context, a number is just decoration.

### 3.3 Rules: things to avoid or treat carefully

- **No unexplained composite "health score".** Only use one if it's clear exactly what moves it. Unexplained scores erode trust fast.
- **Weight and calories are opt-in**, never default headline metrics. Putting them up front is a real risk for anyone with disordered eating.
- **No red alerts without a next step.** Every warning comes with "here's what to do". Alerts with no next step cause anxiety, not action.
- **Missing data:** a card whose data isn't available (e.g. no wearable) shows "Connect a wearable to track this" instead of a blank.

### 3.4 Where the data comes from (iPhone only, no watch)

| Metric | Source today | With a watch later |
|---|---|---|
| Active minutes | Not recorded by the iPhone alone. Count workouts logged in the app, plus brisk-walking time. | Recorded automatically |
| Sleep / time in bed | Apple Health, only if Sleep / Bedtime is set up. Measures time in bed, not actual sleep. | Real sleep tracking |
| Resting heart rate, HRV, VO₂ max | Not available | Available |
| Calories burned | Rough estimate from steps | Much more accurate |
| Body weight | Apple Health (smart scale or app), or typed into the app | Same |
| Workout streak | Workouts completed in the app | Same, plus watch workouts |
| Macro / micro targets | Generated by the LLM nutrition plan | Same |
| Macros / micros achieved, calorie intake | Logged on Plan for Today: as recommended, photo + LLM, or manual (section 5) | Same |
| Water intake | Logged with quick-add buttons (+250 ml / +500 ml) on Plan for Today | Same |
| Appointments, medications | Entered on Personal Artifacts (typed, or taken from a confirmed doctor's note); daily doses ticked off on Plan for Today | Same |

## 4. Personal Artifacts Page

**Purpose:** each person uploads any health document they have. The LLM reads it and adjusts that person's workout and meal plans. Example: if someone is anaemic, the meal plan suggests iron-rich foods (with vitamin C to help absorption) and workout intensity may be eased.

- **Document types:** PDF lab reports, photos of reports, and doctor's notes or typed notes (e.g. "knee pain on squats").
- **Flow:**
  1. Upload.
  2. The LLM extracts the health facts (e.g. "Haemoglobin 10.2 g/dL, low").
  3. The person reviews, corrects and confirms them.
  4. The confirmed facts are saved to that person's health profile.
  5. The workout and meal plans are regenerated from the health profile.
- **Confirmation required:** plans never change from extracted facts until the person confirms them.
- **Plans use the saved facts, not the original documents.**
- **Privacy ("facts only to cloud"):**
  - Documents are read only by **local Ollama** (a Qwen vision model, e.g. Qwen2.5-VL, for photos).
  - Only confirmed facts (e.g. "low haemoglobin") go to the cloud Qwen API when building plans.
  - Uploads made while the local machine is off wait as "pending" and are read when it's next on.
- **Storage:** original files are kept in private Supabase Storage, visible only to that person's login. Older reports are kept so the Progress page can show trends (e.g. haemoglobin over time).
- **Safety:** the app never diagnoses. Out-of-range values are marked "discuss with your doctor", and suggestions never override treatment a doctor prescribed (e.g. iron supplements).

## 5. Plan for Today Page

One combined page showing everything for the selected person's day.

### 5.1 Today's workout

- The detailed workout for the day (from the LLM workout plan).
- Each exercise links to its **Exercise Guide** entry (text, images, YouTube links).
- Completing the workout here counts towards the **workout day streak** on the Summary page.

### 5.2 Today's meals

- A **recommended meal plan** for the day (from the LLM nutrition plan).
- For each meal, the person can log it in one of three ways:
  1. **Ate as recommended:** one tap; the recommended meal's nutrients count automatically.
  2. **Upload a photo:** the upload button takes the picture and runs the photo analysis (5.3).
  3. **Add your own:** enter the food and values manually.
- Running totals for the day (calories, macros, micros vs targets) update as meals are logged; these feed the Summary page.

### 5.2a Water

- **Quick-add buttons** (+250 ml / +500 ml) live on Plan for Today only, keeping all daily logging in one place. The Summary page shows the water intake card but has no buttons.

### 5.2b Medications

- For anyone with medications listed (from Personal Artifacts), today's doses appear as checkboxes to tick off. These feed the medication adherence card on the Summary page.

### 5.3 Photo analysis flow (always with a confirmation prompt)

1. **Upload:** the person takes or uploads a picture of the meal.
2. **Identify:** the vision LLM suggests the dish and its likely ingredients.
3. **Confirm the dish:** the app always asks first, e.g. "Is this a chicken Caesar salad?" The person confirms or corrects it.
4. **Follow-up questions** about the things a photo can't show, e.g.:
   - "How much chicken, approximately?"
   - "How much oil was used?"
   - "Are these the veggies?" (shows the detected list to edit)
   - "Anything else we missed?"
5. **Calculate:** calories, macros and micros are calculated automatically.
6. **Review:** a final, editable screen shows the totals before saving.

### 5.4 Food logging rules (confirmed)

- **Numbers come from a food database, not LLM guesses.** The LLM identifies the ingredients and amounts; the nutrients come from a nutrition database (e.g. USDA FoodData Central, or the Indian Food Composition Tables for Indian dishes). More accurate, and the same meal always gives the same numbers.
- **Quick-pick answers** instead of typing grams, e.g. oil: none / 1 tsp / 1 tbsp / 2 tbsp; chicken: palm-size / 100 g / 150 g / 200 g.
- **Always ask about hidden calories:** oil, butter / ghee, dressings, sugar.
- **Favourites:** a repeated meal can be saved and logged in one tap.
- **Privacy:** food photos are not medical documents, so they go to a cloud Qwen vision model (local Ollama as backup).

## 6. Workout Plan Page

### 6.1 Requirements (from Amol)

1. **Weekly customised workout plan.** The person can add or change something (e.g. add a session, swap an exercise, mark a day unavailable). If that change affects the rest of the week, the plan automatically rebalances.
2. **Body weight input** that is saved to the backend (feeds the opt-in weight card on the Summary page). Weight lifted per exercise is logged separately (see progressive overload in 6.3).
3. **Explanation of the plan:** what type of workout each session is and which muscles it targets.

### 6.2 Session structure (confirmed)

Every workout follows these five phases, in this order, and every activity of the day is labelled with its phase (on this page and on Plan for Today):

1. **Cardio:** at the beginning, to warm up.
2. **Mobility:** for the joints used in that day's session.
3. **Activation:** of the muscles targeted that day.
4. **Main workout.**
5. **Cooldown and stretching.**

### 6.3 Confirmed additions

- **Effort feedback:** after each session, a quick "how hard was it?" (easy / right / too hard) that the next plan uses.
- **Exercise swaps:** each exercise offers alternatives from the same phase that hit the same muscles with the available equipment.
- **Preview before changing the week:** when a change rebalances the plan, show what moves (e.g. "Leg day moves from Wed to Fri") and apply it only after the person confirms.
- **Progressive overload:** log sets, reps and weight lifted per exercise; next week's plan adjusts the load from what was actually done.
- **Weekly muscle coverage:** a body map or table showing sets per muscle group for the week, so gaps and imbalances are visible.

### 6.4 Plan inputs

The LLM needs, for each person: available days, time per session, equipment, and location (home / gym / travel), along with the profile (section 8) and confirmed facts from Personal Artifacts.

### 6.5 Out of scope for this page

- **75 Hard:** Amol's two daily workouts and 75 Hard rules are handled on the 75 Hard page, not here.
- **Parked suggestions (not selected):** "why this plan" note, missed-workout rescheduling, deload weeks, plan history.

## 7. Nutrition Plan Page

1. **Weekly meal plan:** breakfast, lunch, dinner and snacks for each day. Plan for Today shows today's part of it.
2. **Daily targets with the reasoning:** calories, protein, carbs and fat, plus key micronutrients. Each target has a one-line reason, e.g. "Iron target raised because of your low haemoglobin report."
3. **Change and rebalance:** the person can swap a meal or mark a day as eating out; the rest of the week adjusts to stay on target, with a preview before anything changes (same as the Workout Plan).
4. **Meal swaps:** alternatives with similar macros that fit the person's diet type.
5. **Weekly grocery list** generated from the week's plan.
6. **Matched to workouts:** more carbs and protein on heavy training days, less on rest days.
7. **Adjusts to what was actually eaten:** uses food logs from Plan for Today; e.g. if protein is often under target, next week's plan makes it easier to hit.

**Plan inputs** (set on the Settings / Profile page): diet type (vegetarian / eggetarian / non-vegetarian), cuisine preferences, allergies and disliked foods, meals per day, and cooking time available, along with confirmed facts from Personal Artifacts.

## 8. Settings / Profile Page

- Opened from the profile dropdown at the top of every page.
- Holds each person's details, which are the inputs the LLM uses to build plans (see below), plus available days, time per session, equipment and training location (section 6.4), and diet type, cuisine preferences, allergies / dislikes, meals per day and cooking time (section 7).
- Holds the switches for the opt-in Summary cards (body weight, calorie intake, calories burned), off by default.

### 8.1 Personal details (entered in the app)

Decided: personal details are not collected here; each person fills them in on the Settings / Profile page once the app exists. **(Proposed)** On first sign-in, the app asks for these before generating any plans.

Fields:

- **Both:** age, height, weight, goals, diet type, cuisine preferences, allergies / dislikes, meals per day, cooking time, equipment, available days, time per session, training location, injuries / limitations.
- **Amol only:** 75 Hard current day (asked on the 75 Hard page).

## 9. 75 Hard Page (Amol only)

A simple daily checklist of the 75 Hard rules. Only visible on Amol's profile.

**Daily checklist (the standard 75 Hard rules):**

- [ ] Follow the diet: no cheat meals, no alcohol
- [ ] Workout 1: 45 minutes
- [ ] Workout 2: 45 minutes, outdoors
- [ ] Drink 1 gallon (about 3.8 L) of water
- [ ] Read 10 pages of a non-fiction book
- [ ] Take a progress photo

**Also on the page:**

- **Day counter:** "Day X of 75". On first use, the page asks "What day are you on?" so a challenge already in progress can be picked up; it then counts up automatically.
- **Missed item = restart:** if any item is not ticked by midnight, the counter automatically resets to Day 1 (the standard 75 Hard rule).
- **Keep it simple for now:** no history grid and no reminders; just today's checklist and the day counter.

**Not on this page:** the workouts themselves aren't planned here; this page only ticks them off. (Earlier note in section 6.5 that 75 Hard workouts are handled here means as checklist items.)

## 10. Progress Page

### 10.1 Purpose and how it differs from Summary

| | Summary | Progress |
|---|---|---|
| Question it answers | "How am I doing right now?" | "Where have I come from, and where am I heading?" |
| Time span | Today, this week, 7/30-day arrows | Months: full history plus forecast |
| Depth | Glanceable cards, one-line "so what" | Full charts, insights, explanations |
| Inputs | None (read-only) | Only for what-if scenarios and planned disruptions |
| Future | No | Forecasts and what-if simulations |

- Each Summary card links to its full chart on the Progress page.
- Summary shows no full charts; Progress shows no "today" statuses.

### 10.2 Trends and insights over time

Trend lines and written insights for:

- **Blood work:** markers from uploaded lab reports (e.g. haemoglobin, vitamin D, lipids) over time, against normal ranges.
- **Body composition:** e.g. weight, body fat %, muscle mass, from uploaded reports (DEXA / InBody) or a smart scale.
- **Progress pictures:** side-by-side comparison over time, **plus LLM analysis** of visible changes (e.g. "visible change in shoulders"). Where the analysis runs (local Ollama vs cloud) is an open question, to revisit later (section 12).
- **Load capacity:** weight lifted per exercise over time (from progressive overload logs).
- Plus the everyday metrics: activity, sleep, nutrition adherence, water, workout consistency.

### 10.3 Forecast

- Shows where each parameter is likely to be if the person continues the current workout and diet plan, e.g. in 4, 8 and 12 weeks.
- Based on how the person has actually been following the plan, not perfect adherence.
- Shown as a range, not a single number; only appears once there are enough weeks of data.
- Numbers come from simple calculations (e.g. weight from calorie balance, strength from recent progression); the LLM only writes the explanation.

### 10.4 What-if simulator

- The person changes something (e.g. calorie target, workout days per week) or adds a disruption (e.g. a 10-day vacation) and sees how the forecast changes, compared with the current path.
- Nothing changes in the actual plans unless the person chooses to apply it (with the usual preview).

### 10.5 Disruption planning

- The person adds a planned disruption: dates and type (vacation, travel, festival, illness, busy work week).
- The app suggests what to do from the person's end, e.g. a hotel / bodyweight workout version, eating-out guidelines, minimum routine to keep progress, how to get back on track afterwards.
- Can apply a travel version of the workout and meal plans for those dates, with a preview first.
- An upcoming disruption shows as an action item on the Summary page.

### 10.6 Rules

- Weight and calorie charts follow the same opt-in switches as the Summary page.
- Blood markers are shown against normal ranges with "discuss with your doctor" where relevant; no diagnoses.

## 11. Exercise Guide Page

Gives a detailed breakdown of every exercise in the person's plan for the week (grouped by day and by phase: cardio, mobility, activation, main, cooldown). Exercises on Plan for Today and the Workout Plan link here.

### 11.1 For each exercise, in this order

1. **Diagram** of the exercise (start and end positions).
2. **Muscles targeted, shown visually:** a front and back body map with the targeted muscles marked in **red**. Primary muscles in dark red, secondary muscles in light red.
3. **About the exercise:** what it is and what it's for.
4. **Correct-form markers:** the cues that tell you you're doing it right (e.g. "knees track over toes", "back stays neutral", "feel it in the glutes, not the lower back").
5. **Precautions** to take during the exercise. Plus personal precautions from confirmed Personal Artifacts facts (e.g. a knee note).
6. **YouTube video link** (see 11.2).

### 11.2 Choosing the YouTube video

- **Priority:** short video first, then highest views, then positive comments.
- **Maximum length:** under 3 minutes.
- **YouTube Shorts:** allowed and recommended.
- **How:**
  - Search with the YouTube Data API (free quota: about 100 searches a day, plenty for two people).
  - For each candidate, get duration, view count and like count.
  - Read the top comments and have the LLM rate whether they're positive (e.g. "clear", "fixed my form" vs "this is wrong").
  - Combine into a score and pick the top video.
  - Save the choice per exercise, so each exercise is searched only once (refreshed e.g. monthly or on request).

### 11.3 Where the content comes from

- **Diagrams and exercise data:** a free, open exercise database, e.g. free-exercise-db (public domain, ~800 exercises with images) or wger (open source). LLM-generated diagrams aren't reliable enough.
- **Body map:** an open-source muscle-map component that highlights muscles in red (e.g. react-native-body-highlighter, which works with Expo).
- **Form markers and precautions:** written by the LLM once per exercise, saved, and reused, so they're consistent and can be reviewed and corrected.

## 12. Open Questions

- **First sign-in:** confirm that the app asks for profile details before generating any plans (8.1).
- **Progress photo analysis: local vs cloud (revisit later).** Decided: the LLM analyses progress photos. Open: where it runs.
  - *Local Ollama only:* photos never go to a cloud LLM; but analysis waits until the local machine is on, needs a capable Mac (Apple Silicon, ~16 GB memory), the local machine needs upkeep, and smaller local models are less accurate. Reuses the pending-queue setup already needed for Personal Artifacts.
  - *Cloud:* instant, more accurate, simpler to build; but body photos go to a free third-party API that may keep or log them. A paid API that promises not to keep data is a later option (a few dollars a month at most).
  - *Either way:* inconsistent photos (lighting, angle, clothing) give unreliable results, so add a photo guide (same spot, pose, time of day, outline overlay); word feedback carefully so "no visible change" doesn't demotivate.
