import type { Slug } from 'react-native-body-highlighter';

// The library's muscle names (free-exercise-db) and how to show them.
export const muscles = [
  'abdominals',
  'abductors',
  'adductors',
  'biceps',
  'calves',
  'chest',
  'forearms',
  'glutes',
  'hamstrings',
  'lats',
  'lower back',
  'middle back',
  'neck',
  'quadriceps',
  'shoulders',
  'traps',
  'triceps',
] as const;

export type Muscle = (typeof muscles)[number];

export const muscleLabel = (muscle: string) => muscle.charAt(0).toUpperCase() + muscle.slice(1);

// Where each muscle is on the body map. The map has no separate lats, middle
// back or hip abductors, so those light up the nearest region.
const BODY_MAP: Record<Muscle, Slug[]> = {
  abdominals: ['abs', 'obliques'],
  abductors: ['gluteal'],
  adductors: ['adductors'],
  biceps: ['biceps'],
  calves: ['calves'],
  chest: ['chest'],
  forearms: ['forearm'],
  glutes: ['gluteal'],
  hamstrings: ['hamstring'],
  lats: ['upper-back'],
  'lower back': ['lower-back'],
  'middle back': ['upper-back'],
  neck: ['neck'],
  quadriceps: ['quadriceps'],
  shoulders: ['deltoids'],
  traps: ['trapezius'],
  triceps: ['triceps'],
};

// Body map data: primary muscles at intensity 1 (dark red), secondary at 2 (light red).
export function bodyMapData(primary: string[], secondary: string[]) {
  const slugsFor = (names: string[]) => names.flatMap((name) => BODY_MAP[name as Muscle] ?? []);
  const primarySlugs = new Set(slugsFor(primary));
  const secondarySlugs = new Set(slugsFor(secondary).filter((slug) => !primarySlugs.has(slug)));
  return [
    ...[...primarySlugs].map((slug) => ({ slug, intensity: 1 })),
    ...[...secondarySlugs].map((slug) => ({ slug, intensity: 2 })),
  ];
}

export const equipmentOptions = [
  'body only',
  'dumbbell',
  'barbell',
  'kettlebells',
  'bands',
  'cable',
  'machine',
  'medicine ball',
  'exercise ball',
  'foam roll',
  'e-z curl bar',
  'other',
] as const;
