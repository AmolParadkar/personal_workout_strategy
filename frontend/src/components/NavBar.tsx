import { Link, usePathname } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { navOrder, pages } from '@/features/navigation/pages';
import { radius, spacing, useTheme } from '@/theme';

// Links to every page. Scrolls sideways on narrow phone screens.
export function NavBar() {
  const pathname = usePathname();
  const { colors } = useTheme();

  // TODO(M2): hide pages with requires75Hard for profiles without an active
  // 75 Hard challenge, once the challenges table exists.
  const visiblePages = navOrder.map((key) => pages[key]);

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
