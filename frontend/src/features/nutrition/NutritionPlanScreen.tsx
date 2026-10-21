import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { BodyWeightSection } from '@/features/settings/BodyWeightSection';
import { dayLabel, weekDays } from '@/features/workouts/plans';
import { ApiError, apiDelete, apiPost } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import { DayTargets } from './DayTargets';
import { GroceryListSection } from './GroceryListSection';
import { MealCard } from './MealCard';
import { type MealPlan, useWeekMealPlan, type WeekMealPlan } from './meals';

// The week's meal plan (spec: context/pages/nutrition-plan.md): daily targets
// with reasons, meals by day, swaps, eating out with a preview, and the
// household grocery list.
export function NutritionPlanScreen() {
  const { colors } = useTheme();
  const { activeProfile, canEdit } = useProfile();
  const { week, weekStart, error, setWeek } = useWeekMealPlan(activeProfile.id, canEdit);
  const today = todayLocal();
  const [chosenDay, setChosenDay] = useState<string | null>(null);
  const [eatingOut, setEatingOut] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const act = async (request: () => Promise<WeekMealPlan>) => {
    setBusy(true);
    setActionError(null);
    try {
      setWeek(await request());
      setEatingOut([]);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const generate = (reason: 'new_week' | 'requested') =>
    act(() => apiPost<WeekMealPlan>('/api/me/meal-plan/generate', { today, reason }));

  const muted = { color: colors.textMuted };
  const text = { color: colors.text };
  const days = weekDays(weekStart);
  const plan = week?.active ?? null;
  const planDays = plan?.days.map((d) => d.day) ?? [];
  const day =
    chosenDay && planDays.includes(chosenDay)
      ? chosenDay
      : planDays.includes(today)
        ? today
        : planDays[0];

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: colors.primary }]}>
          {activeProfile.display_name.toUpperCase()}
        </Text>
        <Text style={[styles.title, text]}>{pages.nutritionPlan.title}</Text>
        <Text style={[styles.description, muted]}>
          {dayLabel(days[0], 'short')} – {dayLabel(days[6], 'short')}
          {canEdit ? '' : ` · ${activeProfile.display_name}’s plan (view-only)`}
        </Text>

        {error && <Text style={{ color: colors.alert }}>{error}</Text>}
        {!week && !error && <ActivityIndicator color={colors.primary} />}

        {week && canEdit && week.missing.length > 0 && (
          <View style={[styles.notice, styles.column, { borderColor: colors.primary }]}>
            <Text style={[styles.sectionTitle, text]}>One thing first</Text>
            {week.missing.includes('weight') ? (
              <>
                <Text style={[styles.body, text]}>
                  Your calorie and protein targets are worked out from your body weight. Add today’s
                  weight and your meal plan is made straight away.
                </Text>
                <BodyWeightSection
                  profileId={activeProfile.id}
                  onSaved={() => generate('new_week')}
                />
              </>
            ) : (
              <Text style={[styles.body, text]}>
                Add your date of birth and height in Settings → About you, then come back.
              </Text>
            )}
          </View>
        )}

        {week?.generating && (
          <View style={[styles.notice, { borderColor: colors.border }]}>
            <ActivityIndicator color={colors.primary} />
            <Text style={[styles.body, text]}>
              Making {week.active ? 'a new plan' : 'this week’s meal plan'}… This page updates by
              itself.
            </Text>
          </View>
        )}

        {week?.draft && (
          <View
            style={[
              styles.preview,
              { borderColor: colors.primary, backgroundColor: colors.surface },
            ]}
          >
            <Text style={[styles.sectionTitle, text]}>New plan ready to preview</Text>
            {week.draft.change_note && (
              <Text style={[styles.body, { color: colors.primary, fontWeight: '600' }]}>
                For: {week.draft.change_note}
              </Text>
            )}
            <Text style={[styles.body, muted]}>{week.draft.rationale}</Text>
            <Differences current={week.active} next={week.draft} />
            <View style={styles.row}>
              <Button
                label="Use this plan"
                onPress={() =>
                  act(() => apiPost<WeekMealPlan>(`/api/me/meal-plans/${week.draft!.id}/apply`))
                }
                disabled={busy}
              />
              <Button
                label="Keep current plan"
                variant="secondary"
                onPress={() =>
                  act(() => apiDelete<WeekMealPlan>(`/api/me/meal-plans/${week.draft!.id}`))
                }
                disabled={busy}
              />
            </View>
          </View>
        )}

        {week && !plan && !week.generating && week.missing.length === 0 && (
          <Text style={[styles.body, muted]}>
            {canEdit
              ? 'No meal plan for this week yet.'
              : `${activeProfile.display_name} has no meal plan for this week yet.`}
          </Text>
        )}

        {plan && day && (
          <>
            <Text style={[styles.body, text]}>{plan.rationale}</Text>
            <Text style={[styles.caption, muted]}>
              {plan.made_by === 'rules'
                ? 'Dishes chosen by the app’s rules (the AI wasn’t available).'
                : 'Dishes chosen by AI from your diet settings.'}{' '}
              Portions and every number come from the food databases (USDA FoodData Central and the
              Indian Nutrient Databank).
            </Text>
            <View style={styles.dayChips} accessibilityRole="tablist">
              {planDays.map((d) => {
                const selected = d === day;
                return (
                  <Pressable
                    key={d}
                    role="tab"
                    aria-selected={selected}
                    onPress={() => setChosenDay(d)}
                    style={[
                      styles.dayChip,
                      {
                        borderColor: selected ? colors.primary : colors.border,
                        backgroundColor: selected ? colors.primarySoft : 'transparent',
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.dayChipText,
                        { color: selected ? colors.primary : colors.text },
                      ]}
                    >
                      {d === today ? 'Today' : dayLabel(d, 'short').split(' ')[0]}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <DayView
              plan={plan}
              day={day}
              canChange={canEdit && !week?.draft && day >= today}
              eatingOut={eatingOut}
              onToggle={(id) =>
                setEatingOut((ids) =>
                  ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id],
                )
              }
              onSwapped={setWeek}
            />
            {eatingOut.length > 0 && (
              <View style={[styles.notice, styles.column, { borderColor: colors.primary }]}>
                <Text style={[styles.body, text]}>
                  {eatingOut.length === 1 ? '1 meal' : `${eatingOut.length} meals`} marked as eating
                  out. The preview counts each as a richer meal and trims later days a little to
                  keep the week on target.
                </Text>
                <View style={styles.row}>
                  <Button
                    label={busy ? 'Working…' : 'Preview the change'}
                    onPress={() =>
                      act(() =>
                        apiPost<WeekMealPlan>('/api/me/meal-plan/eating-out', {
                          today,
                          meal_ids: eatingOut,
                        }),
                      )
                    }
                    disabled={busy}
                  />
                  <Button label="Clear" variant="secondary" onPress={() => setEatingOut([])} />
                </View>
              </View>
            )}
          </>
        )}

        {canEdit && week && !week.generating && week.missing.length === 0 && (
          <View style={styles.row}>
            <Button
              label="Make a new plan"
              variant="secondary"
              onPress={() => generate('requested')}
              disabled={busy}
            />
          </View>
        )}
        {actionError && <Text style={{ color: colors.alert }}>{actionError}</Text>}

        {plan && (
          <GroceryListSection
            weekStart={weekStart}
            profileId={activeProfile.id}
            name={activeProfile.display_name}
            refreshKey={`${plan?.id ?? ''}|${plan?.days.map((d) => d.meals.map((m) => m.name).join()).join()}`}
          />
        )}
      </View>
    </ScrollView>
  );
}

function DayView({
  plan,
  day,
  canChange,
  eatingOut,
  onToggle,
  onSwapped,
}: {
  plan: MealPlan;
  day: string;
  canChange: boolean;
  eatingOut: string[];
  onToggle: (id: string) => void;
  onSwapped: (week: WeekMealPlan) => void;
}) {
  const found = plan.days.find((d) => d.day === day);
  if (!found) return null;
  return (
    <View style={styles.dayView}>
      <DayTargets day={found} />
      {found.meals.map((meal) => (
        <MealCard
          key={meal.id}
          meal={meal}
          canChange={canChange}
          selected={eatingOut.includes(meal.id)}
          onToggleEatingOut={() => onToggle(meal.id)}
          onSwapped={onSwapped}
        />
      ))}
    </View>
  );
}

// What the preview changes, e.g. "Sat dinner: Eating out; Sun lunch: smaller portions".
function Differences({ current, next }: { current: MealPlan | null; next: MealPlan }) {
  const { colors } = useTheme();
  if (!current) return null;
  const lines: string[] = [];
  for (const day of next.days) {
    const before = current.days.find((d) => d.day === day.day);
    for (const meal of day.meals) {
      const old = before?.meals.find((m) => m.position === meal.position);
      if (!old) continue;
      const label = `${dayLabel(day.day, 'short').split(' ')[0]} ${meal.slot}`;
      if (meal.kind === 'eating_out' && old.kind !== 'eating_out') {
        lines.push(`${label}: eating out`);
      } else if (meal.name !== old.name) {
        lines.push(`${label}: ${meal.name}`);
      } else if (Math.round(meal.nutrients.kcal) < Math.round(old.nutrients.kcal)) {
        lines.push(
          `${label}: a smaller portion (${Math.round(old.nutrients.kcal - meal.nutrients.kcal)} kcal less)`,
        );
      }
    }
  }
  return (
    <Text style={[styles.body, { color: colors.text }]}>
      {lines.length ? `What changes: ${lines.join('; ')}.` : 'Different dishes for the week.'}
    </Text>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.lg,
  },
  content: {
    width: '100%',
    maxWidth: 760,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    gap: spacing.md,
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
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  caption: {
    fontSize: 13,
    lineHeight: 18,
  },
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  column: {
    flexDirection: 'column',
    alignItems: 'stretch',
  },
  preview: {
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 2,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  dayChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  dayChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  dayChipText: {
    fontSize: 14,
    fontWeight: '600',
  },
  dayView: {
    gap: spacing.sm,
  },
});
