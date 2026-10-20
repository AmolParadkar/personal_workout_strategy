import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { radius, spacing, useTheme } from '@/theme';

import { useAuth } from './AuthContext';

export function SignInScreen() {
  const { signIn } = useAuth();
  const { colors } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = email.trim() !== '' && password !== '' && !busy;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const message = await signIn(email.trim(), password);
    // On success the layout notices the new session and leaves this page.
    if (message) {
      setError(message);
      setBusy(false);
    }
  };

  const inputStyle = [
    styles.input,
    { color: colors.text, borderColor: colors.border, backgroundColor: colors.background },
  ];

  return (
    <View style={[styles.screen, { backgroundColor: colors.background }]}>
      <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
        <View style={styles.brand}>
          <View style={[styles.brandMark, { backgroundColor: colors.primary }]} />
          <Text style={[styles.appName, { color: colors.text }]}>Workout Strategy</Text>
        </View>
        <Text style={[styles.subtitle, { color: colors.textMuted }]}>Sign in to continue</Text>

        <View style={styles.field}>
          <Text style={[styles.label, { color: colors.textMuted }]}>Email</Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            inputMode="email"
            accessibilityLabel="Email"
            style={inputStyle}
          />
        </View>
        <View style={styles.field}>
          <Text style={[styles.label, { color: colors.textMuted }]}>Password</Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="current-password"
            accessibilityLabel="Password"
            onSubmitEditing={submit}
            style={inputStyle}
          />
        </View>

        {error && (
          <Text accessibilityRole="alert" style={[styles.error, { color: colors.alert }]}>
            {error}
          </Text>
        )}

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !canSubmit }}
          onPress={submit}
          disabled={!canSubmit}
          style={[
            styles.button,
            { backgroundColor: colors.primary, opacity: canSubmit || busy ? 1 : 0.5 },
          ]}
        >
          {busy ? (
            <ActivityIndicator color={colors.onPrimary} />
          ) : (
            <Text style={[styles.buttonText, { color: colors.onPrimary }]}>Sign in</Text>
          )}
        </Pressable>

        <Text style={[styles.note, { color: colors.textMuted }]}>
          Accounts are by invitation only.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.md,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    padding: spacing.xl,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  brand: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  brandMark: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  appName: {
    fontSize: 22,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  subtitle: {
    fontSize: 15,
    marginTop: -spacing.sm,
  },
  field: {
    gap: spacing.xs,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
  },
  input: {
    height: 46,
    paddingHorizontal: spacing.md,
    fontSize: 16,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  error: {
    fontSize: 14,
    fontWeight: '600',
  },
  button: {
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
    marginTop: spacing.xs,
  },
  buttonText: {
    fontSize: 16,
    fontWeight: '700',
  },
  note: {
    fontSize: 13,
    textAlign: 'center',
  },
});
