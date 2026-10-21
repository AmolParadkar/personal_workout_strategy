import { StyleSheet, Text, View } from 'react-native';

import { useProfile } from '@/features/profile/ProfileContext';
import { useWeekPlan } from '@/features/workouts/plans';
import { SessionCard } from '@/features/workouts/SessionCard';
import { todayLocal } from '@/lib/dates';
import { spacing, useTheme } from '@/theme';

// This week's exercises, by day and phase, above the full library
// (spec: context/pages/exercise-guide.md). Each name opens its guide.
export function WeekExercises() {
  const { colors } = useTheme();
  const { activeProfile, canEdit } = useProfile();
  const { week } = useWeekPlan(activeProfile.id, canEdit);
  const sessions = week?.active?.sessions ?? [];
  if (sessions.length === 0) return null;

  return (
    <View style={styles.section}>
      <Text style={[styles.heading, { color: colors.text }]}>This week’s exercises</Text>
      {sessions.map((session) => (
        <SessionCard
          key={session.id}
          session={session}
          canSwap={false}
          startOpen={session.day === todayLocal()}
        />
      ))}
      <Text style={[styles.heading, { color: colors.text }]}>All exercises</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: spacing.sm,
  },
  heading: {
    fontSize: 18,
    fontWeight: '700',
    marginTop: spacing.sm,
  },
});
