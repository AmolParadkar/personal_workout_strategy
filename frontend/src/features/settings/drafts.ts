import type { Schemas } from '@/lib/api';

// A "draft" is what's in the form while editing: numbers are kept as text
// until saved, and single choices are 0-or-1-item lists (for ChipSelect).
// Converters below turn drafts into API updates and list any problems.

type Settings = Schemas['ProfileSettings'];
type Profile = Schemas['ProfileDetails'];
type Training = Schemas['TrainingPreferences'];
type Diet = Schemas['DietPreferences'];

export type AboutDraft = {
  display_name: string;
  date_of_birth: string;
  sex: NonNullable<Profile['sex']>[];
  height_cm: string;
  goals: Profile['goals'];
  goals_notes: string;
  goal_metric: NonNullable<Profile['goal_metric']>[];
  injuries_notes: string;
};

export type TrainingDraft = {
  equipment: Training['equipment'];
  available_days: Training['available_days'];
  minutes_per_session: string;
  location: NonNullable<Training['location']>[];
};

export type DietDraft = {
  diet_type: NonNullable<Diet['diet_type']>[];
  cuisines: string;
  allergies: string;
  dislikes: string;
  meals_per_day: string;
  cooking_minutes: string;
};

export type DisplayDraft = Schemas['DisplaySettings'];

export type Converted<T> = { values: T; problems: string[] };

const text = (value: string | number | null | undefined) => (value == null ? '' : String(value));
const one = <T>(value: T | null | undefined): T[] => (value == null ? [] : [value]);
const tags = (value: string[]) => value.join(', ');
const splitTags = (value: string) =>
  value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
const orNull = (value: string) => (value.trim() === '' ? null : value.trim());

export function aboutDraft(settings: Settings): AboutDraft {
  const p = settings.profile;
  return {
    display_name: p.display_name,
    date_of_birth: text(p.date_of_birth),
    sex: one(p.sex),
    height_cm: text(p.height_cm),
    goals: p.goals,
    goals_notes: text(p.goals_notes),
    goal_metric: one(p.goal_metric),
    injuries_notes: text(p.injuries_notes),
  };
}

export function trainingDraft(settings: Settings): TrainingDraft {
  const t = settings.training;
  return {
    equipment: t.equipment,
    available_days: t.available_days,
    minutes_per_session: text(t.minutes_per_session),
    location: one(t.location),
  };
}

export function dietDraft(settings: Settings): DietDraft {
  const d = settings.diet;
  return {
    diet_type: one(d.diet_type),
    cuisines: tags(d.cuisines),
    allergies: tags(d.allergies),
    dislikes: tags(d.dislikes),
    meals_per_day: text(d.meals_per_day),
    cooking_minutes: text(d.cooking_minutes),
  };
}

// Parses a whole number (or decimal) within a range; records a problem otherwise.
function number(
  raw: string,
  label: string,
  min: number,
  max: number,
  problems: string[],
  { decimal = false, required = false } = {},
): number | null {
  if (raw.trim() === '') {
    if (required) problems.push(`${label} is required.`);
    return null;
  }
  const value = Number(raw);
  if (!Number.isFinite(value) || (!decimal && !Number.isInteger(value))) {
    problems.push(`${label} must be a ${decimal ? 'number' : 'whole number'}.`);
    return null;
  }
  if (value < min || value > max) {
    problems.push(`${label} must be between ${min} and ${max}.`);
    return null;
  }
  return value;
}

function need(condition: boolean, message: string, problems: string[]) {
  if (!condition) problems.push(message);
}

export function aboutUpdate(
  draft: AboutDraft,
  requireAll: boolean,
): Converted<Schemas['ProfileDetailsUpdate']> {
  const problems: string[] = [];
  need(draft.display_name.trim() !== '', 'Name is required.', problems);
  const dob = draft.date_of_birth.trim();
  if (dob !== '' && !/^\d{4}-\d{2}-\d{2}$/.test(dob)) {
    problems.push('Date of birth must look like 1990-05-21.');
  }
  if (requireAll) {
    need(dob !== '', 'Date of birth is required.', problems);
    need(draft.sex.length > 0, 'Choose a sex.', problems);
    need(draft.goals.length > 0, 'Choose at least one goal.', problems);
    need(draft.goal_metric.length > 0, 'Choose the metric you care about most.', problems);
  }
  const height = number(draft.height_cm, 'Height', 50, 260, problems, {
    decimal: true,
    required: requireAll,
  });
  return {
    problems,
    values: {
      display_name: draft.display_name.trim(),
      date_of_birth: dob === '' ? null : dob,
      sex: draft.sex[0] ?? null,
      height_cm: height,
      goals: draft.goals,
      goals_notes: orNull(draft.goals_notes),
      goal_metric: draft.goal_metric[0] ?? null,
      injuries_notes: orNull(draft.injuries_notes),
    },
  };
}

export function trainingUpdate(
  draft: TrainingDraft,
  requireAll: boolean,
): Converted<Schemas['TrainingPreferencesUpdate']> {
  const problems: string[] = [];
  if (requireAll) {
    need(draft.available_days.length > 0, 'Choose at least one training day.', problems);
    need(draft.location.length > 0, 'Choose where you usually train.', problems);
  }
  const minutes = number(draft.minutes_per_session, 'Minutes per session', 5, 300, problems, {
    required: requireAll,
  });
  return {
    problems,
    values: {
      equipment: draft.equipment,
      available_days: draft.available_days,
      minutes_per_session: minutes,
      location: draft.location[0] ?? null,
    },
  };
}

export function dietUpdate(
  draft: DietDraft,
  requireAll: boolean,
): Converted<Schemas['DietPreferencesUpdate']> {
  const problems: string[] = [];
  if (requireAll) need(draft.diet_type.length > 0, 'Choose a diet type.', problems);
  const meals = number(draft.meals_per_day, 'Meals per day', 1, 8, problems, {
    required: requireAll,
  });
  const cooking = number(draft.cooking_minutes, 'Cooking time', 0, 240, problems);
  return {
    problems,
    values: {
      diet_type: draft.diet_type[0] ?? null,
      cuisines: splitTags(draft.cuisines),
      allergies: splitTags(draft.allergies),
      dislikes: splitTags(draft.dislikes),
      meals_per_day: meals,
      cooking_minutes: cooking,
    },
  };
}
