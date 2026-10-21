import { Link } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError, apiGet, apiPut, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import {
  dayLabel,
  PHASES,
  type PlanItem,
  type PlanSession,
  prescription,
  type WeekPlan,
} from './plans';

type Alternative = Schemas['ExerciseSummary'];

// One training day: what it is, then its five phases. On your own plan, main
// and activation exercises can be swapped for alternatives.
export function SessionCard({
  session,
  canSwap,
  onSwapped,
  startOpen = false,
}: {
  session: PlanSession;
  canSwap: boolean;
  onSwapped?: (week: WeekPlan) => void;
  startOpen?: boolean;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(startOpen);
  const text = { color: colors.text };
  const muted = { color: colors.textMuted };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <Pressable
        accessibilityRole="button"
        aria-expanded={open}
        onPress={() => setOpen((o) => !o)}
        style={styles.header}
      >
        <View style={styles.headerText}>
          <Text style={[styles.day, { color: colors.primary }]}>{dayLabel(session.day)}</Text>
          <Text style={[styles.title, text]}>{session.title}</Text>
          <Text style={[styles.body, muted]}>
            {session.minutes} min · {session.explanation}
          </Text>
        </View>
        <Text style={[styles.chevron, muted]}>{open ? '▲' : '▼'}</Text>
      </Pressable>

      {open &&
        PHASES.map((phase) => {
          const items = session.items.filter((i) => i.phase === phase.key);
          if (items.length === 0) return null;
          return (
            <View key={phase.key} style={styles.phase}>
              <Text style={[styles.phaseLabel, muted]}>{phase.label.toUpperCase()}</Text>
              {items.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  canSwap={canSwap && (item.phase === 'main' || item.phase === 'activation')}
                  onSwapped={onSwapped}
                />
              ))}
            </View>
          );
        })}
    </View>
  );
}

function ItemRow({
  item,
  canSwap,
  onSwapped,
}: {
  item: PlanItem;
  canSwap: boolean;
  onSwapped?: (week: WeekPlan) => void;
}) {
  const { colors } = useTheme();
  const [options, setOptions] = useState<Alternative[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showSwaps = async () => {
    if (options) {
      setOptions(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setOptions(await apiGet<Alternative[]>(`/api/me/session-items/${item.id}/alternatives`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t load swaps.');
    } finally {
      setBusy(false);
    }
  };

  const choose = async (exerciseId: string) => {
    setBusy(true);
    setError(null);
    try {
      const week = await apiPut<WeekPlan>(`/api/me/session-items/${item.id}/exercise`, {
        exercise_id: exerciseId,
      });
      setOptions(null);
      onSwapped?.(week);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t swap.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.item}>
      <View style={styles.itemRow}>
        <View style={styles.itemText}>
          <Link
            href={`/exercises/${item.exercise_id}`}
            style={[styles.itemName, { color: colors.text }]}
          >
            {item.exercise_name}
          </Link>
          <Text style={[styles.body, { color: colors.textMuted }]}>{prescription(item)}</Text>
        </View>
        {canSwap && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Swap ${item.exercise_name}`}
            onPress={showSwaps}
            disabled={busy}
            style={[styles.swap, { borderColor: colors.border }]}
          >
            <Text style={[styles.swapText, { color: colors.primary }]}>
              {options ? 'Close' : 'Swap'}
            </Text>
          </Pressable>
        )}
      </View>
      {busy && <ActivityIndicator color={colors.primary} />}
      {options && (
        <View style={[styles.options, { borderColor: colors.border }]}>
          <Text style={[styles.body, { color: colors.textMuted }]}>
            {options.length
              ? 'Same muscles, your equipment:'
              : 'No other exercise fits here with your equipment.'}
          </Text>
          {options.map((option) => (
            <Pressable
              key={option.id}
              accessibilityRole="button"
              onPress={() => choose(option.id)}
              disabled={busy}
              style={styles.option}
            >
              <Text style={[styles.body, { color: colors.primary, fontWeight: '600' }]}>
                {option.name}
              </Text>
              <Text style={[styles.caption, { color: colors.textMuted }]}>
                {[option.primary_muscles.join(', '), option.equipment].filter(Boolean).join(' · ')}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
      {error && <Text style={[styles.caption, { color: colors.alert }]}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.md,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  header: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  headerText: {
    flex: 1,
    gap: 2,
  },
  day: {
    fontSize: 13,
    fontWeight: '700',
  },
  title: {
    fontSize: 17,
    fontWeight: '700',
  },
  chevron: {
    fontSize: 14,
    paddingTop: spacing.xs,
  },
  phase: {
    gap: spacing.sm,
  },
  phaseLabel: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  item: {
    gap: spacing.xs,
  },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  itemText: {
    flex: 1,
    gap: 2,
  },
  itemName: {
    fontSize: 15,
    fontWeight: '600',
  },
  swap: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  swapText: {
    fontSize: 13,
    fontWeight: '700',
  },
  options: {
    gap: spacing.sm,
    padding: spacing.sm,
    borderLeftWidth: 2,
    marginLeft: spacing.xs,
  },
  option: {
    gap: 2,
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
  },
  caption: {
    fontSize: 12,
    lineHeight: 16,
  },
});
