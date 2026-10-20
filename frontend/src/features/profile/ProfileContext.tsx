import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { OnboardingScreen } from '@/features/settings/OnboardingScreen';
import { apiGet, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

export type Profile = Schemas['ProfileSummary'];

type ProfileContextValue = {
  profiles: Profile[];
  activeProfile: Profile;
  setActiveProfileId: (id: string) => void;
  // False when viewing the other person's profile: pages must hide inputs.
  canEdit: boolean;
  // Fetches the profiles again in the background (e.g. after a name change).
  reload: () => void;
};

// A React "context" lets any screen read the selected profile without
// passing it down through every component.
const ProfileContext = createContext<ProfileContextValue | null>(null);

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; profiles: Profile[] };

// Loads the household's profiles from the API. Pages inside it can rely on
// there always being an active profile.
export function ProfileProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [activeId, setActiveProfileId] = useState<string | null>(null);
  // Bumped by "Try again" to load once more.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Ignore a result that arrives after this component has gone (e.g. sign-out).
    let cancelled = false;
    fetchProfiles().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reload = () => setAttempt((n) => n + 1);
  const retry = () => {
    setState({ status: 'loading' });
    reload();
  };

  if (state.status !== 'ready' || state.profiles.length === 0) {
    return (
      <ProfileStatus
        message={state.status === 'error' ? state.message : null}
        onRetry={retry}
      />
    );
  }

  const { profiles } = state;

  // First sign-in: answer the welcome questions before using the app.
  const own = profiles.find((p) => p.is_own);
  if (own && !own.onboarded) {
    return <OnboardingScreen profileId={own.id} onDone={reload} />;
  }

  // The API lists the signed-in person's own profile first.
  const activeProfile = profiles.find((p) => p.id === activeId) ?? profiles[0];

  return (
    <ProfileContext.Provider
      value={{
        profiles,
        activeProfile,
        setActiveProfileId,
        canEdit: activeProfile.is_own,
        reload,
      }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

async function fetchProfiles(): Promise<LoadState> {
  try {
    const data = await apiGet<Schemas['HouseholdProfiles']>('/api/me/profiles');
    return { status: 'ready', profiles: data.profiles };
  } catch (error) {
    return {
      status: 'error',
      message: error instanceof Error ? error.message : 'Couldn’t load profiles.',
    };
  }
}

function ProfileStatus({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.status}>
      {message === null ? (
        <ActivityIndicator color={colors.primary} />
      ) : (
        <>
          <Text style={[styles.statusText, { color: colors.text }]}>{message}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={onRetry}
            style={[styles.retry, { borderColor: colors.border }]}
          >
            <Text style={{ color: colors.primary, fontWeight: '700' }}>Try again</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

export function useProfile(): ProfileContextValue {
  const value = useContext(ProfileContext);
  if (!value) {
    throw new Error('useProfile must be used inside ProfileProvider');
  }
  return value;
}

const styles = StyleSheet.create({
  status: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.md,
  },
  statusText: {
    fontSize: 15,
    textAlign: 'center',
  },
  retry: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
});
