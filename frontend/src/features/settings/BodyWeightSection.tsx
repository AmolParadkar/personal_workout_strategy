import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button, Field, TextField } from '@/components/form';
import { ApiError, apiGet, apiPost, type Schemas } from '@/lib/api';
import { formatShortDate, todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type Weight = Schemas['WeightSummary'];

// Latest body weight, plus a box to log today's. Weights from Apple Health
// arrive through the Shortcut. View-only on the other person's profile.
export function BodyWeightSection({ profileId }: { profileId: string }) {
  const { colors } = useTheme();
  const [loaded, setLoaded] = useState<{ profileId: string; weight: Weight } | null>(null);
  const [kg, setKg] = useState('');
  const [message, setMessage] = useState<{ text: string; isError: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet<Weight>(`/api/profiles/${profileId}/weight`)
      .then((weight) => {
        if (!cancelled) setLoaded({ profileId, weight });
      })
      .catch(() => {
        if (!cancelled) setMessage({ text: 'Couldn’t load weight.', isError: true });
      });
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  const weight = loaded?.profileId === profileId ? loaded.weight : null;

  const save = async () => {
    const value = Number(kg.replace(',', '.'));
    if (!Number.isFinite(value) || value < 20 || value > 400) {
      setMessage({ text: 'Enter a weight between 20 and 400 kg.', isError: true });
      return;
    }
    setBusy(true);
    try {
      const updated = await apiPost<Weight>('/api/me/weight', { kg: value, date: todayLocal() });
      setLoaded({ profileId, weight: updated });
      setKg('');
      setMessage({ text: 'Saved.', isError: false });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.message : 'Couldn’t save.', isError: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.heading}>
        <Text style={[styles.title, { color: colors.text }]}>Body weight</Text>
        <Text style={[styles.body, { color: colors.textMuted }]}>
          Used for plans and, if switched on below, the weight card. Weigh-ins from Apple Health
          arrive automatically.
        </Text>
      </View>

      {!weight ? (
        <ActivityIndicator color={colors.primary} />
      ) : weight.latest ? (
        <Text style={[styles.body, { color: colors.text }]}>
          Latest: <Text style={styles.strong}>{weight.latest.kg} kg</Text> on{' '}
          {formatShortDate(weight.latest.date)}
          {weight.latest.source === 'apple_health' ? ' (Apple Health)' : ''}
        </Text>
      ) : (
        <Text style={[styles.body, { color: colors.textMuted }]}>No weight recorded yet.</Text>
      )}

      {weight?.can_edit && (
        <View style={styles.logRow}>
          <View style={styles.input}>
            <Field label="Today’s weight (kg)">
              <TextField
                label="Today’s weight in kilograms"
                value={kg}
                onChange={(value) => {
                  setKg(value);
                  setMessage(null);
                }}
                inputMode="decimal"
                placeholder="e.g. 78.5"
              />
            </Field>
          </View>
          <Button label={busy ? 'Saving…' : 'Log weight'} onPress={save} disabled={busy || !kg} />
        </View>
      )}

      {message && (
        <Text
          accessibilityRole={message.isError ? 'alert' : undefined}
          style={[styles.body, { color: message.isError ? colors.alert : colors.good }]}
        >
          {message.text}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.lg,
    gap: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  heading: {
    gap: spacing.xs,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
  },
  strong: {
    fontWeight: '700',
  },
  logRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  input: {
    flex: 1,
    minWidth: 180,
  },
});
