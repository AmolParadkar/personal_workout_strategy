// Shared design values so every screen uses the same colours and spacing.
//
// Look and feel follows leading health apps (e.g. Whoop, Oura): a dark
// near-black background by default, one green accent for actions and
// progress, and green / amber / red reserved for health signals.
// Every text colour below passes WCAG AA contrast (4.5:1) on both
// `background` and `surface` in its theme.

export type ThemeColors = {
  // Page background (lowest layer).
  background: string;
  // Cards and the header (one layer up).
  surface: string;
  // Menus and pop-ups (top layer). In dark mode, higher layers are lighter.
  surfaceRaised: string;
  border: string;
  text: string;
  textMuted: string;
  // Accent for actions, active states and progress.
  primary: string;
  primarySoft: string;
  onPrimary: string;
  // Health signals only (e.g. a recovery score), never decoration.
  good: string;
  caution: string;
  alert: string;
  shadow: string;
};

export const darkColors: ThemeColors = {
  background: '#0D1215',
  surface: '#151C20',
  surfaceRaised: '#1D262B',
  border: '#26323A',
  text: '#ECF2F4',
  textMuted: '#9AA9B1',
  primary: '#2BD9A0',
  primarySoft: '#123A30',
  onPrimary: '#04241A',
  good: '#4ADE80',
  caution: '#FACC15',
  alert: '#F87171',
  shadow: 'rgba(0, 0, 0, 0.5)',
};

export const lightColors: ThemeColors = {
  background: '#F2F5F6',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFFFF',
  border: '#DCE3E6',
  text: '#0F171B',
  textMuted: '#55646C',
  primary: '#08704F',
  primarySoft: '#E1F4EC',
  onPrimary: '#FFFFFF',
  good: '#15803D',
  caution: '#A15C07',
  alert: '#B91C1C',
  shadow: 'rgba(15, 23, 27, 0.12)',
};
