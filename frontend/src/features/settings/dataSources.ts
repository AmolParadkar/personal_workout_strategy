import type { Schemas } from '@/lib/api';

// "Apps and devices you use": the choices, grouped, and how each one's data
// can reach the app today. Keys must match the backend (core/models/settings.py).
// Assessment of each service: context/data-sources.md.

export type DataSource = Schemas['ProfileDetails']['data_sources'][number];

type Route = 'shortcut' | 'via_apple_health' | 'not_yet';

export const routeNotes: Record<Route, string> = {
  shortcut: 'Connected through the Apple Health Shortcut.',
  via_apple_health:
    'Can usually share its data with Apple Health (turn that on in its app); the Shortcut then picks up what it reads.',
  not_yet: 'Not connected yet. We’ll look at the options.',
};

export const dataSourceGroups: {
  title: string;
  options: { value: DataSource; label: string; route: Route }[];
}[] = [
  {
    title: 'Phone and watch',
    options: [
      { value: 'iphone_health', label: 'iPhone (Apple Health)', route: 'shortcut' },
      { value: 'apple_watch', label: 'Apple Watch', route: 'shortcut' },
      { value: 'garmin', label: 'Garmin', route: 'via_apple_health' },
      { value: 'fitbit', label: 'Fitbit', route: 'not_yet' },
      { value: 'samsung_watch', label: 'Samsung Galaxy Watch', route: 'not_yet' },
    ],
  },
  {
    title: 'Rings and bands',
    options: [
      { value: 'oura', label: 'Oura', route: 'via_apple_health' },
      { value: 'whoop', label: 'Whoop', route: 'via_apple_health' },
    ],
  },
  {
    title: 'Scales and health devices',
    options: [
      { value: 'withings', label: 'Withings', route: 'via_apple_health' },
      { value: 'other_scale', label: 'Other smart scale', route: 'not_yet' },
      { value: 'bp_monitor', label: 'Blood pressure monitor', route: 'not_yet' },
      { value: 'glucose_monitor', label: 'Glucose monitor', route: 'not_yet' },
    ],
  },
  {
    title: 'Apps',
    options: [
      { value: 'strava', label: 'Strava', route: 'via_apple_health' },
      { value: 'nike_run_club', label: 'Nike Run Club', route: 'via_apple_health' },
      { value: 'myfitnesspal', label: 'MyFitnessPal', route: 'via_apple_health' },
      { value: 'cronometer', label: 'Cronometer', route: 'via_apple_health' },
      { value: 'healthifyme', label: 'HealthifyMe', route: 'not_yet' },
    ],
  },
];

export const dataSourceInfo = new Map(
  dataSourceGroups.flatMap((group) => group.options.map((option) => [option.value, option])),
);
