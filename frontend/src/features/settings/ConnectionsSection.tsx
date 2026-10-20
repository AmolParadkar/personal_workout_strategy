import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { ApiError, apiDelete, apiGet, apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type Connections = Schemas['Connections'];
type Connection = Schemas['ServiceConnection'];

const WHAT_EACH_SENDS: Record<Connection['service'], string> = {
  withings: 'Weight, body fat, blood pressure, sleep and steps.',
  oura: 'Sleep, readiness, HRV and steps.',
  whoop: 'Recovery, strain, sleep and HRV.',
  polar: 'Steps, activity, sleep and HRV.',
};

export function errorText(e: unknown, fallback: string): string {
  if (e instanceof ApiError && typeof e.detail === 'string') return e.detail;
  return e instanceof ApiError ? e.message : fallback;
}

// The page the service sends the person back to after they approve access.
export function connectReturnAddress(service: string): string {
  return `${window.location.origin}/connect/${service}`;
}

// Withings, Oura, Whoop and Polar: connect with the service's own sign-in,
// see when data last arrived, sync now or disconnect. View-only on the other
// person's profile.
export function ConnectionsSection({ profileId }: { profileId: string }) {
  const { colors } = useTheme();
  const [connections, setConnections] = useState<Connections | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<Connections>(`/api/profiles/${profileId}/connections`)
      .then((c) => {
        if (!cancelled) setConnections(c);
      })
      .catch((e) => {
        if (!cancelled) setError(errorText(e, 'Couldn’t load connections.'));
      });
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  const run = async (service: string, action: () => Promise<void>) => {
    setBusy(service);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorText(e, 'Something went wrong. Please try again.'));
    } finally {
      setBusy(null);
    }
  };

  const connect = (service: string) =>
    run(service, async () => {
      const started = await apiPost<Schemas['StartedConnection']>(
        `/api/me/connections/${service}/start`,
        { redirect_uri: connectReturnAddress(service) },
      );
      // Leaves the app for the service's sign-in page; it sends the person back.
      window.location.assign(started.url);
    });

  const syncNow = (service: string) =>
    run(service, async () => {
      const result = await apiPost<Schemas['SyncResult']>('/api/me/connections/sync', {
        today: todayLocal(),
        force: true,
        service,
      });
      setConnections(result.connections);
    });

  const disconnect = (service: string) =>
    run(service, async () => {
      setConnections(await apiDelete<Connections>(`/api/me/connections/${service}`));
      setConfirmDisconnect(null);
    });

  const muted = { color: colors.textMuted };
  const text = { color: colors.text };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.heading}>
        <Text style={[styles.title, text]}>Connected services</Text>
        <Text style={[styles.body, muted]}>
          {connections?.can_edit === false
            ? 'Services this person has connected.'
            : 'Connect a service with its own sign-in. New data is fetched when you open the app (at most every 3 hours). Data already fetched stays if you disconnect.'}
        </Text>
      </View>

      {!connections && !error && <ActivityIndicator color={colors.primary} />}

      {connections?.services.map((c) => (
        <View key={c.service} style={[styles.service, { borderTopColor: colors.border }]}>
          <View style={styles.serviceText}>
            <Text style={[styles.name, text]}>{c.label}</Text>
            <Text style={[styles.body, muted]}>{WHAT_EACH_SENDS[c.service]}</Text>
            <Text
              style={[
                styles.body,
                c.needs_reconnect || c.last_sync_error ? { color: colors.caution } : text,
              ]}
            >
              {statusLine(c)}
            </Text>
          </View>
          {connections.can_edit && c.available && (
            <View style={styles.row}>
              {(!c.connected || c.needs_reconnect) && (
                <Button
                  label={
                    busy === c.service ? 'Opening…' : c.connected ? 'Connect again' : 'Connect'
                  }
                  onPress={() => connect(c.service)}
                  disabled={busy !== null}
                />
              )}
              {c.connected && !c.needs_reconnect && (
                <Button
                  label={busy === c.service ? 'Syncing…' : 'Sync now'}
                  variant="secondary"
                  onPress={() => syncNow(c.service)}
                  disabled={busy !== null}
                />
              )}
              {c.connected &&
                (confirmDisconnect === c.service ? (
                  <>
                    <Button
                      label="Cancel"
                      variant="secondary"
                      onPress={() => setConfirmDisconnect(null)}
                    />
                    <Button
                      label={`Disconnect ${c.label}`}
                      onPress={() => disconnect(c.service)}
                      disabled={busy !== null}
                    />
                  </>
                ) : (
                  <Button
                    label="Disconnect"
                    variant="secondary"
                    onPress={() => setConfirmDisconnect(c.service)}
                    disabled={busy !== null}
                  />
                ))}
            </View>
          )}
        </View>
      ))}

      {error && (
        <Text accessibilityRole="alert" style={[styles.body, { color: colors.alert }]}>
          {error}
        </Text>
      )}
    </View>
  );
}

function statusLine(c: Connection): string {
  if (!c.available && !c.connected) return 'Not set up yet (the app’s developer keys are missing).';
  if (!c.connected) return 'Not connected.';
  if (c.needs_reconnect) return c.last_sync_error ?? 'Needs connecting again.';
  const synced = c.last_synced_at
    ? `Last synced ${new Date(c.last_synced_at).toLocaleString(undefined, {
        day: 'numeric',
        month: 'short',
        hour: 'numeric',
        minute: '2-digit',
      })}.`
    : 'Not synced yet.';
  return c.last_sync_error ? `${synced} ${c.last_sync_error}` : `✓ Connected. ${synced}`;
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
  service: {
    gap: spacing.sm,
    paddingTop: spacing.md,
    borderTopWidth: 1,
  },
  serviceText: {
    gap: 2,
  },
  name: {
    fontSize: 16,
    fontWeight: '700',
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
});
