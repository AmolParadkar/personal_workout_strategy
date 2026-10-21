import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError, apiGet, apiPut } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import { type FoodOption, kcal, type PlannedMeal, SLOT_LABELS, type WeekMealPlan } from './meals';

// One planned meal: its dishes and portions, calories and protein. On your own
// plan (today on), the main dish can be swapped and the meal ticked for eating out.
export function MealCard({
  meal,
  canChange,
  selected,
  onToggleEatingOut,
  onSwapped,
}: {
  meal: PlannedMeal;
  canChange: boolean;
  selected?: boolean;
  onToggleEatingOut?: () => void;
  onSwapped?: (week: WeekMealPlan) => void;
}) {
  const { colors } = useTheme();
  const [options, setOptions] = useState<FoodOption[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const text = { color: colors.text };
  const muted = { color: colors.textMuted };
  const out = meal.kind === 'eating_out';

  const showSwaps = async () => {
    if (options) return setOptions(null);
    setLoading(true);
    setError(null);
    try {
      setOptions(
        await apiGet<FoodOption[]>(
          `/api/me/planned-meals/${meal.id}/alternatives?today=${todayLocal()}`,
        ),
      );
    } catch {
      setError('Couldn’t load swaps.');
    } finally {
      setLoading(false);
    }
  };

  const swap = async (option: FoodOption) => {
    setLoading(true);
    setError(null);
    try {
      const week = await apiPut<WeekMealPlan>(
        `/api/me/planned-meals/${meal.id}/food?today=${todayLocal()}`,
        { food_id: option.id },
      );
      setOptions(null);
      onSwapped?.(week);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t swap. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View
      style={[
        styles.card,
        {
          borderColor: selected ? colors.primary : colors.border,
          backgroundColor: colors.surface,
        },
      ]}
    >
      <View style={styles.header}>
        <Text style={[styles.slot, { color: colors.primary }]}>
          {SLOT_LABELS[meal.slot].toUpperCase()}
        </Text>
        <Text style={[styles.caption, muted]}>
          {kcal(meal.nutrients.kcal)} · {Math.round(meal.nutrients.protein_g)} g protein
          {out ? ' (estimate)' : ''}
        </Text>
      </View>
      {out ? (
        <Text style={[styles.name, text]}>Eating out</Text>
      ) : (
        meal.items.map((item, n) => (
          <View key={`${item.food_id}-${n}`} style={styles.item}>
            <Text style={[styles.name, text, n > 0 && styles.secondary]}>{item.name}</Text>
            <Text style={[styles.body, muted]}>{item.unit}</Text>
          </View>
        ))
      )}
      {meal.note && <Text style={[styles.caption, muted]}>{meal.note}</Text>}

      {canChange && !out && (
        <View style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Swap ${meal.items[0]?.name ?? SLOT_LABELS[meal.slot]}`}
            onPress={showSwaps}
            style={[styles.action, { borderColor: colors.border }]}
          >
            <Text style={[styles.actionText, text]}>{options ? 'Close swaps' : 'Swap dish'}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="checkbox"
            aria-checked={!!selected}
            accessibilityLabel={`Eating out for ${SLOT_LABELS[meal.slot].toLowerCase()}`}
            onPress={onToggleEatingOut}
            style={[
              styles.action,
              {
                borderColor: selected ? colors.primary : colors.border,
                backgroundColor: selected ? colors.primarySoft : 'transparent',
              },
            ]}
          >
            <Text style={[styles.actionText, { color: selected ? colors.primary : colors.text }]}>
              {selected ? '✓ Eating out' : 'Eating out'}
            </Text>
          </Pressable>
        </View>
      )}
      {loading && <ActivityIndicator color={colors.primary} />}
      {error && <Text style={{ color: colors.alert }}>{error}</Text>}
      {options && !loading && (
        <View style={styles.options}>
          {options.length === 0 && (
            <Text style={[styles.caption, muted]}>No other dishes fit here.</Text>
          )}
          {options.map((option) => (
            <Pressable
              key={option.id}
              accessibilityRole="button"
              accessibilityLabel={`Swap to ${option.name}`}
              onPress={() => swap(option)}
              style={[styles.option, { borderColor: colors.border }]}
            >
              <Text style={[styles.body, text]}>{option.name}</Text>
              <Text style={[styles.caption, muted]}>
                {option.serving_label ? `1 ${option.serving_label}: ` : ''}
                {kcal(option.kcal)} · {option.protein_g} g protein
              </Text>
            </Pressable>
          ))}
          <Text style={[styles.caption, muted]}>Portions are resized to fit the meal.</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.md,
    gap: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  slot: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  item: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  name: {
    fontSize: 15,
    fontWeight: '600',
    flexShrink: 1,
  },
  secondary: {
    fontWeight: '400',
  },
  body: {
    fontSize: 14,
  },
  caption: {
    fontSize: 12,
    lineHeight: 17,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  action: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  actionText: {
    fontSize: 13,
    fontWeight: '600',
  },
  options: {
    gap: spacing.xs,
  },
  option: {
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    gap: 2,
  },
});
