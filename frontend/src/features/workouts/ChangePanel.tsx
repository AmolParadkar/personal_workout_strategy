import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button, ChipSelect, Field, TextField } from '@/components/form';
import { ApiError, apiPost } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

import { dayLabel, type WeekPlan, weekDays } from './plans';

type Kind = 'day_off' | 'add_session' | 'shorter' | 'vacation' | 'cheat_meal' | 'medical' | 'other';

const KINDS: { value: Kind; label: string }[] = [
  { value: 'day_off', label: 'Can’t train on a day' },
  { value: 'add_session', label: 'Add a session' },
  { value: 'shorter', label: 'Less time on a day' },
  { value: 'vacation', label: 'Vacation' },
  { value: 'cheat_meal', label: 'Cheat meal day' },
  { value: 'medical', label: 'Medical emergency' },
  { value: 'other', label: 'Something else' },
];

const DATE = /^\d{4}-\d{2}-\d{2}$/;

// "Change this week" (spec: context/pages/workout-plan.md, "Changes"): each
// change makes a preview shown above, applied only with "Use this plan".
export function ChangePanel({
  week,
  onChanged,
}: {
  week: WeekPlan;
  onChanged: (week: WeekPlan) => void;
}) {
  const { colors } = useTheme();
  const today = todayLocal();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind[]>([]);
  const [day, setDay] = useState<string[]>([]);
  const [minutes, setMinutes] = useState('');
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState('');
  const [mode, setMode] = useState<string[]>([]);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sessionDays = new Set(week.active?.sessions.map((s) => s.day) ?? []);
  const remaining = weekDays(week.week_start).filter((d) => d >= today);
  const dayOptions = (which: 'with' | 'without' | 'any') =>
    remaining
      .filter((d) =>
        which === 'any' ? true : which === 'with' ? sessionDays.has(d) : !sessionDays.has(d),
      )
      .map((d) => ({ value: d, label: dayLabel(d, 'short') }));
  const chosen = kind[0];

  const reset = () => {
    setKind([]);
    setDay([]);
    setMinutes('');
    setStart(today);
    setEnd('');
    setMode([]);
    setNote('');
    setError(null);
  };

  const submit = async () => {
    setError(null);
    const body: Record<string, unknown> = { kind: chosen, today };
    if (chosen === 'day_off' || chosen === 'add_session' || chosen === 'shorter') {
      if (!day[0]) return setError('Choose a day.');
      body.start_date = day[0];
      if (chosen === 'shorter') body.minutes = Number(minutes) || null;
    } else {
      if (!DATE.test(start)) return setError('Start date as year-month-day, e.g. 2026-10-24.');
      if (end && !DATE.test(end)) return setError('End date as year-month-day, or leave it empty.');
      body.start_date = start;
      body.end_date = end || null;
      if (chosen === 'vacation') body.vacation_mode = mode[0] ?? null;
      if (chosen === 'cheat_meal') body.cheat_mode = mode[0] ?? null;
      if (chosen === 'other') body.note = note;
    }
    setBusy(true);
    try {
      onChanged(await apiPost<WeekPlan>('/api/me/workout-plan/changes', body));
      reset();
      setOpen(false);
    } catch (e) {
      setError(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : 'Couldn’t make that change. Please try again.',
      );
    } finally {
      setBusy(false);
    }
  };

  const endPause = async (changeId: string) => {
    setBusy(true);
    try {
      onChanged(await apiPost<WeekPlan>(`/api/me/plan-changes/${changeId}/end`, { today }));
    } catch {
      setError('Couldn’t end the pause. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const text = { color: colors.text };
  const muted = { color: colors.textMuted };
  const applied = week.changes.filter((c) => c.status === 'applied');

  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      {applied.length > 0 && (
        <View style={styles.list}>
          <Text style={[styles.heading, text]}>Changes this week</Text>
          {applied.map((c) => (
            <View key={c.id} style={styles.changeRow}>
              <Text style={[styles.body, text, styles.grow]}>{c.summary}</Text>
              {c.can_end && (
                <Button label="I’m back" onPress={() => endPause(c.id)} disabled={busy} />
              )}
            </View>
          ))}
        </View>
      )}

      {!open ? (
        <Button label="Change this week" variant="secondary" onPress={() => setOpen(true)} />
      ) : (
        <View style={styles.form}>
          <Text style={[styles.heading, text]}>What’s changing?</Text>
          <ChipSelect
            options={KINDS}
            selected={kind}
            onChange={(k) => {
              reset();
              setKind(k);
            }}
          />

          {chosen === 'day_off' && (
            <Field label="Which day?">
              <ChipSelect options={dayOptions('with')} selected={day} onChange={setDay} />
            </Field>
          )}
          {chosen === 'add_session' && (
            <Field label="Which day?" hint="The week rebalances around the extra session.">
              <ChipSelect options={dayOptions('without')} selected={day} onChange={setDay} />
            </Field>
          )}
          {chosen === 'shorter' && (
            <>
              <Field label="Which day?">
                <ChipSelect options={dayOptions('with')} selected={day} onChange={setDay} />
              </Field>
              <Field label="Minutes that day">
                <TextField
                  label="Minutes that day"
                  value={minutes}
                  onChange={setMinutes}
                  inputMode="numeric"
                  placeholder="e.g. 30"
                />
              </Field>
            </>
          )}
          {(chosen === 'vacation' || chosen === 'cheat_meal' || chosen === 'medical') && (
            <View style={styles.dates}>
              <Field label={chosen === 'cheat_meal' ? 'Which day?' : 'From'} hint="Year-month-day">
                <TextField
                  label="Start date"
                  value={start}
                  onChange={setStart}
                  placeholder="2026-10-24"
                />
              </Field>
              {chosen !== 'cheat_meal' && (
                <Field
                  label="Until"
                  hint={
                    chosen === 'medical'
                      ? 'Leave empty: paused until you tap “I’m back”.'
                      : 'Last day away'
                  }
                >
                  <TextField
                    label="End date"
                    value={end}
                    onChange={setEnd}
                    placeholder="2026-10-30"
                  />
                </Field>
              )}
            </View>
          )}
          {chosen === 'vacation' && (
            <Field label="Training while you’re away?">
              <ChipSelect
                options={[
                  { value: 'rest', label: 'No training' },
                  { value: 'travel', label: 'Short bodyweight sessions' },
                ]}
                selected={mode}
                onChange={setMode}
              />
            </Field>
          )}
          {chosen === 'cheat_meal' && (
            <Field label="What about your workouts?">
              <ChipSelect
                options={[
                  { value: 'spread', label: 'Spread the extra load across the week' },
                  { value: 'as_planned', label: 'Keep workouts as planned' },
                ]}
                selected={mode}
                onChange={setMode}
              />
            </Field>
          )}
          {chosen === 'medical' && (
            <Text style={[styles.body, muted]}>
              Training pauses from that day. When you’re back, the first week is lighter. Please
              follow your doctor’s advice on when to restart.
            </Text>
          )}
          {chosen === 'other' && (
            <Field
              label="Describe the change"
              hint="e.g. “My knee hurts, nothing heavy for legs this week”."
            >
              <TextField label="Describe the change" value={note} onChange={setNote} multiline />
            </Field>
          )}

          {error && <Text style={{ color: colors.alert }}>{error}</Text>}
          <View style={styles.row}>
            <Button
              label="Cancel"
              variant="secondary"
              onPress={() => {
                reset();
                setOpen(false);
              }}
            />
            {chosen && (
              <Button
                label={busy ? 'Working…' : 'Preview the change'}
                onPress={submit}
                disabled={busy}
              />
            )}
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.md,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  list: {
    gap: spacing.sm,
  },
  changeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  grow: {
    flex: 1,
  },
  form: {
    gap: spacing.md,
  },
  dates: {
    gap: spacing.sm,
  },
  heading: {
    fontSize: 16,
    fontWeight: '700',
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
});
