import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { formatSeen, isFinished, type Job, useJob, useWorkerStatus } from '@/features/jobs/jobs';
import { ApiError, apiPost } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

// The Mac worker, which runs slow and private jobs (documents, plans, …):
// whether it's online, how many jobs wait, and a test job to check it works.
export function WorkerSection({ canEdit }: { canEdit: boolean }) {
  const { colors } = useTheme();
  const status = useWorkerStatus();
  const [sent, setSent] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const job = useJob(sent);

  const send = async (quick: boolean) => {
    setBusy(true);
    setError(null);
    try {
      setSent(await apiPost<Job>('/api/me/jobs/test', { quick }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t send the test job.');
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    if (!job?.id) return;
    try {
      setSent(await apiPost<Job>(`/api/me/jobs/${job.id}/retry`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t retry.');
    }
  };

  const muted = { color: colors.textMuted };
  const text = { color: colors.text };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.heading}>
        <Text style={[styles.title, text]}>Mac worker</Text>
        <Text style={[styles.body, muted]}>
          The Mac runs slow and private jobs, like reading health documents with the local AI. Jobs
          wait in a queue while it’s off.
        </Text>
      </View>

      {!status ? (
        <ActivityIndicator color={colors.primary} />
      ) : (
        <View style={styles.status}>
          <Text style={[styles.body, { color: status.online ? colors.good : colors.caution }]}>
            {status.online
              ? '✓ Online'
              : status.last_seen_at
                ? `Offline since ${formatSeen(status.last_seen_at)}`
                : 'Not set up yet'}
          </Text>
          {status.online && (
            <Text style={[styles.body, muted]}>
              Local AI (Ollama): {status.ollama_ok ? 'running' : 'not running'}
            </Text>
          )}
          <Text style={[styles.body, muted]}>
            {status.waiting_jobs === 0
              ? 'No jobs waiting.'
              : `${status.waiting_jobs} job${status.waiting_jobs === 1 ? '' : 's'} waiting.`}
          </Text>
        </View>
      )}

      {canEdit && (
        <View style={styles.status}>
          <View style={styles.row}>
            <Button label="Send test job" onPress={() => send(false)} disabled={busy} />
            <Button
              label="Quick test (Vercel first)"
              variant="secondary"
              onPress={() => send(true)}
              disabled={busy}
            />
          </View>
          {job && (
            <Text style={[styles.body, job.status === 'failed' ? { color: colors.alert } : text]}>
              {jobLine(job)}
            </Text>
          )}
          {job?.status === 'failed' && <Button label="Retry" variant="secondary" onPress={retry} />}
          {job && !isFinished(job) && <ActivityIndicator color={colors.primary} />}
        </View>
      )}

      {error && (
        <Text accessibilityRole="alert" style={[styles.body, { color: colors.alert }]}>
          {error}
        </Text>
      )}
    </View>
  );
}

function jobLine(job: Job): string {
  switch (job.status) {
    case 'pending':
      return 'Test job queued: waiting for the Mac worker…';
    case 'processing':
      return 'The Mac worker is running the test job…';
    case 'failed':
      return `Test job failed: ${job.last_error ?? 'unknown error'}`;
    case 'done': {
      const by = String(job.result?.processed_by ?? 'unknown');
      return by === 'vercel'
        ? '✓ Test job done straight away on Vercel (no queue needed).'
        : `✓ Test job done by the Mac worker (${by}).`;
    }
  }
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
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
});
