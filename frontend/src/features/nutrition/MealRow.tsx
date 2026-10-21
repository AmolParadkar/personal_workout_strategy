import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError, apiGet, apiPut } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import { type FoodOption, kcal, type PlannedMeal, SLOT_LABELS, type WeekMealPlan } from './meals';

const SEARCH_DELAY_MS = 300;

// One meal as a single line (meal, dishes, calories); tap it for portions, what
// each dish is made of, swapping a dish and marking it as eating out.
export function MealRow({
  meal,
  canChange,
  selected,
  onToggleEatingOut,
  onSwapped,
  onAddDish,
}: {
  meal: PlannedMeal;
  canChange: boolean;
  selected?: boolean;
  onToggleEatingOut?: () => void;
  onSwapped?: (week: WeekMealPlan) => void;
  onAddDish?: (name: string) => void;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [swapping, setSwapping] = useState<number | null>(null);
  const text = { color: colors.text };
  const muted = { color: colors.textMuted };
  const out = meal.kind === 'eating_out';
  const names = out ? 'Eating out' : meal.items.map((i) => i.name).join(' · ');

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
      <Pressable
        accessibilityRole="button"
        aria-expanded={open}
        accessibilityLabel={`${SLOT_LABELS[meal.slot]}: ${names}`}
        onPress={() => setOpen((o) => !o)}
        style={styles.row}
      >
        <Text style={[styles.slot, { color: colors.primary }]}>{SLOT_LABELS[meal.slot]}</Text>
        <Text style={[styles.names, text]} numberOfLines={open ? undefined : 2}>
          {names}
        </Text>
        <Text style={[styles.kcal, muted]}>
          {Math.round(meal.nutrients.kcal)}
          <Text style={styles.unit}> kcal</Text>
        </Text>
        <Text style={[styles.chevron, muted]}>{open ? '▴' : '▾'}</Text>
      </Pressable>

      {open && (
        <View style={styles.details}>
          <Text style={[styles.caption, muted]}>
            {kcal(meal.nutrients.kcal)} · {Math.round(meal.nutrients.protein_g)} g protein ·{' '}
            {Math.round(meal.nutrients.carbs_g)} g carbs · {Math.round(meal.nutrients.fat_g)} g fat
            {out ? ' (estimate)' : ''}
          </Text>
          {meal.items.map((item, n) => (
            <View key={`${item.food_id}-${n}`} style={styles.item}>
              <View style={styles.itemLine}>
                <Text style={[styles.itemName, text]}>{item.name}</Text>
                <Text style={[styles.body, muted]}>{item.unit}</Text>
              </View>
              {item.made_with && <Text style={[styles.caption, muted]}>{item.made_with}</Text>}
              {canChange && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Swap ${item.name}`}
                  onPress={() => setSwapping(swapping === n ? null : n)}
                >
                  <Text style={[styles.link, { color: colors.primary }]}>
                    {swapping === n ? 'Close' : 'Swap'}
                  </Text>
                </Pressable>
              )}
              {swapping === n && (
                <SwapPicker
                  meal={meal}
                  item={n}
                  onSwapped={(week) => {
                    setSwapping(null);
                    onSwapped?.(week);
                  }}
                  onAddDish={onAddDish}
                />
              )}
            </View>
          ))}
          {meal.note && <Text style={[styles.caption, muted]}>{meal.note}</Text>}
          {canChange && !out && (
            <Pressable
              accessibilityRole="checkbox"
              aria-checked={!!selected}
              accessibilityLabel={`Eating out for ${SLOT_LABELS[meal.slot].toLowerCase()}`}
              onPress={onToggleEatingOut}
              style={[
                styles.toggle,
                {
                  borderColor: selected ? colors.primary : colors.border,
                  backgroundColor: selected ? colors.primarySoft : 'transparent',
                },
              ]}
            >
              <Text style={[styles.toggleText, { color: selected ? colors.primary : colors.text }]}>
                {selected ? '✓ Eating out' : 'I’m eating out'}
              </Text>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

// Swaps for one dish: suggestions of the same kind, or search every dish
// (the household's own included); "Add a dish" when it isn't there.
function SwapPicker({
  meal,
  item,
  onSwapped,
  onAddDish,
}: {
  meal: PlannedMeal;
  item: number;
  onSwapped: (week: WeekMealPlan) => void;
  onAddDish?: (name: string) => void;
}) {
  const { colors } = useTheme();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<{ key: string; options: FoodOption[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = `${meal.id}|${item}|${query}`;
  const options = result?.key === key ? result.options : null;

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ today: todayLocal(), item: String(item) });
    if (query) params.set('search', query);
    apiGet<FoodOption[]>(`/api/me/planned-meals/${meal.id}/alternatives?${params}`)
      .then((found) => {
        if (!cancelled) setResult({ key, options: found });
      })
      .catch(() => {
        if (!cancelled) setResult({ key, options: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [key, meal.id, item, query]);

  const choose = async (option: FoodOption) => {
    setBusy(true);
    setError(null);
    try {
      onSwapped(
        await apiPut<WeekMealPlan>(`/api/me/planned-meals/${meal.id}/food?today=${todayLocal()}`, {
          food_id: option.id,
          item,
          search: query || null,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t swap. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const muted = { color: colors.textMuted };
  return (
    <View style={styles.picker}>
      <TextInput
        value={search}
        onChangeText={setSearch}
        placeholder="Search all dishes, e.g. aloo paratha"
        placeholderTextColor={colors.textMuted}
        accessibilityLabel="Search dishes to swap in"
        style={[styles.search, { borderColor: colors.border, color: colors.text }]}
      />
      {(!options || busy) && <ActivityIndicator color={colors.primary} />}
      {error && <Text style={{ color: colors.alert }}>{error}</Text>}
      {options?.map((option) => (
        <Pressable
          key={option.id}
          accessibilityRole="button"
          accessibilityLabel={`Swap to ${option.name}`}
          onPress={() => choose(option)}
          disabled={busy}
          style={[styles.option, { borderColor: colors.border }]}
        >
          <Text style={[styles.body, { color: colors.text }]}>
            {option.name}
            {option.custom ? '  · yours' : ''}
          </Text>
          <Text style={[styles.caption, muted]}>
            {option.serving_label ? `1 ${option.serving_label}: ` : ''}
            {kcal(option.kcal)} · {option.protein_g} g protein
          </Text>
        </Pressable>
      ))}
      {options && options.length === 0 && (
        <Text style={[styles.caption, muted]}>
          {query ? `No dish called “${query}” yet.` : 'No other dishes fit here.'}
        </Text>
      )}
      {onAddDish && (
        <Pressable accessibilityRole="button" onPress={() => onAddDish(query)}>
          <Text style={[styles.link, { color: colors.primary }]}>
            {query ? `Add “${query}” as a new dish` : 'Can’t find it? Add a dish'}
          </Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.md,
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  slot: {
    width: 76,
    fontSize: 13,
    fontWeight: '700',
  },
  names: {
    flex: 1,
    fontSize: 15,
    lineHeight: 20,
  },
  kcal: {
    fontSize: 14,
    fontWeight: '600',
  },
  unit: {
    fontSize: 11,
    fontWeight: '400',
  },
  chevron: {
    fontSize: 12,
    width: 12,
  },
  details: {
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
  },
  item: {
    gap: 2,
  },
  itemLine: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  itemName: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
  },
  body: {
    fontSize: 14,
  },
  caption: {
    fontSize: 12,
    lineHeight: 17,
  },
  link: {
    fontSize: 13,
    fontWeight: '600',
    paddingVertical: 2,
  },
  toggle: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  toggleText: {
    fontSize: 13,
    fontWeight: '600',
  },
  picker: {
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  search: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs + 2,
    fontSize: 14,
  },
  option: {
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    gap: 2,
  },
});
