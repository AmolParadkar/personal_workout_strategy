import { StyleSheet, Text, View } from 'react-native';

import { ChipSelect, Field, TextField, ToggleRow } from '@/components/form';
import { spacing, useTheme } from '@/theme';

import { dataSourceGroups, dataSourceInfo, routeNotes } from './dataSources';
import type {
  AboutDraft,
  DietDraft,
  DisplayDraft,
  SourcesDraft,
  TrainingDraft,
  WaterDraft,
} from './drafts';
import {
  dayOptions,
  dietTypeOptions,
  equipmentOptions,
  experienceOptions,
  goalMetricOptions,
  goalOptions,
  locationOptions,
  sexOptions,
} from './options';

// The fields for each section, shared by the Settings page and the welcome steps.

type Props<T> = {
  draft: T;
  onChange: (changes: Partial<T>) => void;
  disabled?: boolean;
};

export function AboutYouFields({ draft, onChange, disabled }: Props<AboutDraft>) {
  return (
    <View style={styles.fields}>
      <Field label="Name" required>
        <TextField
          label="Name"
          value={draft.display_name}
          onChange={(display_name) => onChange({ display_name })}
          disabled={disabled}
        />
      </Field>
      <Field label="Date of birth" hint="Year-month-day, e.g. 1990-05-21" required>
        <TextField
          label="Date of birth"
          value={draft.date_of_birth}
          onChange={(date_of_birth) => onChange({ date_of_birth })}
          placeholder="YYYY-MM-DD"
          disabled={disabled}
        />
      </Field>
      <Field label="Sex" hint="Used for calorie and nutrient targets." required>
        <ChipSelect
          options={sexOptions}
          selected={draft.sex}
          onChange={(sex) => onChange({ sex })}
          disabled={disabled}
        />
      </Field>
      <Field label="Height (cm)" required>
        <TextField
          label="Height in centimetres"
          value={draft.height_cm}
          onChange={(height_cm) => onChange({ height_cm })}
          inputMode="decimal"
          disabled={disabled}
        />
      </Field>
      <Field label="Goals" hint="Choose all that apply." required>
        <ChipSelect
          options={goalOptions}
          selected={draft.goals}
          onChange={(goals) => onChange({ goals })}
          multiple
          disabled={disabled}
        />
      </Field>
      <Field label="Anything else about your goals?">
        <TextField
          label="Goal notes"
          value={draft.goals_notes}
          onChange={(goals_notes) => onChange({ goals_notes })}
          placeholder="e.g. run a 10K in March"
          multiline
          disabled={disabled}
        />
      </Field>
      <Field
        label="The one metric you care about most"
        hint="Shown as your goal card on the Summary."
        required
      >
        <ChipSelect
          options={goalMetricOptions}
          selected={draft.goal_metric}
          onChange={(goal_metric) => onChange({ goal_metric })}
          disabled={disabled}
        />
      </Field>
      <Field label="Injuries or limitations" hint="So plans avoid what could hurt you.">
        <TextField
          label="Injuries or limitations"
          value={draft.injuries_notes}
          onChange={(injuries_notes) => onChange({ injuries_notes })}
          placeholder="e.g. knee pain on deep squats"
          multiline
          disabled={disabled}
        />
      </Field>
    </View>
  );
}

export function TrainingFields({ draft, onChange, disabled }: Props<TrainingDraft>) {
  return (
    <View style={styles.fields}>
      <Field label="Days you can train" required>
        <ChipSelect
          options={dayOptions}
          selected={draft.available_days}
          onChange={(available_days) => onChange({ available_days })}
          multiple
          disabled={disabled}
        />
      </Field>
      <Field label="Minutes per session" required>
        <TextField
          label="Minutes per session"
          value={draft.minutes_per_session}
          onChange={(minutes_per_session) => onChange({ minutes_per_session })}
          inputMode="numeric"
          placeholder="e.g. 60"
          disabled={disabled}
        />
      </Field>
      <Field label="Where you usually train" required>
        <ChipSelect
          options={locationOptions}
          selected={draft.location}
          onChange={(location) => onChange({ location })}
          disabled={disabled}
        />
      </Field>
      <Field
        label="Training experience"
        hint="Beginner: under a year of regular training. Sets how hard the exercises are and the starting volume."
      >
        <ChipSelect
          options={experienceOptions}
          selected={draft.experience}
          onChange={(experience) => onChange({ experience })}
          disabled={disabled}
        />
      </Field>
      <Field label="Equipment you have" hint="Choose all that apply.">
        <ChipSelect
          options={equipmentOptions}
          selected={draft.equipment}
          onChange={(equipment) => onChange({ equipment })}
          multiple
          disabled={disabled}
        />
      </Field>
    </View>
  );
}

export function FoodFields({ draft, onChange, disabled }: Props<DietDraft>) {
  return (
    <View style={styles.fields}>
      <Field label="Diet type" required>
        <ChipSelect
          options={dietTypeOptions}
          selected={draft.diet_type}
          onChange={(diet_type) => onChange({ diet_type })}
          disabled={disabled}
        />
      </Field>
      <Field label="Meals per day" required>
        <TextField
          label="Meals per day"
          value={draft.meals_per_day}
          onChange={(meals_per_day) => onChange({ meals_per_day })}
          inputMode="numeric"
          placeholder="e.g. 4"
          disabled={disabled}
        />
      </Field>
      <Field label="Cooking time per meal (minutes)">
        <TextField
          label="Cooking time per meal in minutes"
          value={draft.cooking_minutes}
          onChange={(cooking_minutes) => onChange({ cooking_minutes })}
          inputMode="numeric"
          placeholder="e.g. 30"
          disabled={disabled}
        />
      </Field>
      <Field label="Cuisines you enjoy" hint="Separate with commas.">
        <TextField
          label="Cuisines you enjoy"
          value={draft.cuisines}
          onChange={(cuisines) => onChange({ cuisines })}
          placeholder="e.g. Indian, Mediterranean"
          disabled={disabled}
        />
      </Field>
      <Field label="Allergies" hint="Separate with commas.">
        <TextField
          label="Allergies"
          value={draft.allergies}
          onChange={(allergies) => onChange({ allergies })}
          placeholder="e.g. peanuts"
          disabled={disabled}
        />
      </Field>
      <Field label="Foods you dislike" hint="Separate with commas.">
        <TextField
          label="Foods you dislike"
          value={draft.dislikes}
          onChange={(dislikes) => onChange({ dislikes })}
          placeholder="e.g. mushrooms, okra"
          disabled={disabled}
        />
      </Field>
    </View>
  );
}

export function WaterFields({ draft, onChange, disabled }: Props<WaterDraft>) {
  return (
    <View style={styles.fields}>
      <Field label="Daily water target (ml)" hint="3000 ml = 3 litres. The 75 Hard gallon is 3785 ml." required>
        <TextField
          label="Daily water target in millilitres"
          value={draft.water_target_ml}
          onChange={(water_target_ml) => onChange({ water_target_ml })}
          inputMode="numeric"
          disabled={disabled}
        />
      </Field>
    </View>
  );
}

export function SourcesFields({ draft, onChange, disabled }: Props<SourcesDraft>) {
  const { colors } = useTheme();
  return (
    <View style={styles.fields}>
      {dataSourceGroups.map((group) => (
        <Field key={group.title} label={group.title}>
          <ChipSelect
            options={group.options}
            // Each group shows only its own choices but saves into one shared list.
            selected={draft.data_sources.filter((s) => group.options.some((o) => o.value === s))}
            onChange={(selectedInGroup) =>
              onChange({
                data_sources: [
                  ...draft.data_sources.filter((s) => !group.options.some((o) => o.value === s)),
                  ...selectedInGroup,
                ],
              })
            }
            multiple
            disabled={disabled}
          />
        </Field>
      ))}
      <Field label="Anything else?" hint="Other apps or devices you use.">
        <TextField
          label="Other apps or devices"
          value={draft.data_sources_other}
          onChange={(data_sources_other) => onChange({ data_sources_other })}
          placeholder="e.g. Cult.fit"
          disabled={disabled}
        />
      </Field>
      {draft.data_sources.length > 0 && (
        <View style={styles.notes}>
          <Text style={[styles.notesTitle, { color: colors.text }]}>How each one connects</Text>
          {draft.data_sources.map((source) => {
            const info = dataSourceInfo.get(source);
            if (!info) return null;
            return (
              <Text key={source} style={[styles.note, { color: colors.textMuted }]}>
                <Text style={{ color: colors.text, fontWeight: '600' }}>{info.label}: </Text>
                {routeNotes[info.route]}
              </Text>
            );
          })}
        </View>
      )}
    </View>
  );
}

export function DisplayFields({ draft, onChange, disabled }: Props<DisplayDraft>) {
  return (
    <View style={styles.fields}>
      <ToggleRow
        label="Show body weight"
        hint="Adds a weight card to the Summary and charts on Progress."
        value={draft.show_weight}
        onChange={(show_weight) => onChange({ show_weight })}
        disabled={disabled}
      />
      <ToggleRow
        label="Show calories eaten"
        value={draft.show_calorie_intake}
        onChange={(show_calorie_intake) => onChange({ show_calorie_intake })}
        disabled={disabled}
      />
      <ToggleRow
        label="Show calories burned"
        value={draft.show_calories_burned}
        onChange={(show_calories_burned) => onChange({ show_calories_burned })}
        disabled={disabled}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fields: {
    gap: spacing.lg,
  },
  notes: {
    gap: spacing.xs + 2,
  },
  notesTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  note: {
    fontSize: 13,
    lineHeight: 18,
  },
});
