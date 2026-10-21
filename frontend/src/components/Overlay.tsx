import type { ReactNode } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

// A panel over the page (grocery list, chat, adding a dish): full height on a
// phone, a centred card on wider screens. Closes with ✕, the backdrop or Escape.
export function Overlay({
  title,
  open,
  onClose,
  children,
  footer,
  scroll = true,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  // Stays at the bottom, outside the scrolling part (e.g. the chat's message box).
  footer?: ReactNode;
  scroll?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdropWrap}>
        <Pressable
          accessibilityLabel="Close"
          onPress={onClose}
          style={[StyleSheet.absoluteFill, { backgroundColor: colors.shadow }]}
        />
        <View
          role="dialog"
          aria-modal
          aria-label={title}
          style={[styles.panel, { backgroundColor: colors.background, borderColor: colors.border }]}
        >
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Close ${title.toLowerCase()}`}
              onPress={onClose}
              style={styles.close}
            >
              <Text style={[styles.closeText, { color: colors.textMuted }]}>✕</Text>
            </Pressable>
          </View>
          {scroll ? (
            <ScrollView contentContainerStyle={styles.body}>{children}</ScrollView>
          ) : (
            <View style={[styles.body, styles.grow]}>{children}</View>
          )}
          {footer && (
            <View style={[styles.footer, { borderTopColor: colors.border }]}>{footer}</View>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdropWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  panel: {
    width: '100%',
    maxWidth: 640,
    height: '100%',
    maxHeight: 820,
    borderRadius: radius.md,
    borderWidth: 1,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  close: {
    padding: spacing.sm,
  },
  closeText: {
    fontSize: 18,
  },
  body: {
    padding: spacing.md,
    gap: spacing.md,
  },
  grow: {
    flex: 1,
  },
  footer: {
    padding: spacing.sm,
    borderTopWidth: 1,
  },
});
