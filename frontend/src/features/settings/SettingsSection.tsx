import { type ComponentType, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { ApiError, apiPatch, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import type { Converted } from './drafts';

type Settings = Schemas['ProfileSettings'];

type Props<Draft, Update> = {
  title: string;
  description?: string;
  settings: Settings;
  // Which part of the settings this section edits, e.g. 'training'.
  path: 'profile' | 'training' | 'diet' | 'display';
  toDraft: (settings: Settings) => Draft;
  toUpdate: (draft: Draft, requireAll: boolean) => Converted<Update>;
  Fields: ComponentType<{
    draft: Draft;
    onChange: (changes: Partial<Draft>) => void;
    disabled?: boolean;
  }>;
  onSaved: (settings: Settings) => void;
};

// One card on the Settings page with its own Save button, so saving one
// section never touches unsaved changes in another.
export function SettingsSection<Draft, Update>({
  title,
  description,
  settings,
  path,
  toDraft,
  toUpdate,
  Fields,
  onSaved,
}: Props<Draft, Update>) {
  const { colors } = useTheme();
  const [saved, setSaved] = useState<Draft>(() => toDraft(settings));
  const [draft, setDraft] = useState<Draft>(saved);
  const [message, setMessage] = useState<{ text: string; isError: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const canEdit = settings.can_edit;
  const changed = JSON.stringify(draft) !== JSON.stringify(saved);

  const save = async () => {
    // Only "Name" is required here; the rest can stay empty until the person is ready.
    const { values, problems } = toUpdate(draft, false);
    if (problems.length > 0) {
      setMessage({ text: problems.join(' '), isError: true });
      return;
    }
    setBusy(true);
    try {
      const updated = await apiPatch<Settings>(`/api/me/settings/${path}`, values);
      const fresh = toDraft(updated);
      setSaved(fresh);
      setDraft(fresh);
      setMessage({ text: 'Saved.', isError: false });
      onSaved(updated);
    } catch (error) {
      const text = error instanceof ApiError ? error.message : 'Couldn’t save. Please try again.';
      setMessage({ text, isError: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <View style={styles.heading}>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
        {description && (
          <Text style={[styles.description, { color: colors.textMuted }]}>{description}</Text>
        )}
      </View>
      <Fields
        draft={draft}
        onChange={(changes) => {
          setDraft((current) => ({ ...current, ...changes }));
          setMessage(null);
        }}
        disabled={!canEdit}
      />
      {canEdit && (
        <View style={styles.footer}>
          {message && (
            <Text
              accessibilityRole={message.isError ? 'alert' : undefined}
              style={[styles.message, { color: message.isError ? colors.alert : colors.good }]}
            >
              {message.text}
            </Text>
          )}
          <Button label={busy ? 'Saving…' : 'Save'} onPress={save} disabled={!changed || busy} />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.lg,
    gap: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  heading: {
    gap: spacing.xs,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  description: {
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  message: {
    flex: 1,
    minWidth: 160,
    fontSize: 14,
    fontWeight: '600',
  },
});
