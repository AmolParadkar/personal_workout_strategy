import type { Schemas } from '@/lib/api';

// Labels for every fixed choice on the Settings page and the welcome steps.
// The values must match the backend models (core/models/settings.py).

type Option<T extends string> = { value: T; label: string };

type Profile = Schemas['ProfileDetails'];
type Training = Schemas['TrainingPreferences'];
type Diet = Schemas['DietPreferences'];

export const sexOptions: Option<NonNullable<Profile['sex']>>[] = [
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
];

export const goalOptions: Option<Profile['goals'][number]>[] = [
  { value: 'lose_fat', label: 'Lose fat' },
  { value: 'build_muscle', label: 'Build muscle' },
  { value: 'get_stronger', label: 'Get stronger' },
  { value: 'endurance', label: 'Improve endurance' },
  { value: 'general_health', label: 'General health' },
  { value: 'mobility', label: 'Flexibility & mobility' },
];

export const goalMetricOptions: Option<NonNullable<Profile['goal_metric']>>[] = [
  { value: 'weight', label: 'Body weight' },
  { value: 'body_fat', label: 'Body fat %' },
  { value: 'vo2_max', label: 'VO₂ max' },
  { value: 'resting_hr', label: 'Resting heart rate' },
  { value: 'hrv', label: 'HRV' },
  { value: 'strength', label: 'Strength (lifts)' },
  { value: 'steps', label: 'Daily steps' },
  { value: 'sleep', label: 'Sleep' },
];

export const dayOptions: Option<Training['available_days'][number]>[] = [
  { value: 'mon', label: 'Mon' },
  { value: 'tue', label: 'Tue' },
  { value: 'wed', label: 'Wed' },
  { value: 'thu', label: 'Thu' },
  { value: 'fri', label: 'Fri' },
  { value: 'sat', label: 'Sat' },
  { value: 'sun', label: 'Sun' },
];

export const locationOptions: Option<NonNullable<Training['location']>>[] = [
  { value: 'home', label: 'Home' },
  { value: 'gym', label: 'Gym' },
  { value: 'travel', label: 'Travelling' },
];

export const equipmentOptions: Option<Training['equipment'][number]>[] = [
  { value: 'bodyweight', label: 'Bodyweight only' },
  { value: 'dumbbells', label: 'Dumbbells' },
  { value: 'barbell', label: 'Barbell' },
  { value: 'kettlebell', label: 'Kettlebell' },
  { value: 'resistance_bands', label: 'Resistance bands' },
  { value: 'pull_up_bar', label: 'Pull-up bar' },
  { value: 'bench', label: 'Bench' },
  { value: 'cable_machine', label: 'Cable machine' },
  { value: 'treadmill', label: 'Treadmill' },
  { value: 'exercise_bike', label: 'Exercise bike' },
  { value: 'rowing_machine', label: 'Rowing machine' },
  { value: 'full_gym', label: 'Full gym' },
];

export const dietTypeOptions: Option<NonNullable<Diet['diet_type']>>[] = [
  { value: 'vegetarian', label: 'Vegetarian' },
  { value: 'eggetarian', label: 'Eggetarian' },
  { value: 'non_vegetarian', label: 'Non-vegetarian' },
];
