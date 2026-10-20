import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

// Small form controls shared by the Settings page and the welcome steps.
// Each one takes `disabled` so the other person's profile is view-only.

export function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.field}>
      <Text style={[styles.label, { color: colors.text }]}>
        {label}
        {required && <Text style={{ color: colors.primary }}> *</Text>}
      </Text>
      {hint && <Text style={[styles.hint, { color: colors.textMuted }]}>{hint}</Text>}
      {children}
    </View>
  );
}

export function TextField({
  value,
  onChange,
  label,
  placeholder,
  multiline,
  disabled,
  inputMode,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
  multiline?: boolean;
  disabled?: boolean;
  inputMode?: 'text' | 'decimal' | 'numeric';
}) {
  const { colors } = useTheme();
  return (
    <TextInput
      value={value}
      onChangeText={onChange}
      accessibilityLabel={label}
      placeholder={placeholder}
      placeholderTextColor={colors.textMuted}
      multiline={multiline}
      editable={!disabled}
      inputMode={inputMode}
      style={[
        styles.input,
        multiline && styles.multiline,
        {
          color: colors.text,
          borderColor: colors.border,
          backgroundColor: disabled ? colors.surface : colors.background,
        },
      ]}
    />
  );
}

// Tappable "chips". With `multiple`, any number can be selected.
export function ChipSelect<T extends string>({
  options,
  selected,
  onChange,
  multiple,
  disabled,
}: {
  options: { value: T; label: string }[];
  selected: T[];
  onChange: (selected: T[]) => void;
  multiple?: boolean;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  const toggle = (value: T) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange(multiple ? [...selected, value] : [value]);
    }
  };
  return (
    <View style={styles.chips}>
      {options.map((option) => {
        const isSelected = selected.includes(option.value);
        return (
          <Pressable
            key={option.value}
            role={multiple ? 'checkbox' : 'radio'}
            // aria-checked (not accessibilityState) so the web reports the selection.
            aria-checked={isSelected}
            aria-disabled={disabled}
            disabled={disabled}
            onPress={() => toggle(option.value)}
            style={[
              styles.chip,
              {
                borderColor: isSelected ? colors.primary : colors.border,
                backgroundColor: isSelected ? colors.primarySoft : 'transparent',
              },
            ]}
          >
            <Text
              style={[
                styles.chipText,
                { color: isSelected ? colors.primary : colors.text },
                isSelected && styles.chipTextSelected,
              ]}
            >
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function ToggleRow({
  label,
  hint,
  value,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.toggleRow}>
      <View style={styles.toggleText}>
        <Text style={[styles.label, { color: colors.text }]}>{label}</Text>
        {hint && <Text style={[styles.hint, { color: colors.textMuted }]}>{hint}</Text>}
      </View>
      <Switch
        accessibilityLabel={label}
        value={value}
        onValueChange={onChange}
        disabled={disabled}
        trackColor={{ true: colors.primary, false: colors.border }}
        thumbColor={colors.surfaceRaised}
      />
    </View>
  );
}

export function Button({
  label,
  onPress,
  disabled,
  variant = 'primary',
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'secondary';
}) {
  const { colors } = useTheme();
  const primary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.button,
        primary
          ? { backgroundColor: colors.primary }
          : { borderWidth: 1, borderColor: colors.border },
        disabled && styles.buttonDisabled,
      ]}
    >
      <Text style={[styles.buttonText, { color: primary ? colors.onPrimary : colors.text }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  field: {
    gap: spacing.xs + 2,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
  },
  hint: {
    fontSize: 13,
    lineHeight: 18,
  },
  input: {
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  multiline: {
    minHeight: 88,
    textAlignVertical: 'top',
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  chipText: {
    fontSize: 14,
  },
  chipTextSelected: {
    fontWeight: '700',
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  toggleText: {
    flex: 1,
    gap: 2,
  },
  button: {
    minHeight: 44,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    fontSize: 15,
    fontWeight: '700',
  },
});
