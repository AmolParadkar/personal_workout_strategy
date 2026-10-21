import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/form';
import { Overlay } from '@/components/Overlay';
import { pages } from '@/features/navigation/pages';
import { useProfile } from '@/features/profile/ProfileContext';
import { BodyWeightSection } from '@/features/settings/BodyWeightSection';
import { dayLabel, weekDays } from '@/features/workouts/plans';
import { ApiError, apiDelete, apiPost } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import { AddDishOverlay } from './AddDishOverlay';
import { ChatOverlay } from './ChatOverlay';
import { DayTargets } from './DayTargets';
import { GroceryListSection } from './GroceryListSection';
import { type MealDay, type MealPlan, useWeekMealPlan, type WeekMealPlan } from './meals';
import { MealRow } from './MealRow';

type Panel = 'groceries' | 'chat' | 'dish' | null;

// The week's meal plan (spec: context/pages/nutrition-plan.md): one day at a
// time, its targets in a line, its meals as rows to open. Grocery list, chat
// and adding a dish open over the page.
export function NutritionPlanScreen() {
  const { colors } = useTheme();
  const { activeProfile, canEdit } = useProfile();
  const { week, weekStart, error, setWeek } = useWeekMealPlan(activeProfile.id, canEdit);
  const today = todayLocal();
  const [chosenDay, setChosenDay] = useState<string | null>(null);
  const [eatingOut, setEatingOut] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [dishName, setDishName] = useState('');
  // A new key opens the dish form afresh each time.
  const [dishKey, setDishKey] = useState(0);
  const [more, setMore] = useState(false);

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
  const addDish = (name: string) => {
    setDishName(name);
    setDishKey((k) => k + 1);
    setPanel('dish');
  };

  const muted = { color: colors.textMuted };
  const text = { color: colors.text };
  const days = weekDays(weekStart);
  const plan = week?.active ?? null;
  const shown = week?.draft ?? plan;
  const planDays = shown?.days.map((d) => d.day) ?? [];
  const day =
    chosenDay && planDays.includes(chosenDay)
      ? chosenDay
      : planDays.includes(today)
        ? today
        : planDays[0];
  const current = shown?.days.find((d) => d.day === day);

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <View style={styles.titleRow}>
          <View style={styles.grow}>
            <Text style={[styles.eyebrow, { color: colors.primary }]}>
              {activeProfile.display_name.toUpperCase()} · {dayLabel(days[0], 'short')} –{' '}
              {dayLabel(days[6], 'short')}
            </Text>
            <Text style={[styles.title, text]}>{pages.nutritionPlan.title}</Text>
          </View>
          {plan && (
            <View style={styles.actions}>
              <HeaderButton label="🛒 Groceries" onPress={() => setPanel('groceries')} />
              {canEdit && <HeaderButton label="💬 Ask" onPress={() => setPanel('chat')} />}
            </View>
          )}
        </View>
        {!canEdit && <Text style={[styles.caption, muted]}>View-only</Text>}

        {error && <Text style={{ color: colors.alert }}>{error}</Text>}
        {!week && !error && <ActivityIndicator color={colors.primary} />}

        {week && canEdit && week.missing.length > 0 && (
          <View style={[styles.notice, { borderColor: colors.primary }]}>
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
          <View style={[styles.notice, styles.inline, { borderColor: colors.border }]}>
            <ActivityIndicator color={colors.primary} />
            <Text style={[styles.body, text]}>
              Making {plan ? 'a new plan' : 'this week’s meal plan'}… This page updates by itself.
            </Text>
          </View>
        )}

        {week?.draft && (
          <View
            style={[
              styles.notice,
              { borderColor: colors.primary, backgroundColor: colors.primarySoft },
            ]}
          >
            <Text style={[styles.sectionTitle, text]}>Preview</Text>
            {week.draft.change_note && (
              <Text style={[styles.body, text]}>{week.draft.change_note}</Text>
            )}
            <Differences current={plan} next={week.draft} />
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

        {shown && day && current && (
          <>
            <View style={styles.dayStrip} role="tablist">
              {planDays.map((d) => {
                const selected = d === day;
                const [y, m, n] = d.split('-').map(Number);
                const weekday = new Date(y, m - 1, n).toLocaleDateString(undefined, {
                  weekday: 'short',
                });
                const date = String(n);
                return (
                  <Pressable
                    key={d}
                    role="tab"
                    aria-selected={selected}
                    accessibilityLabel={dayLabel(d)}
                    onPress={() => setChosenDay(d)}
                    style={[
                      styles.dayChip,
                      {
                        borderColor: selected ? colors.primary : colors.border,
                        backgroundColor: selected ? colors.primary : 'transparent',
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.dayName,
                        { color: selected ? colors.onPrimary : colors.textMuted },
                      ]}
                    >
                      {d === today ? 'Today' : weekday}
                    </Text>
                    <Text
                      style={[styles.dayNum, { color: selected ? colors.onPrimary : colors.text }]}
                    >
                      {date}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <DaySummary day={current} />

            <View style={styles.meals}>
              {current.meals.map((meal) => (
                <MealRow
                  key={meal.id}
                  meal={meal}
                  canChange={canEdit && !week?.draft && day >= today}
                  selected={eatingOut.includes(meal.id)}
                  onToggleEatingOut={() =>
                    setEatingOut((ids) =>
                      ids.includes(meal.id) ? ids.filter((x) => x !== meal.id) : [...ids, meal.id],
                    )
                  }
                  onSwapped={setWeek}
                  onAddDish={addDish}
                />
              ))}
            </View>

            {eatingOut.length > 0 && (
              <View style={[styles.notice, { borderColor: colors.primary }]}>
                <Text style={[styles.body, text]}>
                  {eatingOut.length === 1 ? '1 meal' : `${eatingOut.length} meals`} eaten out. The
                  preview counts a meal out as richer and trims later days a little.
                </Text>
                <View style={styles.row}>
                  <Button
                    label={busy ? 'Working…' : 'Preview'}
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

            <Pressable
              accessibilityRole="button"
              aria-expanded={more}
              onPress={() => setMore((m) => !m)}
            >
              <Text style={[styles.link, { color: colors.primary }]}>
                {more ? 'Less' : 'About this plan'}
              </Text>
            </Pressable>
            {more && (
              <View style={styles.more}>
                <Text style={[styles.body, text]}>{shown.rationale}</Text>
                <Text style={[styles.caption, muted]}>
                  {shown.made_by === 'rules'
                    ? 'Dishes chosen by the app’s rules (the AI wasn’t available).'
                    : 'Dishes chosen by AI from your diet settings.'}{' '}
                  Portions and every number come from the food databases (USDA FoodData Central, the
                  Indian Nutrient Databank, and your household’s own dishes).
                </Text>
                {canEdit && !week?.generating && (
                  <View style={styles.row}>
                    <Button label="Add a dish" variant="secondary" onPress={() => addDish('')} />
                    <Button
                      label="Make a new plan"
                      variant="secondary"
                      onPress={() => generate('requested')}
                      disabled={busy}
                    />
                  </View>
                )}
              </View>
            )}
          </>
        )}
        {actionError && <Text style={{ color: colors.alert }}>{actionError}</Text>}
      </View>

      <Overlay title="Grocery list" open={panel === 'groceries'} onClose={() => setPanel(null)}>
        {plan && (
          <GroceryListSection
            weekStart={weekStart}
            profileId={activeProfile.id}
            name={activeProfile.display_name}
            refreshKey={`${plan.id}|${plan.days.map((d) => d.meals.map((m) => m.name).join()).join()}`}
          />
        )}
      </Overlay>
      {canEdit && (
        <ChatOverlay
          open={panel === 'chat'}
          onClose={() => setPanel(null)}
          onWeek={setWeek}
          onAddDish={addDish}
        />
      )}
      {canEdit && (
        <AddDishOverlay
          key={dishKey}
          open={panel === 'dish'}
          initialName={dishName}
          onClose={() => setPanel(null)}
        />
      )}
    </ScrollView>
  );
}

function HeaderButton({ label, onPress }: { label: string; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={[styles.headerButton, { borderColor: colors.border, backgroundColor: colors.surface }]}
    >
      <Text style={[styles.headerButtonText, { color: colors.text }]}>{label}</Text>
    </Pressable>
  );
}

// The day in one line: calories planned against the target, then protein, carbs
// and fat; tap for the reasons and vitamins and minerals.
function DaySummary({ day }: { day: MealDay }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const { targets, totals } = day;
  const macro = (label: string, planned: number, target: number) => (
    <Text style={[styles.macro, { color: colors.textMuted }]}>
      <Text style={{ color: colors.text, fontWeight: '700' }}>{Math.round(planned)}</Text>/{target}{' '}
      g {label}
    </Text>
  );
  return (
    <View style={styles.summaryWrap}>
      <Pressable
        accessibilityRole="button"
        aria-expanded={open}
        accessibilityLabel={`${Math.round(totals.kcal)} of ${targets.kcal} kcal planned. Details`}
        onPress={() => setOpen((o) => !o)}
        style={[styles.summary, { borderColor: colors.border, backgroundColor: colors.surface }]}
      >
        <View style={styles.kcalRow}>
          <Text style={[styles.kcalBig, { color: colors.text }]}>
            {Math.round(totals.kcal).toLocaleString()}
          </Text>
          <Text style={[styles.body, { color: colors.textMuted }]}>
            {' '}
            / {targets.kcal.toLocaleString()} kcal
          </Text>
          <Text style={[styles.caption, { color: colors.textMuted }, styles.push]}>
            {targets.training_minutes ? `Training ${targets.training_minutes} min` : 'Rest day'}{' '}
            {open ? '▴' : '▾'}
          </Text>
        </View>
        <View style={styles.macros}>
          {macro('protein', totals.protein_g, targets.protein_g)}
          {macro('carbs', totals.carbs_g, targets.carbs_g)}
          {macro('fat', totals.fat_g, targets.fat_g)}
        </View>
      </Pressable>
      {open && <DayTargets day={day} />}
    </View>
  );
}

// What the preview changes, e.g. "Sat dinner: eating out · Sun lunch: Rajma".
function Differences({ current, next }: { current: MealPlan | null; next: MealPlan }) {
  const { colors } = useTheme();
  if (!current) return null;
  const lines: string[] = [];
  for (const day of next.days) {
    const before = current.days.find((d) => d.day === day.day);
    for (const meal of day.meals) {
      const old = before?.meals.find((m) => m.position === meal.position);
      if (!old) continue;
      const label = `${dayLabel(day.day, 'short').replace(',', '').split(' ')[0]} ${meal.slot}`;
      if (meal.kind === 'eating_out' && old.kind !== 'eating_out') {
        lines.push(`${label}: eating out`);
      } else if (meal.name !== old.name) {
        lines.push(`${label}: ${meal.items.map((i) => i.name).join(', ')}`);
      } else if (Math.round(meal.nutrients.kcal) < Math.round(old.nutrients.kcal) - 5) {
        lines.push(`${label}: a little smaller`);
      }
    }
  }
  const first = lines.slice(0, 6);
  const rest = lines.length - first.length;
  return (
    <Text style={[styles.body, { color: colors.text }]}>
      {lines.length
        ? `${first.join(' · ')}${rest > 0 ? ` · and ${rest} more` : ''}`
        : 'Different dishes for the week.'}{' '}
      <Text style={{ color: colors.textMuted }}>The days below show the preview.</Text>
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
    maxWidth: 720,
    alignSelf: 'center',
    paddingHorizontal: spacing.md,
    gap: spacing.md,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  grow: {
    flexGrow: 1,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  headerButton: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  headerButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
  },
  body: {
    fontSize: 15,
    lineHeight: 21,
  },
  caption: {
    fontSize: 13,
    lineHeight: 18,
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
  notice: {
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  inline: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  dayStrip: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  dayChip: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  dayName: {
    fontSize: 11,
    fontWeight: '600',
  },
  dayNum: {
    fontSize: 16,
    fontWeight: '700',
  },
  summaryWrap: {
    gap: spacing.sm,
  },
  summary: {
    padding: spacing.md,
    gap: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  kcalRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    flexWrap: 'wrap',
  },
  kcalBig: {
    fontSize: 26,
    fontWeight: '800',
  },
  push: {
    marginLeft: 'auto',
  },
  macros: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  macro: {
    fontSize: 14,
  },
  meals: {
    gap: spacing.sm,
  },
  more: {
    gap: spacing.sm,
  },
});
