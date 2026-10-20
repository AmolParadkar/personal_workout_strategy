import { Link } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '@/features/auth/AuthContext';
import { pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { radius, spacing, useTheme } from '@/theme';

// The dropdown at the top of every page: switch profile, or open Settings.
export function ProfileSwitcher() {
  const { profiles, activeProfile, setActiveProfileId } = useProfile();
  const { signOut } = useAuth();
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);

  const menuItemText = { color: colors.text };

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Profile: ${activeProfile.display_name}. Change profile`}
        onPress={() => setOpen((isOpen) => !isOpen)}
        style={[styles.button, { borderColor: colors.border, backgroundColor: colors.surfaceRaised }]}
      >
        <View style={[styles.avatar, { backgroundColor: colors.primarySoft }]}>
          <Text style={[styles.avatarText, { color: colors.primary }]}>
            {activeProfile.display_name.charAt(0).toUpperCase()}
          </Text>
        </View>
        <Text style={[styles.buttonText, { color: colors.text }]}>{activeProfile.display_name}</Text>
        <Text style={[styles.chevron, { color: colors.textMuted }]}>▾</Text>
      </Pressable>

      {open && (
        <View
          style={[
            styles.menu,
            {
              borderColor: colors.border,
              backgroundColor: colors.surfaceRaised,
              boxShadow: `0 8px 24px ${colors.shadow}`,
            },
          ]}
        >
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
              <Text style={[styles.check, { color: colors.primary }]}>
                {profile.id === activeProfile.id ? '✓' : ''}
              </Text>
              <Text style={[styles.menuText, menuItemText]}>
                {profile.display_name}
                {profile.is_own && <Text style={{ color: colors.textMuted }}> (you)</Text>}
              </Text>
            </Pressable>
          ))}
          <View style={[styles.divider, { backgroundColor: colors.border }]} />
          <Link href={pages.settings.href} asChild>
            <Pressable
              accessibilityRole="menuitem"
              onPress={() => setOpen(false)}
              style={styles.menuItem}
            >
              <Text style={styles.check} />
              <Text style={[styles.menuText, menuItemText]}>{pages.settings.title}</Text>
            </Pressable>
          </Link>
          <Pressable
            accessibilityRole="menuitem"
            onPress={() => {
              setOpen(false);
              signOut();
            }}
            style={styles.menuItem}
          >
            <Text style={styles.check} />
            <Text style={[styles.menuText, menuItemText]}>Sign out</Text>
          </Pressable>
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
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    height: 40,
    paddingLeft: spacing.xs,
    paddingRight: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  avatar: {
    width: 30,
    height: 30,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
  },
  avatarText: {
    fontSize: 14,
    fontWeight: '700',
  },
  buttonText: {
    fontSize: 15,
    fontWeight: '600',
  },
  chevron: {
    fontSize: 12,
  },
  menu: {
    position: 'absolute',
    top: '100%',
    right: 0,
    marginTop: spacing.sm,
    minWidth: 220,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  check: {
    width: 20,
    fontSize: 14,
    fontWeight: '700',
  },
  menuText: {
    fontSize: 15,
  },
  divider: {
    height: 1,
    marginVertical: spacing.xs,
  },
});
