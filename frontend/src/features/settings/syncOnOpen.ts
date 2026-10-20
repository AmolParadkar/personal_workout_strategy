import { useEffect } from 'react';

import { apiPost } from '@/lib/api';
import { todayLocal } from '@/lib/dates';

// When the app opens, fetch new data from the person's connected services
// (Withings, Oura, …). The API skips any synced in the last 3 hours, so this
// is cheap. Runs in the background: pages don't wait for it, and a failure
// shows up as the connection's status in Settings.
export function useSyncConnectionsOnOpen() {
  useEffect(() => {
    apiPost('/api/me/connections/sync', { today: todayLocal() }).catch(() => {});
  }, []);
}
