import { useCallback, useEffect, useState } from 'react';

import { ApiError, apiGet, apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';

export type WeekPlan = Schemas['WeekPlan'];
export type Plan = Schemas['Plan'];
export type PlanSession = Schemas['PlanSession'];
export type PlanItem = Schemas['PlanItem'];

const GENERATING_POLL_MS = 4000;

export const PHASES: { key: PlanItem['phase']; label: string }[] = [
  { key: 'cardio', label: 'Cardio warm-up' },
  { key: 'mobility', label: 'Mobility' },
  { key: 'activation', label: 'Activation' },
  { key: 'main', label: 'Main workout' },
  { key: 'cooldown', label: 'Cooldown and stretching' },
];

// The Monday of the week a local YYYY-MM-DD date is in.
export function mondayOf(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  const day = new Date(y, m - 1, d);
  day.setDate(day.getDate() - ((day.getDay() + 6) % 7));
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

export function weekDays(monday: string): string[] {
  const [y, m, d] = monday.split('-').map(Number);
  const pad = (n: number) => String(n).padStart(2, '0');
  return Array.from({ length: 7 }, (_, offset) => {
    const day = new Date(y, m - 1, d + offset);
    return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
  });
}

export function dayLabel(isoDate: string, style: 'long' | 'short' = 'long'): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: style,
    day: 'numeric',
    month: 'short',
  });
}

// "45 s", "90 s", "3 min", "12 min".
function seconds(total: number): string {
  if (total >= 180) return `${Math.round(total / 60)} min`;
  if (total >= 60 && total % 60 === 0) return `${total / 60} min`;
  return `${total} s`;
}

// "3 × 8–12 · rest 90 s", "2 rounds × 1 min", "45 s".
export function prescription(item: PlanItem): string {
  const parts: string[] = [];
  if (item.reps_min) {
    const reps =
      item.reps_max && item.reps_max !== item.reps_min
        ? `${item.reps_min}–${item.reps_max}`
        : `${item.reps_min}`;
    parts.push(`${item.sets ?? 1} × ${reps}`);
  } else if (item.duration_seconds) {
    const each = seconds(item.duration_seconds);
    parts.push(item.sets && item.sets > 1 ? `${item.sets} × ${each}` : each);
  }
  if (item.target_load_kg) parts.push(`${item.target_load_kg} kg`);
  if (item.rest_seconds && item.phase === 'main') parts.push(`rest ${seconds(item.rest_seconds)}`);
  return parts.join(' · ');
}

// A person's plan for the week containing today, refreshed while it's being made.
export function useWeekPlan(profileId: string, isOwn: boolean) {
  const weekStart = mondayOf(todayLocal());
  const [loaded, setLoaded] = useState<{ key: string; week: WeekPlan } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${profileId}|${weekStart}`;
  const week = loaded?.key === key ? loaded.week : null;

  const load = useCallback(
    () =>
      apiGet<WeekPlan>(`/api/profiles/${profileId}/workout-plan?week_start=${weekStart}`).then(
        (next) => setLoaded({ key: `${profileId}|${weekStart}`, week: next }),
      ),
    [profileId, weekStart],
  );

  // First load; on your own profile, make the week's plan if there isn't one.
  useEffect(() => {
    let cancelled = false;
    // Your own: wait for the shared "make it if missing" request first.
    (isOwn ? ensureWeekPlan() : Promise.resolve())
      .then(() =>
        apiGet<WeekPlan>(`/api/profiles/${profileId}/workout-plan?week_start=${weekStart}`),
      )
      .then((found) => {
        if (!cancelled) setLoaded({ key, week: found });
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Couldn’t load the plan.');
      });
    return () => {
      cancelled = true;
    };
  }, [key, profileId, weekStart, isOwn]);

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
    setWeek: (next: WeekPlan) => setLoaded({ key, week: next }),
  };
}

// "Make this week's plan if there isn't one": one request per day, shared by the
// app-open check and the Workout Plan page, so they never make two plans at once.
let ensuring: { day: string; request: Promise<unknown> } | null = null;

export function ensureWeekPlan(): Promise<unknown> {
  const today = todayLocal();
  if (ensuring?.day !== today) {
    ensuring = {
      day: today,
      request: apiPost('/api/me/workout-plan/generate', { today, reason: 'new_week' }).catch(
        () => {},
      ),
    };
  }
  return ensuring.request;
}

// When the app opens: if this week has no plan yet, make one (your own profile).
// Runs in the background; the Workout Plan page shows it when it's ready.
export function useEnsureWeekPlanOnOpen() {
  useEffect(() => {
    ensureWeekPlan();
  }, []);
}
