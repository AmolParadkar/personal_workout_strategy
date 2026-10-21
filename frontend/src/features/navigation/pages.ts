import type { Href } from 'expo-router';

// The single list of pages in the app. The navigation bar and the
// placeholder screens both read from here, so a page is added in one place.
// Specs for each page live in context/pages/.

export type PageKey =
  | 'summary'
  | 'today'
  | 'workoutPlan'
  | 'nutritionPlan'
  | 'progress'
  | 'seventyFiveHard'
  | 'exerciseGuide'
  | 'artifacts'
  | 'settings';

export type PageInfo = {
  title: string;
  href: Href;
  description: string;
  milestone: string;
  // Hidden from the navigation bar (Settings is reached from the profile dropdown).
  hiddenFromNav?: boolean;
  // Shown on your own profile, and on the other person's only while they're doing 75 Hard.
  requires75Hard?: boolean;
};

export const pages: Record<PageKey, PageInfo> = {
  summary: {
    title: 'Summary',
    href: '/',
    description: 'How am I doing right now? A read-only dashboard.',
    milestone: 'M8',
  },
  today: {
    title: 'Plan for Today',
    href: '/today',
    description: "Today's workout and meals, plus logging for meals, water and medications.",
    milestone: 'M6–M7',
  },
  workoutPlan: {
    title: 'Workout Plan',
    href: '/workout-plan',
    description: 'The weekly workout plan, which you can change.',
    milestone: 'M6',
  },
  nutritionPlan: {
    title: 'Nutrition Plan',
    href: '/nutrition-plan',
    description: 'The weekly meal plan with macro and micronutrient targets.',
    milestone: 'M7',
  },
  progress: {
    title: 'Progress',
    href: '/progress',
    description: 'Trends, forecasts, what-if simulator and disruption planning.',
    milestone: 'M10',
  },
  seventyFiveHard: {
    title: '75 Hard',
    href: '/75-hard',
    description: 'Daily 75 Hard checklist and day counter.',
    milestone: 'M2',
    requires75Hard: true,
  },
  exerciseGuide: {
    title: 'Exercise Guide',
    href: '/exercises',
    description: 'How to do each exercise: muscles worked, form cues, precautions and a video.',
    milestone: 'M5',
  },
  artifacts: {
    title: 'Personal Artifacts',
    href: '/artifacts',
    description: 'Upload health documents; confirmed facts adjust your plans.',
    milestone: 'M9',
  },
  settings: {
    title: 'Settings / Profile',
    href: '/settings',
    description: 'Your personal details and which cards appear on the Summary.',
    milestone: 'M1',
    hiddenFromNav: true,
  },
};

// Order of the links in the navigation bar.
export const navOrder: PageKey[] = [
  'summary',
  'today',
  'workoutPlan',
  'nutritionPlan',
  'progress',
  'seventyFiveHard',
  'exerciseGuide',
  'artifacts',
];
