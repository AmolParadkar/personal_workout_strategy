import { Redirect, Slot, usePathname } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { NavBar } from '@/components/NavBar';
import { ProfileSwitcher } from '@/components/ProfileSwitcher';
import { RefreshButton } from '@/components/RefreshButton';
import { ThemeToggle } from '@/components/ThemeToggle';
import { AuthProvider, useAuth } from '@/features/auth/AuthContext';
import { ProfileProvider } from '@/features/profile/ProfileContext';
import { useSyncConnectionsOnOpen } from '@/features/settings/syncOnOpen';
import { maxContentWidth, spacing, ThemeProvider, useTheme } from '@/theme';

const SIGN_IN_PATH = '/sign-in';

// Providers wrap the whole app so every screen can read the theme and sign-in state.
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <AuthProvider>
          <AuthGate />
        </AuthProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

// Sends signed-out visitors to the sign-in page, and signed-in people away
// from it. This only controls what the website shows: the data itself is
// protected by the database access rules and the API.
function AuthGate() {
  const { session, loading } = useAuth();
  const { mode, colors } = useTheme();
  const pathname = usePathname();
  const onSignInPage = pathname === SIGN_IN_PATH;

  let content;
  if (loading) {
    content = (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  } else if (!session && !onSignInPage) {
    content = <Redirect href={SIGN_IN_PATH} />;
  } else if (session && onSignInPage) {
    content = <Redirect href="/" />;
  } else if (!session) {
    content = <Slot />;
  } else {
    content = (
      <ProfileProvider>
        <AppFrame />
      </ProfileProvider>
    );
  }

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.background }]} edges={['top']}>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
      {content}
    </SafeAreaView>
  );
}

// The frame around every signed-in page: header with the theme toggle and
// profile dropdown, the navigation bar, then the current page (at <Slot />).
function AppFrame() {
  const { colors } = useTheme();
  useSyncConnectionsOnOpen();
  // Bumped by the Refresh button: re-mounting the page makes it load its data again.
  const [pageKey, setPageKey] = useState(0);
  const [notice, setNotice] = useState<{ text: string; problem: boolean } | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshed = (problem: string | null) => {
    setPageKey((key) => key + 1);
    setNotice(
      problem ? { text: problem, problem: true } : { text: 'Data refreshed.', problem: false },
    );
    if (hideTimer.current) clearTimeout(hideTimer.current);
    // Problems stay until the next refresh; "refreshed" fades after a few seconds.
    hideTimer.current = problem ? null : setTimeout(() => setNotice(null), 4000);
  };

  return (
    <>
      <View
        style={[
          styles.headerArea,
          { borderBottomColor: colors.border, backgroundColor: colors.surface },
        ]}
      >
        <View style={styles.header}>
          <View style={styles.brand}>
            <View style={[styles.brandMark, { backgroundColor: colors.primary }]} />
            <Text style={[styles.appName, { color: colors.text }]}>Workout Strategy</Text>
          </View>
          <View style={styles.actions}>
            <RefreshButton onDone={refreshed} />
            <ThemeToggle />
            <ProfileSwitcher />
          </View>
        </View>
        <View style={styles.navWrapper}>
          <NavBar />
        </View>
      </View>
      {notice && (
        <Text
          accessibilityRole="alert"
          style={[styles.notice, { color: notice.problem ? colors.caution : colors.good }]}
        >
          {notice.text}
        </Text>
      )}
      <View key={pageKey} style={styles.page}>
        <Slot />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerArea: {
    // Keeps the profile dropdown menu above the page content.
    zIndex: 10,
    borderBottomWidth: 1,
  },
  header: {
    width: '100%',
    maxWidth: maxContentWidth,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    zIndex: 10,
  },
  brand: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  brandMark: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  appName: {
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  navWrapper: {
    width: '100%',
    maxWidth: maxContentWidth,
    alignSelf: 'center',
  },
  page: {
    flex: 1,
  },
  notice: {
    width: '100%',
    maxWidth: maxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    fontSize: 14,
  },
});
