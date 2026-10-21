import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

import { grams, kcal, type MealDay, MICROS } from './meals';

const OVER_IS_TOO_MUCH = new Set(['kcal', 'carbs_g', 'fat_g']);

const MACROS: {
  key: 'kcal' | 'protein_g' | 'carbs_g' | 'fat_g' | 'fibre_g';
  label: string;
}[] = [
  { key: 'kcal', label: 'Calories' },
  { key: 'protein_g', label: 'Protein' },
  { key: 'carbs_g', label: 'Carbs' },
  { key: 'fat_g', label: 'Fat' },
  { key: 'fibre_g', label: 'Fibre' },
];

// A day's targets next to what its planned meals add up to, with the one-line
// reason for each target and the micronutrients behind a toggle.
export function DayTargets({ day }: { day: MealDay }) {
  const { colors } = useTheme();
  const [why, setWhy] = useState(false);
  const [micros, setMicros] = useState(false);
  const { targets, totals } = day;
  const text = { color: colors.text };
  const muted = { color: colors.textMuted };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.headingRow}>
        <Text style={[styles.heading, text]}>Targets</Text>
        <Text style={[styles.caption, muted]}>
          {targets.training_minutes ? `Training day (${targets.training_minutes} min)` : 'Rest day'}
        </Text>
      </View>
      {MACROS.map(({ key, label }) => {
        const target = targets[key] ?? 0;
        const planned = (totals[key] as number | null) ?? 0;
        const share = target ? Math.min(planned / target, 1.3) : 0;
        const value = key === 'kcal' ? kcal : grams;
        return (
          <View key={key} style={styles.macro}>
            <View style={styles.macroRow}>
              <Text style={[styles.body, text]}>{label}</Text>
              <Text style={[styles.body, muted]}>
                {value(planned)} planned · target {value(target)}
              </Text>
            </View>
            <View
              style={[styles.track, { backgroundColor: colors.border }]}
              accessibilityRole="progressbar"
              accessibilityLabel={`${label}: ${Math.round(share * 100)}% of target`}
            >
              <View
                style={[
                  styles.fill,
                  {
                    width: `${Math.min(share, 1) * 100}%`,
                    // More protein or fibre than the target is fine; more energy isn't.
                    backgroundColor:
                      share > 1.1 && OVER_IS_TOO_MUCH.has(key) ? colors.caution : colors.primary,
                  },
                ]}
              />
            </View>
            {why && targets.reasons[key] && (
              <Text style={[styles.caption, muted]}>{targets.reasons[key]}</Text>
            )}
          </View>
        );
      })}
      <View style={styles.links}>
        <Pressable accessibilityRole="button" onPress={() => setWhy((w) => !w)}>
          <Text style={[styles.link, { color: colors.primary }]}>
            {why ? 'Hide the reasons' : 'Why these targets?'}
          </Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => setMicros((m) => !m)}>
          <Text style={[styles.link, { color: colors.primary }]}>
            {micros ? 'Hide vitamins and minerals' : 'Vitamins and minerals'}
          </Text>
        </Pressable>
      </View>
      {micros && (
        <View style={styles.micros}>
          {MICROS.map(({ key, label, unit, limit }) => {
            const target = targets.micros[limit ? `${key}_max` : key];
            if (target == null) return null;
            const planned = totals.micros[key] ?? 0;
            const off = limit ? planned > target : planned < 0.8 * target;
            return (
              <View key={key} style={styles.macroRow}>
                <Text style={[styles.body, text]}>
                  {label}
                  {limit ? ' (limit)' : ''}
                </Text>
                <Text style={[styles.body, { color: off ? colors.caution : colors.textMuted }]}>
                  {Math.round(planned).toLocaleString()} / {Math.round(target).toLocaleString()}{' '}
                  {unit}
                </Text>
              </View>
            );
          })}
          <Text style={[styles.caption, muted]}>{targets.reasons.micros}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.md,
    gap: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  headingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  heading: {
    fontSize: 16,
    fontWeight: '700',
  },
  macro: {
    gap: 4,
  },
  macroRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  track: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
  },
  fill: {
    height: 6,
    borderRadius: 3,
  },
  links: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
  micros: {
    gap: spacing.xs,
  },
  body: {
    fontSize: 14,
  },
  caption: {
    fontSize: 12,
    lineHeight: 17,
  },
});
