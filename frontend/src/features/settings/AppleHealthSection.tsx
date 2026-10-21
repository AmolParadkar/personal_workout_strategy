import * as Clipboard from 'expo-clipboard';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { ApiError, apiDelete, apiGet, apiPost, apiUrl, type Schemas } from '@/lib/api';
import { formatShortDate } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type Connection = Schemas['HealthConnection'];
type NewConnection = Schemas['NewHealthConnection'];

const GUIDE_URL =
  'https://github.com/AmolParadkar/personal_workout_strategy/blob/main/context/apple-health-shortcut.md';

// Connects the person's iOS Shortcut: creates the connection token (shown
// once), shows when data last arrived, and lets them disconnect. Own profile only.
export function AppleHealthSection() {
  const { colors } = useTheme();
  const [connection, setConnection] = useState<Connection | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet<Connection>('/api/me/health-connection')
      .then((c) => {
        if (!cancelled) setConnection(c);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Couldn’t load.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const create = () =>
    run(async () => {
      const created = await apiPost<NewConnection>('/api/me/health-connection');
      setNewToken(created.token);
      setConfirmReplace(false);
      setConnection(await apiGet<Connection>('/api/me/health-connection'));
    });

  const disconnect = () =>
    run(async () => {
      setConnection(await apiDelete<Connection>('/api/me/health-connection'));
      setNewToken(null);
    });

  const copy = async (label: string, value: string) => {
    await Clipboard.setStringAsync(value);
    setCopied(label);
  };

  const muted = { color: colors.textMuted };
  const text = { color: colors.text };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.heading}>
        <Text style={[styles.title, text]}>Apple Health</Text>
        <Text style={[styles.body, muted]}>
          An iOS Shortcut sends your steps, sleep, active energy and weight from Apple Health once a
          day. It uses a connection token instead of your password.
        </Text>
      </View>

      {!connection && !error && <ActivityIndicator color={colors.primary} />}

      {connection && !connection.connected && !newToken && (
        <Button label="Create connection token" onPress={create} disabled={busy} />
      )}

      {connection?.connected && !newToken && (
        <View style={styles.status}>
          <Text style={[styles.body, text]}>
            ✓ Connected
            {connection.created_at ? ` since ${formatShortDate(connection.created_at)}` : ''}.
          </Text>
          <Text style={[styles.body, muted]}>
            {connection.latest_data_on
              ? `Latest data: ${formatShortDate(connection.latest_data_on)}`
              : 'No data received yet. Run the Shortcut once to check it works.'}
          </Text>
          {confirmReplace ? (
            <View style={styles.confirm}>
              <Text style={[styles.body, { color: colors.caution }]}>
                A new token stops the old one working. You’ll need to paste it into the Shortcut.
              </Text>
              <View style={styles.row}>
                <Button
                  label="Cancel"
                  variant="secondary"
                  onPress={() => setConfirmReplace(false)}
                />
                <Button label="Create new token" onPress={create} disabled={busy} />
              </View>
            </View>
          ) : (
            <View style={styles.row}>
              <Button
                label="New token"
                variant="secondary"
                onPress={() => setConfirmReplace(true)}
              />
              <Button label="Disconnect" variant="secondary" onPress={disconnect} disabled={busy} />
            </View>
          )}
        </View>
      )}

      {newToken && (
        <View style={styles.status}>
          <Text style={[styles.body, { color: colors.caution }]}>
            Copy this token into the Shortcut now. It won’t be shown again.
          </Text>
          <Secret label="Connection token" value={newToken} onCopy={copy} copied={copied} />
          <Secret
            label="Address for the Shortcut"
            value={`${apiUrl}/api/ingest/health`}
            onCopy={copy}
            copied={copied}
          />
          <Button label="Done" variant="secondary" onPress={() => setNewToken(null)} />
        </View>
      )}

      {error && (
        <Text accessibilityRole="alert" style={[styles.body, { color: colors.alert }]}>
          {error}
        </Text>
      )}

      <Pressable accessibilityRole="link" onPress={() => Linking.openURL(GUIDE_URL)}>
        <Text style={[styles.link, { color: colors.primary }]}>How to build the Shortcut →</Text>
      </Pressable>
    </View>
  );
}

function Secret({
  label,
  value,
  onCopy,
  copied,
}: {
  label: string;
  value: string;
  onCopy: (label: string, value: string) => void;
  copied: string | null;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.secret}>
      <Text style={[styles.label, { color: colors.textMuted }]}>{label}</Text>
      <View
        style={[
          styles.valueBox,
          { borderColor: colors.border, backgroundColor: colors.background },
        ]}
      >
        <Text selectable style={[styles.value, { color: colors.text }]}>
          {value}
        </Text>
      </View>
      <View style={styles.row}>
        <Button
          label={copied === label ? 'Copied ✓' : 'Copy'}
          variant="secondary"
          onPress={() => onCopy(label, value)}
        />
      </View>
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
  status: {
    gap: spacing.md,
  },
  confirm: {
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  secret: {
    gap: spacing.xs,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
  },
  valueBox: {
    padding: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  value: {
    fontSize: 14,
    fontFamily: 'monospace',
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
});
