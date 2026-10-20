# Personal Artifacts Page

← [Hub: skills.md](../skills.md) · Status: **Defined**

**Purpose:** each person uploads any health document they have. The LLM reads it and adjusts that person's [Workout Plan](workout-plan.md) and [Nutrition Plan](nutrition-plan.md). Example: if someone is anaemic, the meal plan suggests iron-rich foods (with vitamin C to help absorption) and workout intensity may be eased.

## Document types

PDF lab reports, photos of reports, and doctor's notes or typed notes (e.g. "knee pain on squats"). Appointments and medications are also entered here (typed, or taken from a confirmed doctor's note).

## Flow

1. Upload.
2. The LLM extracts the health facts (e.g. "Haemoglobin 10.2 g/dL, low").
3. The person reviews, corrects and confirms them.
4. The confirmed facts are saved to that person's health profile.
5. The workout and meal plans are regenerated from the health profile.

## Rules

- **Confirmation required:** plans never change from extracted facts until the person confirms them.
- **Plans use the saved facts, not the original documents.**
- **Privacy ("facts only to cloud"):**
  - Documents are read only by **local Ollama** (a Qwen vision model, e.g. Qwen2.5-VL, for photos).
  - Only confirmed facts (e.g. "low haemoglobin") go to the cloud Qwen API when building plans.
  - Uploads made while the local machine is off wait as "pending" and are read when it's next on.
- **Storage:** original files in private Supabase Storage, visible only to that person's login. Older reports are kept so [Progress](progress.md) can show trends.
- **Safety:** the app never diagnoses. Out-of-range values are marked "discuss with your doctor", and suggestions never override treatment a doctor prescribed (e.g. iron supplements).

## What uses these facts

- [Workout Plan](workout-plan.md) and [Nutrition Plan](nutrition-plan.md): adjust plans and targets.
- [Summary](summary.md): condition-driven cards (blood pressure, glucose, lipids, medication adherence) and action items (appointments, screenings, overdue lab tests).
- [Plan for Today](plan-for-today.md): daily medication checkboxes.
- [Progress](progress.md): blood work and body composition trends.
- [Exercise Guide](exercise-guide.md): personal precautions.
