import { StyleSheet, Text, View } from 'react-native';

import { BodyMap } from '@/features/exercises/BodyMap';
import { muscleLabel } from '@/features/exercises/muscles';
import { radius, spacing, useTheme } from '@/theme';

import type { Plan } from './plans';

// Sets a week that clearly trains a muscle (about the minimum for progress).
const WELL_TRAINED = 6;
// Muscles worth noticing when they get nothing.
const MAJOR = [
  'chest',
  'lats',
  'middle back',
  'shoulders',
  'quadriceps',
  'hamstrings',
  'glutes',
  'abdominals',
];

// Weekly muscle coverage: body map, sets per muscle, and gaps
// (spec: context/pages/workout-plan.md, "Weekly muscle coverage").
export function Coverage({ plan, gender }: { plan: Plan; gender: 'male' | 'female' }) {
  const { colors } = useTheme();
  const well = plan.coverage.filter((c) => c.sets >= WELL_TRAINED).map((c) => c.muscle);
  const some = plan.coverage
    .filter((c) => c.sets > 0 && c.sets < WELL_TRAINED)
    .map((c) => c.muscle);
  const covered = new Set(plan.coverage.map((c) => c.muscle));
  const gaps = MAJOR.filter((m) => !covered.has(m));
  const most = Math.max(1, ...plan.coverage.map((c) => c.sets));

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <Text style={[styles.title, { color: colors.text }]}>Muscles this week</Text>
      <BodyMap
        primary={well}
        secondary={some}
        gender={gender}
        labels={[`${WELL_TRAINED}+ sets`, `1–${WELL_TRAINED - 1} sets`]}
      />
      <View style={styles.rows}>
        {plan.coverage.map((c) => (
          <View key={c.muscle} style={styles.row}>
            <Text style={[styles.muscle, { color: colors.text }]}>{muscleLabel(c.muscle)}</Text>
            <View style={[styles.track, { backgroundColor: colors.border }]}>
              <View
                style={[
                  styles.bar,
                  {
                    width: `${(c.sets / most) * 100}%`,
                    backgroundColor: c.sets >= WELL_TRAINED ? '#C62828' : '#EF9A9A',
                  },
                ]}
              />
            </View>
            <Text style={[styles.sets, { color: colors.textMuted }]}>{c.sets}</Text>
          </View>
        ))}
      </View>
      <Text style={[styles.note, { color: gaps.length ? colors.caution : colors.textMuted }]}>
        {gaps.length
          ? `Not trained this week: ${gaps.map(muscleLabel).join(', ')}.`
          : 'Every major muscle group gets some work this week.'}{' '}
        Working sets from the main workout and activation; secondary muscles count half.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  rows: {
    gap: spacing.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  muscle: {
    width: 110,
    fontSize: 14,
  },
  track: {
    flex: 1,
    height: 8,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  bar: {
    height: '100%',
    borderRadius: radius.pill,
  },
  sets: {
    width: 36,
    textAlign: 'right',
    fontSize: 13,
  },
  note: {
    fontSize: 13,
    lineHeight: 18,
  },
});
