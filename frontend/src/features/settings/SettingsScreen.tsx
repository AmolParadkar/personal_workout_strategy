import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { spacing, useTheme } from '@/theme';

import { AppleHealthSection } from './AppleHealthSection';
import { BodyWeightSection } from './BodyWeightSection';
import { ConnectionsSection } from './ConnectionsSection';
import {
  aboutDraft,
  aboutUpdate,
  dietDraft,
  dietUpdate,
  sourcesDraft,
  sourcesUpdate,
  trainingDraft,
  trainingUpdate,
  waterDraft,
  waterUpdate,
} from './drafts';
import {
  AboutYouFields,
  DisplayFields,
  FoodFields,
  SourcesFields,
  TrainingFields,
  WaterFields,
} from './SettingsFields';
import { SettingsSection } from './SettingsSection';
import { useProfileSettings } from './useProfileSettings';

export function SettingsScreen() {
  const { activeProfile, canEdit, reload } = useProfile();
  const { colors } = useTheme();
  const { state, setSettings } = useProfileSettings(activeProfile.id);

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: colors.primary }]}>
          {activeProfile.display_name.toUpperCase()}
        </Text>
        <Text style={[styles.title, { color: colors.text }]}>{pages.settings.title}</Text>
        <Text style={[styles.description, { color: colors.textMuted }]}>
          {canEdit
            ? 'These details shape your workout and meal plans. Fields marked * are needed before plans can be made.'
            : `You’re viewing ${activeProfile.display_name}’s settings, so they’re view-only.`}
        </Text>

        {state.status === 'loading' && <ActivityIndicator color={colors.primary} />}
        {state.status === 'error' && (
          <Text style={{ color: colors.alert }}>{state.message}</Text>
        )}
        {state.status === 'ready' && (
          // `key` resets the sections' drafts when switching profile.
          <View key={state.settings.profile_id} style={styles.sections}>
            <SettingsSection
              title="About you"
              settings={state.settings}
              path="profile"
              toDraft={aboutDraft}
              toUpdate={aboutUpdate}
              Fields={AboutYouFields}
              onSaved={(updated) => {
                setSettings(updated);
                // The name in the profile dropdown may have changed.
                reload();
              }}
            />
            <BodyWeightSection profileId={state.settings.profile_id} />
            <SettingsSection
              title="Training"
              description="Used to build your weekly workout plan."
              settings={state.settings}
              path="training"
              toDraft={trainingDraft}
              toUpdate={trainingUpdate}
              Fields={TrainingFields}
              onSaved={setSettings}
            />
            <SettingsSection
              title="Food"
              description="Used to build your weekly meal plan."
              settings={state.settings}
              path="diet"
              toDraft={dietDraft}
              toUpdate={dietUpdate}
              Fields={FoodFields}
              onSaved={setSettings}
            />
            <SettingsSection
              title="Water"
              description="Your daily target on the Plan for Today water card."
              settings={state.settings}
              path="profile"
              toDraft={waterDraft}
              toUpdate={waterUpdate}
              Fields={WaterFields}
              onSaved={setSettings}
            />
            <SettingsSection
              title="Summary cards"
              description="Weight and calorie cards are off by default. Turn them on only if seeing these numbers helps you."
              settings={state.settings}
              path="display"
              toDraft={(settings) => settings.display}
              toUpdate={(draft) => ({ values: draft, problems: [] })}
              Fields={DisplayFields}
              onSaved={setSettings}
            />
            <SettingsSection
              title="Apps and devices you use"
              description="Tell us what you use, so we can connect the right ones and give you the right tips. Optional."
              settings={state.settings}
              path="profile"
              toDraft={sourcesDraft}
              toUpdate={sourcesUpdate}
              Fields={SourcesFields}
              onSaved={setSettings}
            />
            <ConnectionsSection profileId={state.settings.profile_id} />
            {state.settings.can_edit && <AppleHealthSection />}
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.lg,
  },
  content: {
    width: '100%',
    // Narrower than other pages: long forms are easier to read.
    maxWidth: 760,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  description: {
    fontSize: 16,
    lineHeight: 22,
    marginBottom: spacing.md,
  },
  sections: {
    gap: spacing.lg,
  },
});
