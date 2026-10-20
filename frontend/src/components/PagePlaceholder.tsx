import type { ReactNode } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { type PageKey, pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { colors, maxContentWidth, radius, spacing } from '@/theme';

// Temporary content for pages that haven't been built yet.
export function PagePlaceholder({ page, children }: { page: PageKey; children?: ReactNode }) {
  const info = pages[page];
  const { activeProfile } = useProfile();

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={styles.title}>{info.title}</Text>
        <Text style={styles.description}>{info.description}</Text>
        <View style={styles.card}>
          <Text style={styles.cardText}>
            Showing {activeProfile.name}’s profile. This page is planned for milestone{' '}
            {info.milestone}.
          </Text>
          {children}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.md,
  },
  content: {
    width: '100%',
    maxWidth: maxContentWidth,
    alignSelf: 'center',
    // Same side padding as the header, so titles line up with "Workout Strategy".
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.text,
  },
  description: {
    fontSize: 16,
    color: colors.textMuted,
  },
  card: {
    marginTop: spacing.md,
    padding: spacing.lg,
    gap: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  cardText: {
    fontSize: 15,
    color: colors.text,
  },
});
