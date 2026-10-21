import { useEffect, useState } from 'react';

import { apiGet, type Schemas } from '@/lib/api';

type Settings = Schemas['ProfileSettings'];

export type SettingsState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; settings: Settings };

// Loads one profile's settings, and again whenever the profile changes.
export function useProfileSettings(profileId: string) {
  const [loaded, setLoaded] = useState<{ profileId: string; state: SettingsState } | null>(null);

  useEffect(() => {
    // Ignore a result for a profile that's no longer selected.
    let cancelled = false;
    apiGet<Settings>(`/api/profiles/${profileId}/settings`)
      .then((settings): SettingsState => ({ status: 'ready', settings }))
      .catch((error): SettingsState => ({
        status: 'error',
        message: error instanceof Error ? error.message : 'Couldn’t load settings.',
      }))
      .then((state) => {
        if (!cancelled) setLoaded({ profileId, state });
      });
    return () => {
      cancelled = true;
    };
  }, [profileId]);

  // Until this profile's result arrives, it's loading (even if an older one is shown).
  const state: SettingsState =
    loaded?.profileId === profileId ? loaded.state : { status: 'loading' };

  const setSettings = (settings: Settings) =>
    setLoaded({ profileId, state: { status: 'ready', settings } });

  return { state, setSettings };
}
