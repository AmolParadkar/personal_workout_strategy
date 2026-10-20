import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { type PageKey, pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { maxContentWidth, radius, spacing, useTheme } from '@/theme';

// Temporary content for pages that haven't been built yet.
export function PagePlaceholder({ page, children }: { page: PageKey; children?: ReactNode }) {
  const info = pages[page];
  const { activeProfile, canEdit } = useProfile();
  const { colors } = useTheme();

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: colors.primary }]}>
          {activeProfile.display_name.toUpperCase()}
        </Text>
        <Text style={[styles.title, { color: colors.text }]}>{info.title}</Text>
        <Text style={[styles.description, { color: colors.textMuted }]}>{info.description}</Text>
        <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          <View style={[styles.badge, { backgroundColor: colors.primarySoft }]}>
            <Text style={[styles.badgeText, { color: colors.primary }]}>
              Coming in {info.milestone}
            </Text>
          </View>
          <Text style={[styles.cardText, { color: colors.text }]}>
            Showing {activeProfile.display_name}’s profile. This page hasn’t been built yet.
          </Text>
          {!canEdit && (
            <Text style={[styles.cardText, { color: colors.textMuted }]}>
              You’re viewing {activeProfile.display_name}’s profile, so it’s view-only.
            </Text>
          )}
          {children}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.lg,
  },
  content: {
    width: '100%',
    maxWidth: maxContentWidth,
    alignSelf: 'center',
    // Same side padding as the header, so titles line up with the app name.
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  description: {
    fontSize: 16,
    lineHeight: 22,
  },
  card: {
    marginTop: spacing.md,
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '700',
  },
  cardText: {
    fontSize: 15,
    lineHeight: 21,
  },
});
