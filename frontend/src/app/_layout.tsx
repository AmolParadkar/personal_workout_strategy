import { Slot } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { NavBar } from '@/components/NavBar';
import { ProfileSwitcher } from '@/components/ProfileSwitcher';
import { ProfileProvider } from '@/features/profile/ProfileContext';
import { colors, maxContentWidth, spacing } from '@/theme';

// The frame around every page: header with the profile dropdown, the
// navigation bar, then the current page (rendered where <Slot /> is).
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ProfileProvider>
        <SafeAreaView style={styles.screen} edges={['top']}>
          <StatusBar style="dark" />
          <View style={styles.headerArea}>
            <View style={styles.header}>
              <Text style={styles.appName}>Workout Strategy</Text>
              <ProfileSwitcher />
            </View>
            <View style={styles.navWrapper}>
              <NavBar />
            </View>
          </View>
          <View style={styles.page}>
            <Slot />
          </View>
        </SafeAreaView>
      </ProfileProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  headerArea: {
    // Keeps the profile dropdown menu above the page content.
    zIndex: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
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
  appName: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.primary,
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
