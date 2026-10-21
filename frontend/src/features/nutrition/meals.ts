import { useCallback, useEffect, useState } from 'react';

import { ensureWeekPlan, mondayOf } from '@/features/workouts/plans';
import { ApiError, apiGet, apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';

export type WeekMealPlan = Schemas['WeekMealPlan'];
export type MealPlan = Schemas['MealPlan'];
export type MealDay = Schemas['MealDay'];
export type PlannedMeal = Schemas['PlannedMeal'];
export type FoodOption = Schemas['FoodOption'];
export type GroceryList = Schemas['GroceryList'];

const GENERATING_POLL_MS = 4000;

export const SLOT_LABELS: Record<PlannedMeal['slot'], string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  dinner: 'Dinner',
  snack: 'Snack',
};

// Micronutrients shown with the targets (sodium is an upper limit).
export const MICROS: {
  key: string;
  label: string;
  unit: string;
  limit?: boolean;
}[] = [
  { key: 'iron_mg', label: 'Iron', unit: 'mg' },
  { key: 'calcium_mg', label: 'Calcium', unit: 'mg' },
  { key: 'vitamin_d_ug', label: 'Vitamin D', unit: 'µg' },
  { key: 'magnesium_mg', label: 'Magnesium', unit: 'mg' },
  { key: 'potassium_mg', label: 'Potassium', unit: 'mg' },
  { key: 'zinc_mg', label: 'Zinc', unit: 'mg' },
  { key: 'vitamin_c_mg', label: 'Vitamin C', unit: 'mg' },
  { key: 'vitamin_a_ug', label: 'Vitamin A', unit: 'µg' },
  { key: 'folate_ug', label: 'Folate', unit: 'µg' },
  { key: 'sodium_mg', label: 'Sodium', unit: 'mg', limit: true },
];

// A person's meal plan for the week containing today, refreshed while it's made.
export function useWeekMealPlan(profileId: string, isOwn: boolean) {
  const weekStart = mondayOf(todayLocal());
  const [loaded, setLoaded] = useState<{
    key: string;
    week: WeekMealPlan;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${profileId}|${weekStart}`;
  const week = loaded?.key === key ? loaded.week : null;
  const path = `/api/profiles/${profileId}/meal-plan?week_start=${weekStart}`;

  const load = useCallback(
    () => apiGet<WeekMealPlan>(path).then((next) => setLoaded({ key, week: next })),
    [path, key],
  );

  useEffect(() => {
    let cancelled = false;
    // Your own: wait for the shared "make it if missing" request first.
    (isOwn ? ensureMealPlan() : Promise.resolve())
      .then(() => apiGet<WeekMealPlan>(path))
      .then((found) => {
        if (!cancelled) setLoaded({ key, week: found });
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Couldn’t load the plan.');
      });
    return () => {
      cancelled = true;
    };
  }, [key, path, isOwn]);

  // While the Mac worker makes it, check back every few seconds.
  useEffect(() => {
    if (!week?.generating) return;
    const timer = setTimeout(() => {
      load().catch(() => {});
    }, GENERATING_POLL_MS);
    return () => clearTimeout(timer);
  }, [week, load]);

  return {
    week,
    weekStart,
    error,
    setWeek: (next: WeekMealPlan) => setLoaded({ key, week: next }),
  };
}

// "Make this week's meal plan if there isn't one": once a day, after the workout
// plan (meals follow its training days), shared by the app-open check and the page.
let ensuring: { day: string; request: Promise<unknown> } | null = null;

export function ensureMealPlan(): Promise<unknown> {
  const today = todayLocal();
  if (ensuring?.day !== today) {
    ensuring = {
      day: today,
      request: ensureWeekPlan()
        .then(() => apiPost('/api/me/meal-plan/generate', { today, reason: 'new_week' }))
        .catch(() => {}),
    };
  }
  return ensuring.request;
}

export function useEnsureMealPlanOnOpen() {
  useEffect(() => {
    ensureMealPlan();
  }, []);
}

export function kcal(value: number): string {
  return `${Math.round(value).toLocaleString()} kcal`;
}

export function grams(value: number): string {
  return `${Math.round(value)} g`;
}
