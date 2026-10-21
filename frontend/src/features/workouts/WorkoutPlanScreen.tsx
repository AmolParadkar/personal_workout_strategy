import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { BodyWeightSection } from '@/features/settings/BodyWeightSection';
import { useProfileSettings } from '@/features/settings/useProfileSettings';
import { ApiError, apiDelete, apiPost } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import { Coverage } from './Coverage';
import { dayLabel, type Plan, useWeekPlan, type WeekPlan, weekDays } from './plans';
import { SessionCard } from './SessionCard';

// The week's workout plan (spec: context/pages/workout-plan.md): made
// automatically for a new week, with a preview before a new plan replaces it.
export function WorkoutPlanScreen() {
  const { colors } = useTheme();
  const { activeProfile, canEdit } = useProfile();
  const { week, weekStart, error, setWeek } = useWeekPlan(activeProfile.id, canEdit);
  const { state: settings } = useProfileSettings(activeProfile.id);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const gender =
    settings.status === 'ready' && settings.settings.profile.sex === 'female' ? 'female' : 'male';

  const act = async (request: () => Promise<WeekPlan>) => {
    setBusy(true);
    setActionError(null);
    try {
      setWeek(await request());
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const makeNew = () =>
    act(() =>
      apiPost<WeekPlan>('/api/me/workout-plan/generate', {
        today: todayLocal(),
        reason: 'requested',
      }),
    );

  const muted = { color: colors.textMuted };
  const text = { color: colors.text };
  const days = weekDays(weekStart);

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: colors.primary }]}>
          {activeProfile.display_name.toUpperCase()}
        </Text>
        <Text style={[styles.title, text]}>{pages.workoutPlan.title}</Text>
        <Text style={[styles.description, muted]}>
          {dayLabel(days[0], 'short')} – {dayLabel(days[6], 'short')}
          {canEdit ? '' : ` · ${activeProfile.display_name}’s plan (view-only)`}
        </Text>

        {error && <Text style={{ color: colors.alert }}>{error}</Text>}
        {!week && !error && <ActivityIndicator color={colors.primary} />}

        {week?.generating && (
          <View
            style={[styles.notice, { borderColor: colors.border, backgroundColor: colors.surface }]}
          >
            <ActivityIndicator color={colors.primary} />
            <Text style={[styles.body, text]}>
              Making {week.active ? 'a new plan' : 'this week’s plan'}… This page updates by itself.
            </Text>
          </View>
        )}

        {week?.draft && (
          <View
            style={[
              styles.preview,
              { borderColor: colors.primary, backgroundColor: colors.surface },
            ]}
          >
            <Text style={[styles.sectionTitle, text]}>New plan ready to preview</Text>
            <Text style={[styles.body, muted]}>{week.draft.rationale}</Text>
            <Changes current={week.active} next={week.draft} />
            {week.draft.sessions.map((session) => (
              <SessionCard key={session.id} session={session} canSwap={false} />
            ))}
            <View style={styles.row}>
              <Button
                label="Use this plan"
                onPress={() =>
                  act(() => apiPost<WeekPlan>(`/api/me/workout-plans/${week.draft!.id}/apply`))
                }
                disabled={busy}
              />
              <Button
                label="Keep current plan"
                variant="secondary"
                onPress={() =>
                  act(() => apiDelete<WeekPlan>(`/api/me/workout-plans/${week.draft!.id}`))
                }
                disabled={busy}
              />
            </View>
          </View>
        )}

        {week && !week.active && !week.generating && (
          <Text style={[styles.body, muted]}>
            {canEdit
              ? 'No plan for this week yet.'
              : `${activeProfile.display_name} has no plan for this week yet.`}
          </Text>
        )}

        {week?.active && (
          <>
            <Text style={[styles.body, text]}>{week.active.rationale}</Text>
            <Text style={[styles.caption, muted]}>
              {week.active.made_by === 'rules'
                ? 'Made by the app’s rules (the AI wasn’t available).'
                : 'Exercises chosen by AI from your equipment and settings.'}{' '}
              Tap a day to see its exercises.
            </Text>
            {days.map((day) => {
              const session = week.active!.sessions.find((s) => s.day === day);
              return session ? (
                <SessionCard
                  key={day}
                  session={session}
                  canSwap={canEdit}
                  onSwapped={setWeek}
                  startOpen={day === todayLocal()}
                />
              ) : (
                <View key={day} style={[styles.rest, { borderColor: colors.border }]}>
                  <Text style={[styles.restText, muted]}>{dayLabel(day)} · Rest</Text>
                </View>
              );
            })}
            <Coverage plan={week.active} gender={gender} />
          </>
        )}

        {canEdit && week && !week.generating && (
          <View style={styles.row}>
            <Button label="Make a new plan" variant="secondary" onPress={makeNew} disabled={busy} />
          </View>
        )}
        {actionError && <Text style={{ color: colors.alert }}>{actionError}</Text>}

        <BodyWeightSection profileId={activeProfile.id} />
      </View>
    </ScrollView>
  );
}

// What moves when the new plan replaces the current one, e.g. "Wed: Upper body → Lower body".
function Changes({ current, next }: { current: Plan | null; next: Plan }) {
  const { colors } = useTheme();
  if (!current) return null;
  const lines: string[] = [];
  const days = new Set([...current.sessions, ...next.sessions].map((s) => s.day));
  for (const day of [...days].sort()) {
    const before = current.sessions.find((s) => s.day === day)?.title ?? 'Rest';
    const after = next.sessions.find((s) => s.day === day)?.title ?? 'Rest';
    if (before !== after) lines.push(`${dayLabel(day, 'short')}: ${before} → ${after}`);
  }
  return (
    <Text style={[styles.body, { color: colors.text }]}>
      {lines.length
        ? `What changes: ${lines.join('; ')}.`
        : 'Same days and session types, with different exercises.'}
    </Text>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.lg,
  },
  content: {
    width: '100%',
    maxWidth: 760,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    gap: spacing.md,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  description: {
    fontSize: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  caption: {
    fontSize: 13,
    lineHeight: 18,
  },
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  preview: {
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 2,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  rest: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
  },
  restText: {
    fontSize: 14,
  },
});
