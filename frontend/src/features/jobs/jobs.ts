import { useEffect, useState } from 'react';

import { apiGet, type Schemas } from '@/lib/api';

export type Job = Schemas['Job'];
export type WorkerStatus = Schemas['WorkerStatus'];

const JOB_POLL_MS = 3000;
const WORKER_POLL_MS = 60_000;

export const isFinished = (job: Job) => job.status === 'done' || job.status === 'failed';

// Follows a job until it's done or failed, checking every few seconds.
// Pass the job as returned when it was created (or null for none).
export function useJob(initial: Job | null): Job | null {
  // Remembers which job it followed, so a new one (or a retried one, which
  // keeps its id) starts again from what the API just returned.
  const [followed, setFollowed] = useState<{ from: Job | null; latest: Job | null }>({
    from: initial,
    latest: initial,
  });
  const job = followed.from === initial ? followed.latest : initial;
  const setLatest = (latest: Job) => setFollowed({ from: initial, latest });

  useEffect(() => {
    if (!job?.id || isFinished(job)) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      apiGet<Job>(`/api/jobs/${job.id}`)
        .then((next) => {
          if (!cancelled) setLatest(next);
        })
        .catch(() => {
          // Try again on the next tick: a missed check isn't worth an error.
          if (!cancelled) setLatest({ ...job });
        });
    }, JOB_POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setLatest only wraps state
  }, [job]);

  return job;
}

// The Mac worker's status, refreshed every minute.
export function useWorkerStatus(): WorkerStatus | null {
  const [status, setStatus] = useState<WorkerStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      apiGet<WorkerStatus>('/api/worker-status')
        .then((next) => {
          if (!cancelled) setStatus(next);
        })
        .catch(() => {});
    load();
    const timer = setInterval(load, WORKER_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return status;
}

// "9:40 pm" today, otherwise "20 Oct, 9:40 pm".
export function formatSeen(iso: string): string {
  const when = new Date(iso);
  const time = when.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  if (when.toDateString() === new Date().toDateString()) return time;
  return `${when.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}, ${time}`;
}
