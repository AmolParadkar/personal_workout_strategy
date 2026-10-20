import { Link, usePathname } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { navOrder, pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { radius, spacing, useTheme } from '@/theme';

// Links to every page. Scrolls sideways on narrow phone screens.
export function NavBar() {
  const pathname = usePathname();
  const { colors } = useTheme();
  const { activeProfile } = useProfile();

  // 75 Hard: always on your own profile (so you can start one); on the other
  // person's profile only while they have a challenge running.
  const show75Hard = activeProfile.is_own || activeProfile.doing_75_hard;
  const visiblePages = navOrder
    .map((key) => pages[key])
    .filter((page) => !page.requires75Hard || show75Hard);

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
            <Pressable
              style={StyleSheet.flatten([
                styles.link,
                active && { backgroundColor: colors.primarySoft },
              ])}
            >
              <Text
                style={[
                  styles.linkText,
                  { color: active ? colors.primary : colors.textMuted },
                  active && styles.linkTextActive,
                ]}
              >
                {page.title}
              </Text>
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
    borderRadius: radius.pill,
  },
  linkText: {
    fontSize: 14,
    fontWeight: '500',
  },
  linkTextActive: {
    fontWeight: '700',
  },
});
