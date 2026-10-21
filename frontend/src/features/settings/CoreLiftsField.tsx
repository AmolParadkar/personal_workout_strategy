import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { TextField } from '@/components/form';
import { apiGet, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type Option = Schemas['ExerciseSummary'];

const MAX_CORE = 8;
const SEARCH_DELAY_MS = 300;

// Choose core lifts: big compound lifts kept in every plan so their weights can
// keep going up. Options are only lifts the person can do with their equipment
// and level (saved settings), searched by name.
export function CoreLiftsField({
  value,
  onChange,
  disabled,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  const [names, setNames] = useState<Record<string, string>>({});
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<{ query: string; items: Option[] } | null>(null);

  // Names for lifts already chosen.
  useEffect(() => {
    let cancelled = false;
    const missing = value.filter((id) => !names[id]);
    Promise.all(
      missing.map((id) =>
        apiGet<Schemas['ExerciseDetail']>(`/api/exercises/${id}`)
          .then((e) => [id, e.name] as const)
          .catch(() => [id, id.replace(/_/g, ' ')] as const),
      ),
    ).then((pairs) => {
      if (!cancelled && pairs.length)
        setNames((known) => ({ ...known, ...Object.fromEntries(pairs) }));
    });
    return () => {
      cancelled = true;
    };
  }, [value, names]);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (disabled) return;
    let cancelled = false;
    const params = new URLSearchParams({ today: todayLocal() });
    if (query) params.set('search', query);
    apiGet<Option[]>(`/api/me/core-lift-options?${params}`)
      .then((items) => {
        if (!cancelled) setOptions({ query, items });
      })
      .catch(() => {
        if (!cancelled) setOptions({ query, items: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [query, disabled]);

  const add = (option: Option) => {
    setNames((known) => ({ ...known, [option.id]: option.name }));
    onChange([...value, option.id]);
  };
  const full = value.length >= MAX_CORE;

  return (
    <View style={styles.wrapper}>
      <View style={styles.chosen}>
        {value.length === 0 && (
          <Text style={[styles.body, { color: colors.textMuted }]}>None chosen yet.</Text>
        )}
        {value.map((id) => (
          <Pressable
            key={id}
            accessibilityRole="button"
            accessibilityLabel={`Remove ${names[id] ?? id} from core lifts`}
            disabled={disabled}
            onPress={() => onChange(value.filter((v) => v !== id))}
            style={[
              styles.chip,
              { borderColor: colors.primary, backgroundColor: colors.primarySoft },
            ]}
          >
            <Text style={[styles.chipText, { color: colors.primary }]}>
              {names[id] ?? '…'}
              {disabled ? '' : '  ×'}
            </Text>
          </Pressable>
        ))}
      </View>
      {!disabled && !full && (
        <>
          <TextField
            label="Search lifts to add"
            value={search}
            onChange={setSearch}
            placeholder="e.g. squat, row, press"
          />
          <View style={styles.options}>
            {options?.items
              .filter((o) => !value.includes(o.id))
              .slice(0, 8)
              .map((option) => (
                <Pressable
                  key={option.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Add ${option.name}`}
                  onPress={() => add(option)}
                  style={[styles.option, { borderColor: colors.border }]}
                >
                  <Text style={[styles.body, { color: colors.text }]}>+ {option.name}</Text>
                  <Text style={[styles.caption, { color: colors.textMuted }]}>
                    {[option.primary_muscles.join(', '), option.equipment]
                      .filter(Boolean)
                      .join(' · ')}
                  </Text>
                </Pressable>
              ))}
            {options && options.items.length === 0 && (
              <Text style={[styles.caption, { color: colors.textMuted }]}>
                No lifts match with your saved equipment.
              </Text>
            )}
          </View>
        </>
      )}
      {full && (
        <Text style={[styles.caption, { color: colors.textMuted }]}>
          {MAX_CORE} is the most; remove one to add another.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: spacing.sm,
  },
  chosen: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  chipText: {
    fontSize: 14,
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
  body: {
    fontSize: 14,
  },
  caption: {
    fontSize: 12,
  },
});
