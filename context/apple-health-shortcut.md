# Apple Health Shortcut

← [Hub: skills.md](skills.md) · Related: [Setup](setup.md) · [Architecture](architecture.md#daily-health-data) · [Data model](data-model.md#health-data) · [Settings / Profile](pages/settings-profile.md)

How to build the iOS Shortcut that sends yesterday's Apple Health data (and last night's sleep) to the app every morning. Each person builds it once on their own iPhone. It takes about 20 minutes.

> Shortcuts menu names can differ slightly between iOS versions. If an action isn't found by the exact name below, search for the key word (e.g. "Health Samples", "Statistics").

## What it sends

| Metric | From Apple Health | Sent as |
|---|---|---|
| `steps` | Steps, yesterday's total | `value` |
| `active_energy_kcal` | Active Energy, yesterday's total | `value` (kcal) |
| `walking_running_km` | Walking + Running Distance, yesterday's total | `value` (km) |
| `weight_kg` | Weight, latest in the last day (if any) | `value` (kg) |
| `resting_hr` | Resting Heart Rate, latest (needs a watch) | `value` (bpm) |
| `bedtime`, `wake_time` | Sleep, first start and last end since yesterday noon | `at` (date and time) |
| `sleep_in_bed_minutes` | Minutes between bedtime and wake time | `value` |

Sleep only appears if **Sleep / Bedtime** is set up in the Health app. Without a watch, it's time in bed, not actual sleep.

## Message format

`POST https://personal-workout-strategy.vercel.app/api/ingest/health` with headers `Authorization: Bearer <connection token>` and `Content-Type: application/json`:

```json
{
  "samples": [
    { "metric": "steps", "date": "2026-10-19", "value": 8421 },
    { "metric": "weight_kg", "date": "2026-10-19", "value": 78.4 },
    { "metric": "bedtime", "date": "2026-10-20", "at": "2026-10-19T23:40:00+05:30" },
    { "metric": "sleep_in_bed_minutes", "date": "2026-10-20", "value": 455 }
  ]
}
```

- `date` is the local day the value belongs to: **yesterday** for daily totals, **today** (the morning you woke up) for sleep.
- Numbers may contain thousands separators or a unit (`"8,421"`, `"78.4 kg"`): the API takes the number and ignores the rest.
- Sending the same day again **replaces** it, so running the Shortcut twice is harmless.
- One bad or missing value doesn't lose the rest: the reply lists `saved` and `skipped` (with reasons). A `0` for weight or heart rate means "no reading" and is skipped.
- Reply `401` means the token is wrong or was replaced: create a new one in Settings.

## Part A: get your connection token

1. In the app: **profile dropdown → Settings / Profile → Apple Health → Create connection token**.
2. Keep that screen open. It shows the **token** and the **address**, each with a Copy button. The token is shown only once; if you lose it, create a new one (the old one stops working).

## Part B: build the Shortcut

Open the **Shortcuts** app → **+** → name it **Send health data**. Add these actions in order.

### 1. Dates

1. **Date** (Current Date) → **Adjust Date**: *Get Start of Day*. Long-press the result → **Rename** → `Today0`.
2. **Adjust Date**: *Subtract 1 day* from `Today0` → rename `Yesterday0`.
3. **Format Date** `Yesterday0`: Date Format *Custom*, `yyyy-MM-dd`, no time → rename `YDate`.
4. **Format Date** `Today0`: Custom `yyyy-MM-dd` → rename `TDate`.
5. **Adjust Date**: *Add 12 hours* to `Yesterday0` → rename `YesterdayNoon`.

### 2. A list to collect the samples

6. Nothing to add here: the first **Add to Variable** below (named `Samples`) creates the list.

### 3. Daily totals (repeat for each row)

For **Steps**, **Active Energy** and **Walking + Running Distance**:

7. **Find Health Samples** where *Type* is the metric, and *Start Date is between* `Yesterday0` and `Today0`.
8. **Calculate Statistics**: *Sum* of the samples.
9. **Text**: `{"metric":"steps","date":"YDate","value":Statistics}`, with `YDate` and `Statistics` inserted as variables (tap where they go and pick them). Use `active_energy_kcal` / `walking_running_km` for the other two.
10. **Add to Variable** `Samples`.

### 4. Weight and resting heart rate (only if there's a reading)

For **Weight** (and **Resting Heart Rate** if you have a watch):

11. **Find Health Samples** where *Type* is Weight and *Start Date is in the last 1 day*, *Sort by Start Date*, *Latest First*, *Limit 1*.
12. **If** *Health Samples* *has any value*:
    - **Get Details of Health Sample**: *Value* (make sure the unit is kg / bpm).
    - **Text**: `{"metric":"weight_kg","date":"YDate","value":Value}` (or `resting_hr`).
    - **Add to Variable** `Samples`.
13. **End If**.

### 5. Sleep (only if there's sleep data)

14. **Find Health Samples** where *Type* is Sleep Analysis and *Start Date is between* `YesterdayNoon` and *Current Date*, *Sort by Start Date*, *Oldest First*.
15. **If** *Health Samples* *has any value*:
    - **Get Item from List**: *First Item* → **Get Details of Health Sample**: *Start Date* → rename `Bedtime`.
    - **Get Item from List** (of the sleep samples): *Last Item* → **Get Details**: *End Date* → rename `WakeTime`.
    - **Get Time Between Dates**: `Bedtime` and `WakeTime` in *Minutes* → rename `InBed`.
    - **Format Date** `Bedtime`: *ISO 8601*, include time → `BedtimeISO`. Same for `WakeTime` → `WakeISO`.
    - **Text** (one line each, then **Add to Variable** `Samples` after each):
      - `{"metric":"bedtime","date":"TDate","at":"BedtimeISO"}`
      - `{"metric":"wake_time","date":"TDate","at":"WakeISO"}`
      - `{"metric":"sleep_in_bed_minutes","date":"TDate","value":InBed}`
16. **End If**.

### 6. Send

17. **Combine Text**: `Samples` with *Custom* separator `,` (a comma).
18. **Text**: `{"samples":[Combined Text]}`.
19. **Get Contents of URL**:
    - URL: the **address** from Part A (`https://personal-workout-strategy.vercel.app/api/ingest/health`)
    - Method: **POST**
    - Headers: `Authorization` = `Bearer ` followed by your **token** (one space after Bearer); `Content-Type` = `application/json`
    - Request Body: **File** → the Text from step 18
20. **Show Notification**: `Contents of URL` (useful while testing; remove later if you like).

### 7. Test it

21. Tap **▶** (run). The first time, iOS asks for permission to read each Health type: **Allow** them all.
22. The notification should show something like `{"saved":6,"skipped":[]}`.
23. In the app, **Settings → Apple Health** now shows "Latest data" with today's or yesterday's date.

## Part C: run it every morning

1. Shortcuts → **Automation** → **+** → **Time of Day** → **7:00**, **Daily**.
2. Choose **Run Immediately** (not "Run After Confirmation"), and turn off "Notify When Run" if you prefer.
3. Action: **Run Shortcut** → **Send health data**.

The iPhone needs to be unlocked at some point for Health data to be readable; if a morning run is missed, the next run (or a manual run) sends yesterday's data again.

## Troubleshooting

| What you see | Why | Fix |
|---|---|---|
| `{"detail":"Not signed in"}` or `401` | Token wrong, missing `Bearer `, or replaced by a newer one | Check the header; or create a new token in Settings and paste it in |
| `422` with `"samples"` | The overall message isn't valid JSON, or the list is empty | Check step 17–18: commas between items, `[` `]` around them |
| A metric in `skipped` | That value was missing or out of range (e.g. weight `0`) | Usually fine (no reading that day); otherwise check the unit (kg, km) |
| Steps look too high | Watch and phone both counted | Apple Health de-duplicates in its own totals; the Shortcut's *Sum* can double-count. Filter *Source* to the iPhone if this happens |
| Nothing arrives in the morning | Automation set to confirm, or phone locked all night | Use *Run Immediately*; run it manually to catch up |

## Related

- [Setup](setup.md): accounts and keys.
- [Architecture](architecture.md#daily-health-data): how the data is received and stored.
- [Data model](data-model.md#health-data): the `health_samples` and `ingest_tokens` tables.
- [Settings / Profile](pages/settings-profile.md): where the connection token is created.
