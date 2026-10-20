import { Link, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { connectReturnAddress, errorText } from '@/features/settings/ConnectionsSection';
import { apiPost, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type Result =
  | { status: 'working' }
  | { status: 'done'; saved: number; warning: string | null }
  | { status: 'failed'; message: string };

const LABELS: Record<string, string> = {
  withings: 'Withings',
  oura: 'Oura',
  whoop: 'Whoop',
  polar: 'Polar',
};

// Where a service sends the person back after they approve (or refuse) access:
// /connect/<service>?code=…&state=…  The code is passed to the API, which
// swaps it for access keys and fetches the last 30 days.
export default function ConnectReturnScreen() {
  const { colors } = useTheme();
  const params = useLocalSearchParams<{
    service: string;
    code?: string;
    state?: string;
    error?: string;
  }>();
  const service = params.service;
  const label = LABELS[service] ?? service;
  // Decided once, from the address the service sent the person back to.
  const [result, setResult] = useState<Result>(() =>
    params.error || !params.code || !params.state
      ? {
          status: 'failed',
          message: params.error
            ? `${label} wasn’t connected (access wasn’t approved).`
            : 'This page needs to be opened by the service’s sign-in.',
        }
      : { status: 'working' },
  );
  // A code works only once: don't send it twice (e.g. React re-running effects).
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    // Keep the one-time code out of the address bar and browser history.
    window.history.replaceState(null, '', `/connect/${service}`);
    if (result.status !== 'working' || !params.code || !params.state) return;

    apiPost<Schemas['ServiceSyncResult']>(`/api/me/connections/${service}/complete`, {
      code: params.code,
      state: params.state,
      redirect_uri: connectReturnAddress(service),
      today: todayLocal(),
    })
      .then((r) => setResult({ status: 'done', saved: r.saved, warning: r.error ?? null }))
      .catch((e) =>
        setResult({
          status: 'failed',
          message: errorText(e, 'Couldn’t connect.'),
        }),
      );
  }, [service, params.code, params.state, result.status]);

  return (
    <View style={styles.page}>
      <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
        <Text style={[styles.title, { color: colors.text }]}>Connecting {label}</Text>
        {result.status === 'working' && (
          <>
            <ActivityIndicator color={colors.primary} />
            <Text style={[styles.body, { color: colors.textMuted }]}>
              Fetching your last 30 days. This can take a few seconds.
            </Text>
          </>
        )}
        {result.status === 'done' && (
          <>
            <Text style={[styles.body, { color: colors.good }]}>
              ✓ {label} is connected. {result.saved} measurements fetched.
            </Text>
            {result.warning && (
              <Text style={[styles.body, { color: colors.caution }]}>{result.warning}</Text>
            )}
          </>
        )}
        {result.status === 'failed' && (
          <Text accessibilityRole="alert" style={[styles.body, { color: colors.alert }]}>
            {result.message}
          </Text>
        )}
        {result.status !== 'working' && (
          <Link href="/settings" style={[styles.link, { color: colors.primary }]}>
            Back to Settings →
          </Link>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {
    flex: 1,
    padding: spacing.md,
    alignItems: 'center',
  },
  card: {
    width: '100%',
    maxWidth: 560,
    marginTop: spacing.xl,
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  link: {
    fontSize: 15,
    fontWeight: '700',
  },
});
