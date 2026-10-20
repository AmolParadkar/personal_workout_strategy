// Shared spacing and sizes, plus re-exports so screens import everything from '@/theme'.
export { darkColors, lightColors, type ThemeColors } from './colors';
export { ThemeProvider, type ThemeMode, useTheme } from './ThemeContext';

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
};

export const radius = {
  sm: 8,
  md: 14,
  pill: 999,
};

// Content never stretches wider than this on large screens.
export const maxContentWidth = 1120;
