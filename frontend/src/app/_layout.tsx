import { Slot } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { NavBar } from '@/components/NavBar';
import { ProfileSwitcher } from '@/components/ProfileSwitcher';
import { ThemeToggle } from '@/components/ThemeToggle';
import { ProfileProvider } from '@/features/profile/ProfileContext';
import { maxContentWidth, spacing, ThemeProvider, useTheme } from '@/theme';

// Providers wrap the whole app so every screen can read the theme and profile.
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <ProfileProvider>
          <AppFrame />
        </ProfileProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

// The frame around every page: header with the theme toggle and profile
// dropdown, the navigation bar, then the current page (rendered at <Slot />).
function AppFrame() {
  const { mode, colors } = useTheme();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.background }]} edges={['top']}>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
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
            <ThemeToggle />
            <ProfileSwitcher />
          </View>
        </View>
        <View style={styles.navWrapper}>
          <NavBar />
        </View>
      </View>
      <View style={styles.page}>
        <Slot />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
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
});
