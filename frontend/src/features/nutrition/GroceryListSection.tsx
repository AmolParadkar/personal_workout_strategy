import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { ChipSelect } from '@/components/form';
import { apiGet } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { spacing, useTheme } from '@/theme';

import type { GroceryList } from './meals';

type Who = 'everyone' | 'one';

// The week's grocery list (shown in an overlay) from today to Sunday: everyone's meal plans added up,
// or just the person whose page this is.
export function GroceryListSection({
  weekStart,
  profileId,
  name,
  refreshKey,
}: {
  weekStart: string;
  profileId: string;
  name: string;
  // Changes when the plan changes, so the list is fetched again.
  refreshKey: string;
}) {
  const { colors } = useTheme();
  const [who, setWho] = useState<Who[]>(['everyone']);
  const [loaded, setLoaded] = useState<{
    key: string;
    list: GroceryList;
  } | null>(null);
  const [error, setError] = useState(false);
  const today = todayLocal();
  const fromDay = today > weekStart ? today : weekStart;
  const params = new URLSearchParams({
    week_start: weekStart,
    from_day: fromDay,
  });
  if (who[0] === 'one') params.set('profile_id', profileId);
  const key = `${params}|${refreshKey}`;
  const list = loaded?.key === key ? loaded.list : null;

  useEffect(() => {
    let cancelled = false;
    const query = key.split('|')[0];
    apiGet<GroceryList>(`/api/grocery-list?${query}`)
      .then((next) => {
        if (!cancelled) {
          setLoaded({ key, list: next });
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  const text = { color: colors.text };
  const muted = { color: colors.textMuted };
  const withoutPlan = list?.people.filter((p) => !p.has_plan).map((p) => p.name) ?? [];

  return (
    <View style={styles.wrapper}>
      <Text style={[styles.caption, muted]}>
        For meals from today to Sunday. Amounts are approximate; spices and staples you already have
        can be skipped.
      </Text>
      <ChipSelect
        options={[
          { value: 'everyone', label: 'Everyone' },
          { value: 'one', label: `Just ${name}` },
        ]}
        selected={who}
        onChange={(next) => setWho(next.length ? next : who)}
      />
      {error && <Text style={{ color: colors.alert }}>Couldn’t load the grocery list.</Text>}
      {!list && !error && <ActivityIndicator color={colors.primary} />}
      {list && withoutPlan.length > 0 && (
        <Text style={[styles.caption, muted]}>
          No meal plan yet this week for {withoutPlan.join(' and ')}.
        </Text>
      )}
      {list && list.groups.length === 0 && (
        <Text style={[styles.body, muted]}>Nothing to buy for the rest of this week.</Text>
      )}
      {list?.groups.map((group) => (
        <View key={group.group} style={styles.group}>
          <Text style={[styles.groupLabel, muted]}>{group.group.toUpperCase()}</Text>
          {group.items.map((item) => (
            <View key={`${item.name}-${item.unit}`} style={styles.item}>
              <Text style={[styles.body, text, styles.grow]}>
                {item.name}
                {who[0] === 'everyone' && list.people.length > 1 && (
                  <Text style={[styles.caption, muted]}> · {item.for_people.join(', ')}</Text>
                )}
              </Text>
              <Text style={[styles.body, muted]}>
                {item.amount != null ? `${item.amount} ${item.unit}`.trim() : item.unit}
              </Text>
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: spacing.sm,
  },
  group: {
    gap: 4,
    marginTop: spacing.xs,
  },
  groupLabel: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  item: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  grow: {
    flex: 1,
  },
  body: {
    fontSize: 14,
  },
  caption: {
    fontSize: 12,
    lineHeight: 17,
  },
});
