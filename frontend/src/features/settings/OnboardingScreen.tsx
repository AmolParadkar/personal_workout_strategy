import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { ApiError, apiPatch, apiPost, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import {
  aboutDraft,
  aboutUpdate,
  dietDraft,
  dietUpdate,
  trainingDraft,
  trainingUpdate,
  type AboutDraft,
  type DietDraft,
  type TrainingDraft,
} from './drafts';
import { AboutYouFields, FoodFields, TrainingFields } from './SettingsFields';
import { useProfileSettings } from './useProfileSettings';

type Settings = Schemas['ProfileSettings'];

const STEPS = [
  { title: 'About you', subtitle: 'The basics your plans are built on.' },
  { title: 'Training', subtitle: 'When, where and how long you can train.' },
  { title: 'Food', subtitle: 'What you eat, so meal plans fit your life.' },
] as const;

// The first-sign-in questions: three short steps, saved one at a time, so
// nothing is lost if the page is closed halfway. Everything can be changed
// later in Settings.
export function OnboardingScreen({ profileId, onDone }: { profileId: string; onDone: () => void }) {
  const { colors } = useTheme();
  const { state } = useProfileSettings(profileId);

  if (state.status !== 'ready') {
    return (
      <View style={styles.centered}>
        {state.status === 'loading' ? (
          <ActivityIndicator color={colors.primary} />
        ) : (
          <Text style={{ color: colors.alert }}>{state.message}</Text>
        )}
      </View>
    );
  }
  return <OnboardingSteps settings={state.settings} onDone={onDone} />;
}

function OnboardingSteps({ settings, onDone }: { settings: Settings; onDone: () => void }) {
  const { colors } = useTheme();
  const [step, setStep] = useState(0);
  const [about, setAbout] = useState<AboutDraft>(() => aboutDraft(settings));
  const [training, setTraining] = useState<TrainingDraft>(() => trainingDraft(settings));
  const [diet, setDiet] = useState<DietDraft>(() => dietDraft(settings));
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const isLast = step === STEPS.length - 1;

  const saveStep = async () => {
    // Every required field must be filled before moving on.
    const converted =
      step === 0 ? aboutUpdate(about, true) : step === 1 ? trainingUpdate(training, true) : dietUpdate(diet, true);
    if (converted.problems.length > 0) {
      setProblems(converted.problems);
      return;
    }
    const path = step === 0 ? 'profile' : step === 1 ? 'training' : 'diet';
    setBusy(true);
    setProblems([]);
    try {
      await apiPatch<Settings>(`/api/me/settings/${path}`, converted.values);
      if (isLast) {
        await apiPost<Settings>('/api/me/onboarding/complete');
        onDone();
        return;
      }
      setStep(step + 1);
    } catch (error) {
      setProblems([error instanceof ApiError ? error.message : 'Couldn’t save. Please try again.']);
    } finally {
      setBusy(false);
    }
  };

  const clearProblems = () => setProblems([]);

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <View style={styles.brand}>
          <View style={[styles.brandMark, { backgroundColor: colors.primary }]} />
          <Text style={[styles.appName, { color: colors.text }]}>Welcome to Workout Strategy</Text>
        </View>
        <Text style={[styles.intro, { color: colors.textMuted }]}>
          Three quick steps before your first plans. You can change any of this later in Settings.
        </Text>

        <View style={styles.progress} accessibilityLabel={`Step ${step + 1} of ${STEPS.length}`}>
          {STEPS.map((s, index) => (
            <View
              key={s.title}
              style={[
                styles.progressBar,
                { backgroundColor: index <= step ? colors.primary : colors.border },
              ]}
            />
          ))}
        </View>

        <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          <View style={styles.heading}>
            <Text style={[styles.stepLabel, { color: colors.primary }]}>
              STEP {step + 1} OF {STEPS.length}
            </Text>
            <Text style={[styles.title, { color: colors.text }]}>{STEPS[step].title}</Text>
            <Text style={[styles.subtitle, { color: colors.textMuted }]}>{STEPS[step].subtitle}</Text>
          </View>

          {step === 0 && (
            <AboutYouFields
              draft={about}
              onChange={(c) => {
                setAbout({ ...about, ...c });
                clearProblems();
              }}
            />
          )}
          {step === 1 && (
            <TrainingFields
              draft={training}
              onChange={(c) => {
                setTraining({ ...training, ...c });
                clearProblems();
              }}
            />
          )}
          {step === 2 && (
            <FoodFields
              draft={diet}
              onChange={(c) => {
                setDiet({ ...diet, ...c });
                clearProblems();
              }}
            />
          )}

          {problems.length > 0 && (
            <View accessibilityRole="alert" style={styles.problems}>
              {problems.map((problem) => (
                <Text key={problem} style={[styles.problem, { color: colors.alert }]}>
                  {problem}
                </Text>
              ))}
            </View>
          )}

          <View style={styles.actions}>
            {step > 0 ? (
              <Button
                label="Back"
                variant="secondary"
                onPress={() => {
                  setStep(step - 1);
                  clearProblems();
                }}
                disabled={busy}
              />
            ) : (
              <View />
            )}
            <Button
              label={busy ? 'Saving…' : isLast ? 'Finish' : 'Next'}
              onPress={saveStep}
              disabled={busy}
            />
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.xl,
  },
  content: {
    width: '100%',
    maxWidth: 640,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    gap: spacing.md,
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
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: -0.4,
  },
  intro: {
    fontSize: 15,
    lineHeight: 21,
  },
  progress: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  progressBar: {
    flex: 1,
    height: 6,
    borderRadius: radius.pill,
  },
  card: {
    padding: spacing.lg,
    gap: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  heading: {
    gap: spacing.xs,
  },
  stepLabel: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
  },
  subtitle: {
    fontSize: 15,
  },
  problems: {
    gap: spacing.xs,
  },
  problem: {
    fontSize: 14,
    fontWeight: '600',
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
});
