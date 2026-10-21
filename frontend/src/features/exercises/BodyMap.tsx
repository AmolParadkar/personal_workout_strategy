import { Platform, StyleSheet, Text, View } from 'react-native';
import Body from 'react-native-body-highlighter';

import { spacing, useTheme } from '@/theme';

import { bodyMapData } from './muscles';

// The package gives every muscle shape a tap handler and `accessible={true}`,
// which the web version of react-native-svg passes on to the page as invalid
// attributes. Harmless (the map isn't tappable, it's labelled as one image
// below, and production builds don't warn), so drop just those two dev
// warnings; LogBox.ignoreLogs doesn't reach the web overlay.
if (__DEV__ && Platform.OS === 'web') {
  const showError = console.error;
  const fromBodyMap = (args: unknown[]) =>
    typeof args[0] === 'string' &&
    (args[0].startsWith('Unknown event handler property') ||
      (args[0].startsWith('Received `%s` for a non-boolean attribute') &&
        args.includes('accessible')));
  console.error = (...args: unknown[]) => {
    if (fromBodyMap(args)) return;
    showError(...args);
  };
}

// Spec colours: primary muscles dark red, secondary light red.
const PRIMARY_RED = '#C62828';
const SECONDARY_RED = '#EF9A9A';

// Front and back body with the exercise's muscles highlighted.
export function BodyMap({
  primary,
  secondary,
  gender,
}: {
  primary: string[];
  secondary: string[];
  gender: 'male' | 'female';
}) {
  const { colors, mode } = useTheme();
  const data = bodyMapData(primary, secondary);
  const common = {
    data,
    gender,
    scale: 0.75,
    colors: [PRIMARY_RED, SECONDARY_RED],
    defaultFill: mode === 'dark' ? '#3A4750' : '#D5DCE0',
    border: colors.border,
  };

  return (
    <View style={styles.wrapper}>
      <View
        style={styles.bodies}
        role="img"
        aria-label={`Muscles worked. Primary: ${primary.join(', ') || 'none'}. Secondary: ${secondary.join(', ') || 'none'}.`}
      >
        <View style={styles.side}>
          <Body {...common} side="front" />
          <Text style={[styles.caption, { color: colors.textMuted }]}>Front</Text>
        </View>
        <View style={styles.side}>
          <Body {...common} side="back" />
          <Text style={[styles.caption, { color: colors.textMuted }]}>Back</Text>
        </View>
      </View>
      <View style={styles.legend}>
        <Legend color={PRIMARY_RED} label="Primary" />
        <Legend color={SECONDARY_RED} label="Secondary" />
      </View>
    </View>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.legendItem}>
      <View style={[styles.swatch, { backgroundColor: color }]} />
      <Text style={[styles.caption, { color: colors.text }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: spacing.sm,
    alignItems: 'center',
  },
  bodies: {
    flexDirection: 'row',
    justifyContent: 'center',
    flexWrap: 'wrap',
  },
  side: {
    alignItems: 'center',
  },
  caption: {
    fontSize: 13,
  },
  legend: {
    flexDirection: 'row',
    gap: spacing.lg,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  swatch: {
    width: 14,
    height: 14,
    borderRadius: 3,
  },
});
