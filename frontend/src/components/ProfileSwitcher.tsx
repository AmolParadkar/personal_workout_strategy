import { Link } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { colors, radius, spacing } from '@/theme';

// The dropdown at the top of every page: switch profile, or open Settings.
export function ProfileSwitcher() {
  const { profiles, activeProfile, setActiveProfileId } = useProfile();
  const [open, setOpen] = useState(false);

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Profile: ${activeProfile.name}. Change profile`}
        onPress={() => setOpen((isOpen) => !isOpen)}
        style={styles.button}
      >
        <Text style={styles.buttonText}>{activeProfile.name} ▾</Text>
      </Pressable>

      {open && (
        <View style={styles.menu}>
          {profiles.map((profile) => (
            <Pressable
              key={profile.id}
              accessibilityRole="menuitem"
              onPress={() => {
                setActiveProfileId(profile.id);
                setOpen(false);
              }}
              style={styles.menuItem}
            >
              <Text style={styles.menuText}>
                {profile.id === activeProfile.id ? '✓ ' : '   '}
                {profile.name}
              </Text>
            </Pressable>
          ))}
          <View style={styles.divider} />
          <Link href={pages.settings.href} asChild>
            <Pressable
              accessibilityRole="menuitem"
              onPress={() => setOpen(false)}
              style={styles.menuItem}
            >
              <Text style={styles.menuText}>{pages.settings.title}</Text>
            </Pressable>
          </Link>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'relative',
    zIndex: 10,
  },
  button: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  buttonText: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.text,
  },
  menu: {
    position: 'absolute',
    top: '100%',
    right: 0,
    marginTop: spacing.xs,
    minWidth: 200,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    boxShadow: '0 4px 16px rgba(0, 0, 0, 0.12)',
  },
  menuItem: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  menuText: {
    fontSize: 15,
    color: colors.text,
  },
  divider: {
    height: 1,
    marginVertical: spacing.xs,
    backgroundColor: colors.border,
  },
});
