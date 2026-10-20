import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, useTheme } from '@/theme';

// Header button: fetch new data from all connected services now (not waiting
// for the 3-hourly sync), then reload the page. Apple Health data can't be
// pulled: it arrives when the iOS Shortcut runs.
export function RefreshButton({ onDone }: { onDone: (message: string | null) => void }) {
  const { colors } = useTheme();
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setBusy(true);
    try {
      const result = await apiPost<Schemas['SyncResult']>('/api/me/connections/sync', {
        today: todayLocal(),
        force: true,
      });
      const errors = result.results.flatMap((r) => (r.error ? [r.error] : []));
      onDone(errors.length > 0 ? errors.join(' ') : null);
    } catch {
      onDone('Couldn’t refresh. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Refresh data from connected services"
      accessibilityState={{ busy, disabled: busy }}
      disabled={busy}
      onPress={refresh}
      style={[styles.button, { borderColor: colors.border, backgroundColor: colors.surfaceRaised }]}
    >
      {busy ? (
        <ActivityIndicator size="small" color={colors.primary} />
      ) : (
        <Text style={[styles.icon, { color: colors.text }]}>↻</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  icon: {
    fontSize: 20,
  },
});
