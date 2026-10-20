import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { useProfile } from '@/features/profile/ProfileContext';
import { ApiError, apiDelete, apiGet, apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type WaterDay = Schemas['WaterDay'];

const GALLON_ML = 3785;
const AMOUNTS = [250, 500];

// 3000 → "3 L", 3500 → "3.5 L", 750 → "0.75 L".
const litres = (ml: number) => `${Number((ml / 1000).toFixed(2))} L`;

// Today's water, with quick-add buttons and Undo. On the other person's
// profile it's view-only. Water buttons live only on Plan for Today.
export function WaterCard() {
  const { activeProfile } = useProfile();
  const { colors } = useTheme();
  const [loaded, setLoaded] = useState<{ profileId: string; water: WaterDay } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const day = todayLocal();

  useEffect(() => {
    let cancelled = false;
    apiGet<WaterDay>(`/api/profiles/${activeProfile.id}/water?day=${day}`)
      .then((water) => {
        if (!cancelled) setLoaded({ profileId: activeProfile.id, water });
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Couldn’t load water.');
      });
    return () => {
      cancelled = true;
    };
  }, [activeProfile.id, day]);

  const water = loaded?.profileId === activeProfile.id ? loaded.water : null;

  const change = async (request: () => Promise<WaterDay>) => {
    setBusy(true);
    setError(null);
    try {
      setLoaded({ profileId: activeProfile.id, water: await request() });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t save. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const card = [styles.card, { borderColor: colors.border, backgroundColor: colors.surface }];

  if (!water) {
    return (
      <View style={card}>
        <Text style={[styles.title, { color: colors.text }]}>Water</Text>
        {error ? (
          <Text style={{ color: colors.alert }}>{error}</Text>
        ) : (
          <ActivityIndicator color={colors.primary} />
        )}
      </View>
    );
  }

  const progress = Math.min(water.total_ml / water.target_ml, 1);
  const reached = water.total_ml >= water.target_ml;
  const lastLog = water.logs[water.logs.length - 1];

  return (
    <View style={card}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.text }]}>Water</Text>
        <Text style={[styles.target, { color: reached ? colors.good : colors.textMuted }]}>
          {reached ? 'Target reached ✓' : `Target ${litres(water.target_ml)}`}
        </Text>
      </View>
      <Text style={[styles.total, { color: colors.text }]}>{litres(water.total_ml)}</Text>
      <View
        style={[styles.track, { backgroundColor: colors.border }]}
        accessibilityLabel={`${water.total_ml} of ${water.target_ml} millilitres`}
      >
        <View
          style={[styles.fill, { backgroundColor: colors.primary, width: `${progress * 100}%` }]}
        />
      </View>
      {activeProfile.doing_75_hard && (
        <Text style={[styles.note, { color: colors.textMuted }]}>
          {water.total_ml >= GALLON_ML
            ? '75 Hard gallon reached: the water item is ticked.'
            : `${litres(GALLON_ML - water.total_ml)} to go for the 75 Hard gallon (ticks itself).`}
        </Text>
      )}
      {error && <Text style={[styles.note, { color: colors.alert }]}>{error}</Text>}
      {water.can_edit && (
        <View style={styles.buttons}>
          {AMOUNTS.map((ml) => (
            <Button
              key={ml}
              label={`+${ml} ml`}
              onPress={() =>
                change(() => apiPost<WaterDay>('/api/me/water', { ml, date: day }))
              }
              disabled={busy}
            />
          ))}
          {lastLog && (
            <Button
              label="Undo"
              variant="secondary"
              onPress={() =>
                change(() => apiDelete<WaterDay>(`/api/me/water/${lastLog.id}?day=${day}`))
              }
              disabled={busy}
            />
          )}
        </View>
      )}
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  target: {
    fontSize: 14,
    fontWeight: '600',
  },
  total: {
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  track: {
    height: 8,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: radius.pill,
  },
  note: {
    fontSize: 13,
    lineHeight: 18,
  },
  buttons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
});
