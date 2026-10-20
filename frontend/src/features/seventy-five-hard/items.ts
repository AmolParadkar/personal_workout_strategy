import type { Schemas } from '@/lib/api';

export type Item = Schemas['ChecklistItem']['item'];

// Labels for the six daily 75 Hard rules. Keys must match the backend
// (core/models/seventy_five_hard.py).
export const itemLabels: Record<Item, { label: string; hint: string }> = {
  diet: { label: 'Followed the diet', hint: 'No cheat meals, no alcohol' },
  workout_1: { label: 'Workout 1', hint: '45 minutes' },
  workout_2_outdoor: { label: 'Workout 2, outdoors', hint: '45 minutes, outside' },
  water: { label: 'Drank a gallon of water', hint: 'About 3.8 litres' },
  reading: { label: 'Read 10 pages', hint: 'Non-fiction' },
  photo: { label: 'Took a progress photo', hint: '' },
};

export function formatDay(isoDate: string): string {
  // Dates from the API are plain dates; parse as local so they don't shift a day.
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}
