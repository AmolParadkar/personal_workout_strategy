import { StyleSheet, Text } from 'react-native';

import { maxContentWidth, spacing, useTheme } from '@/theme';

import { formatSeen, useWorkerStatus } from './jobs';

// Shown on every page while the Mac worker is offline and jobs are waiting,
// so it's clear why something hasn't finished, and what happens next.
export function WorkerNotice() {
  const { colors } = useTheme();
  const status = useWorkerStatus();
  if (!status || status.online || status.waiting_jobs === 0) return null;

  const since = status.last_seen_at
    ? `offline since ${formatSeen(status.last_seen_at)}`
    : 'not set up yet';
  const jobs = status.waiting_jobs === 1 ? '1 job is' : `${status.waiting_jobs} jobs are`;
  return (
    <Text accessibilityRole="alert" style={[styles.notice, { color: colors.caution }]}>
      The Mac worker is {since}. {jobs} queued and will run when it’s back (wake the Mac and sign
      in).
    </Text>
  );
}

const styles = StyleSheet.create({
  notice: {
    width: '100%',
    maxWidth: maxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    fontSize: 14,
    lineHeight: 20,
  },
});
