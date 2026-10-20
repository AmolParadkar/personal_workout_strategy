import { Pressable, StyleSheet, Text } from 'react-native';

import { radius, useTheme } from '@/theme';

// Header button that switches between dark and light mode.
export function ThemeToggle() {
  const { mode, colors, toggleMode } = useTheme();
  const nextMode = mode === 'dark' ? 'light' : 'dark';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Switch to ${nextMode} mode`}
      onPress={toggleMode}
      style={[styles.button, { borderColor: colors.border, backgroundColor: colors.surfaceRaised }]}
    >
      <Text style={[styles.icon, { color: colors.text }]}>{mode === 'dark' ? '☀' : '☾'}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  icon: {
    fontSize: 18,
  },
});
