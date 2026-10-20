import { Link, usePathname } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { navOrder, pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { colors, radius, spacing } from '@/theme';

// Links to every page. Scrolls sideways on narrow phone screens.
export function NavBar() {
  const pathname = usePathname();
  const { activeProfile } = useProfile();

  const visiblePages = navOrder
    .map((key) => pages[key])
    .filter((page) => !page.requires75Hard || activeProfile.doing75Hard);

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      {visiblePages.map((page) => {
        // "/" must match exactly; other pages also match their sub-pages (e.g. /exercises/123).
        const href = String(page.href);
        const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
        return (
          <Link key={href} href={page.href} asChild>
            {/* Link's asChild needs one style object, not a list, so the styles are merged. */}
            <Pressable style={StyleSheet.flatten([styles.link, active && styles.linkActive])}>
              <Text style={[styles.linkText, active && styles.linkTextActive]}>{page.title}</Text>
            </Pressable>
          </Link>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  link: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
  },
  linkActive: {
    backgroundColor: colors.primarySoft,
  },
  linkText: {
    fontSize: 14,
    color: colors.textMuted,
  },
  linkTextActive: {
    color: colors.primary,
    fontWeight: '600',
  },
});
