import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button, ChipSelect } from '@/components/form';
import { useProfile } from '@/features/profile/ProfileContext';
import {
  dayLabel,
  ensureWeekPlan,
  PHASES,
  type PlanItem,
  prescription,
} from '@/features/workouts/plans';
import { ApiError, apiDelete, apiGet, apiPost, apiPut, type Schemas } from '@/lib/api';
import { todayLocal } from '@/lib/dates';
import { radius, spacing, useTheme } from '@/theme';

type Today = Schemas['TodayWorkout'];
type SetLog = Schemas['SetLog'];
type Effort = 'easy' | 'right' | 'too_hard';

const PLAN_POLL_MS = 5000;

const EFFORTS: { value: Effort; label: string }[] = [
  { value: 'easy', label: 'Easy' },
  { value: 'right', label: 'Just right' },
  { value: 'too_hard', label: 'Too hard' },
];

// Today's workout on Plan for Today (spec: context/pages/plan-for-today.md):
// log each set, tick timed moves, finish with how hard it felt, and the streak.
export function WorkoutCard() {
  const { colors } = useTheme();
  const { activeProfile } = useProfile();
  const day = todayLocal();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ key: string; today: Today } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = `${activeProfile.id}|${day}|${sessionId ?? ''}`;
  const today = loaded?.key === key ? loaded.today : null;

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ day });
    if (sessionId) params.set('session_id', sessionId);
    // Your own: wait for this week's plan to be made first (a new week's first open).
    (activeProfile.is_own ? ensureWeekPlan() : Promise.resolve())
      .then(() => apiGet<Today>(`/api/profiles/${activeProfile.id}/workout-today?${params}`))
      .then((found) => {
        if (!cancelled) setLoaded({ key, today: found });
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Couldn’t load the workout.');
      });
    return () => {
      cancelled = true;
    };
  }, [key, activeProfile.id, activeProfile.is_own, day, sessionId]);

  // No plan yet (the Mac worker may still be making it): check back every few seconds.
  const waiting = !!today && !today.has_plan && today.can_edit;
  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ day });
      apiGet<Today>(`/api/profiles/${activeProfile.id}/workout-today?${params}`)
        .then((found) => setLoaded({ key, today: found }))
        .catch(() => {});
    }, PLAN_POLL_MS);
    return () => clearTimeout(timer);
  }, [waiting, today, key, activeProfile.id, day]);

  const setToday = (next: Today) => setLoaded({ key, today: next });
  const card = [styles.card, { borderColor: colors.border, backgroundColor: colors.surface }];
  const text = { color: colors.text };
  const muted = { color: colors.textMuted };

  if (!today) {
    return (
      <View style={card}>
        <Text style={[styles.title, text]}>Workout</Text>
        {error ? (
          <Text style={{ color: colors.alert }}>{error}</Text>
        ) : (
          <ActivityIndicator color={colors.primary} />
        )}
      </View>
    );
  }

  const streak = today.streak > 0 && (
    <Text style={[styles.streak, { color: colors.good }]}>
      {today.streak} planned workout{today.streak === 1 ? '' : 's'} in a row
    </Text>
  );

  if (!today.has_plan || !today.session) {
    return (
      <View style={card}>
        <Text style={[styles.title, text]}>Workout</Text>
        {streak}
        <Text style={[styles.body, muted]}>
          {!today.has_plan
            ? today.can_edit
              ? 'Your plan for this week is being made… This updates by itself.'
              : 'No plan for this week yet.'
            : 'Rest day today. Recovery is part of the plan.'}
        </Text>
        {today.can_edit && today.catch_up.length > 0 && (
          <View style={styles.catchUp}>
            <Text style={[styles.body, text]}>
              Missed a session earlier this week? You can still do it:
            </Text>
            {today.catch_up.map((c) => (
              <Button
                key={c.session_id}
                label={`Do ${dayLabel(c.day, 'short')}: ${c.title}`}
                variant="secondary"
                onPress={() => setSessionId(c.session_id)}
              />
            ))}
          </View>
        )}
        <Link href="/workout-plan" style={[styles.link, { color: colors.primary }]}>
          See the week’s plan →
        </Link>
      </View>
    );
  }

  const session = today.session;
  const catchingUp = session.day !== day;

  return (
    <View style={card}>
      <View style={styles.header}>
        <Text style={[styles.eyebrow, { color: colors.primary }]}>
          {catchingUp
            ? `CATCHING UP: ${dayLabel(session.day, 'short').toUpperCase()}`
            : 'TODAY’S WORKOUT'}
        </Text>
        <Text style={[styles.title, text]}>{session.title}</Text>
        <Text style={[styles.body, muted]}>
          {session.minutes} min · {session.explanation}
        </Text>
        {streak}
      </View>

      {PHASES.map((phase) => {
        const items = session.items.filter((i) => i.phase === phase.key);
        if (!items.length) return null;
        return (
          <View key={phase.key} style={styles.phase}>
            <Text style={[styles.phaseLabel, muted]}>{phase.label.toUpperCase()}</Text>
            {items.map((item) => (
              <ItemLogger
                key={item.id}
                item={item}
                logs={today.logs.filter((l) => l.session_item_id === item.id)}
                canEdit={today.can_edit}
                onLogged={(log) =>
                  setToday({
                    ...today,
                    logs: [
                      ...today.logs.filter(
                        (l) =>
                          l.id !== log.id &&
                          !(
                            l.session_item_id === log.session_item_id &&
                            l.set_number === log.set_number
                          ),
                      ),
                      log,
                    ],
                  })
                }
                onRemoved={(id) =>
                  setToday({ ...today, logs: today.logs.filter((l) => l.id !== id) })
                }
              />
            ))}
          </View>
        );
      })}

      <Finish today={today} sessionId={session.id} onChanged={setToday} />
      {catchingUp && (
        <Button label="Back to today" variant="secondary" onPress={() => setSessionId(null)} />
      )}
    </View>
  );
}

function ItemLogger({
  item,
  logs,
  canEdit,
  onLogged,
  onRemoved,
}: {
  item: PlanItem;
  logs: SetLog[];
  canEdit: boolean;
  onLogged: (log: SetLog) => void;
  onRemoved: (id: string) => void;
}) {
  const { colors } = useTheme();
  const timed = !item.reps_min;
  const sets = item.sets ?? 1;

  return (
    <View style={styles.item}>
      <Link
        href={`/exercises/${item.exercise_id}`}
        style={[styles.itemName, { color: colors.text }]}
      >
        {item.exercise_name}
      </Link>
      <Text style={[styles.caption, { color: colors.textMuted }]}>{prescription(item)}</Text>
      {item.notes && <Text style={[styles.caption, { color: colors.primary }]}>{item.notes}</Text>}
      {timed ? (
        <TimedDone
          item={item}
          log={logs.find((l) => l.set_number === 1)}
          canEdit={canEdit}
          onLogged={onLogged}
          onRemoved={onRemoved}
        />
      ) : (
        Array.from({ length: sets }, (_, index) => (
          <SetRow
            key={index}
            item={item}
            setNumber={index + 1}
            log={logs.find((l) => l.set_number === index + 1)}
            canEdit={canEdit}
            onLogged={onLogged}
          />
        ))
      )}
    </View>
  );
}

function SetRow({
  item,
  setNumber,
  log,
  canEdit,
  onLogged,
}: {
  item: PlanItem;
  setNumber: number;
  log: SetLog | undefined;
  canEdit: boolean;
  onLogged: (log: SetLog) => void;
}) {
  const { colors } = useTheme();
  const [reps, setReps] = useState(log?.reps != null ? String(log.reps) : '');
  const [kg, setKg] = useState(log?.load_kg != null ? String(log.load_kg) : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const weighted = item.phase === 'main';
  const changed =
    reps !== (log?.reps != null ? String(log.reps) : '') ||
    kg !== (log?.load_kg != null ? String(log.load_kg) : '');

  const save = async () => {
    const repsNumber = Number(reps);
    const kgNumber = kg.trim() ? Number(kg.replace(',', '.')) : null;
    if (!reps.trim() || Number.isNaN(repsNumber) || (kgNumber !== null && Number.isNaN(kgNumber))) {
      setError(true);
      return;
    }
    setBusy(true);
    setError(false);
    try {
      onLogged(
        await apiPut<SetLog>('/api/me/exercise-logs', {
          session_item_id: item.id,
          set_number: setNumber,
          reps: repsNumber,
          load_kg: kgNumber,
        }),
      );
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  const input = [
    styles.input,
    { borderColor: error ? colors.alert : colors.border, color: colors.text },
  ];
  const target =
    item.reps_max && item.reps_max !== item.reps_min
      ? `${item.reps_min}–${item.reps_max}`
      : `${item.reps_min ?? ''}`;

  return (
    <View style={styles.setRow}>
      <Text style={[styles.setLabel, { color: colors.textMuted }]}>Set {setNumber}</Text>
      <TextInput
        value={reps}
        onChangeText={setReps}
        inputMode="numeric"
        placeholder={target}
        placeholderTextColor={colors.textMuted}
        accessibilityLabel={`${item.exercise_name} set ${setNumber} reps`}
        editable={canEdit}
        style={input}
      />
      <Text style={[styles.caption, { color: colors.textMuted }]}>reps</Text>
      {weighted && (
        <>
          <TextInput
            value={kg}
            onChangeText={setKg}
            inputMode="decimal"
            placeholder={item.target_load_kg ? String(item.target_load_kg) : '–'}
            placeholderTextColor={colors.textMuted}
            accessibilityLabel={`${item.exercise_name} set ${setNumber} kg`}
            editable={canEdit}
            style={input}
          />
          <Text style={[styles.caption, { color: colors.textMuted }]}>kg</Text>
        </>
      )}
      {canEdit && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Save ${item.exercise_name} set ${setNumber}`}
          onPress={save}
          disabled={busy || (!changed && !!log)}
          style={[
            styles.tick,
            {
              borderColor: log && !changed ? colors.good : colors.border,
              backgroundColor: log && !changed ? colors.good : 'transparent',
            },
          ]}
        >
          <Text
            style={{ color: log && !changed ? colors.onPrimary : colors.text, fontWeight: '700' }}
          >
            ✓
          </Text>
        </Pressable>
      )}
    </View>
  );
}

function TimedDone({
  item,
  log,
  canEdit,
  onLogged,
  onRemoved,
}: {
  item: PlanItem;
  log: SetLog | undefined;
  canEdit: boolean;
  onLogged: (log: SetLog) => void;
  onRemoved: (id: string) => void;
}) {
  const { colors } = useTheme();
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    setBusy(true);
    try {
      if (log) {
        await apiDelete(`/api/me/exercise-logs/${log.id}`);
        onRemoved(log.id);
      } else {
        onLogged(
          await apiPut<SetLog>('/api/me/exercise-logs', {
            session_item_id: item.id,
            set_number: 1,
            duration_seconds: (item.duration_seconds ?? 0) * (item.sets ?? 1),
          }),
        );
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityLabel={`${item.exercise_name} done`}
      aria-checked={!!log}
      disabled={!canEdit || busy}
      onPress={toggle}
      style={[styles.done, { borderColor: log ? colors.good : colors.border }]}
    >
      <Text style={{ color: log ? colors.good : colors.textMuted, fontWeight: '600' }}>
        {log ? '✓ Done' : canEdit ? 'Mark done' : 'Not done'}
      </Text>
    </Pressable>
  );
}

function Finish({
  today,
  sessionId,
  onChanged,
}: {
  today: Today;
  sessionId: string;
  onChanged: (today: Today) => void;
}) {
  const { colors } = useTheme();
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const done = today.completion;

  const complete = async (effort: Effort) => {
    setError(null);
    try {
      onChanged(
        await apiPost<Today>(`/api/me/sessions/${sessionId}/complete`, {
          done_on: todayLocal(),
          effort,
        }),
      );
      setFinishing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t save. Please try again.');
    }
  };
  const undo = async () => {
    onChanged(await apiDelete<Today>(`/api/me/sessions/${sessionId}/complete?day=${todayLocal()}`));
  };

  if (!today.can_edit) {
    return (
      <Text style={[styles.body, { color: colors.textMuted }]}>
        {done
          ? `✓ Done${done.effort ? ` · felt ${EFFORTS.find((e) => e.value === done.effort)?.label.toLowerCase()}` : ''}`
          : 'Not done yet.'}
      </Text>
    );
  }
  if (done && !finishing) {
    return (
      <View style={styles.finish}>
        <Text style={[styles.body, { color: colors.good, fontWeight: '700' }]}>
          ✓ Workout done
          {done.effort
            ? ` · felt ${EFFORTS.find((e) => e.value === done.effort)?.label.toLowerCase()}`
            : ''}
        </Text>
        <View style={styles.row}>
          <Button label="Change rating" variant="secondary" onPress={() => setFinishing(true)} />
          <Button label="Undo" variant="secondary" onPress={undo} />
        </View>
      </View>
    );
  }
  return (
    <View style={styles.finish}>
      {finishing ? (
        <>
          <Text style={[styles.body, { color: colors.text }]}>
            How hard was it? Next week’s plan uses this.
          </Text>
          <ChipSelect
            options={EFFORTS}
            selected={done?.effort ? [done.effort as Effort] : []}
            onChange={(picked) => picked[0] && complete(picked[0])}
          />
        </>
      ) : (
        <Button label="Finish workout" onPress={() => setFinishing(true)} />
      )}
      {error && <Text style={{ color: colors.alert }}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  header: {
    gap: 2,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  streak: {
    fontSize: 13,
    fontWeight: '700',
    marginTop: spacing.xs,
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
  },
  caption: {
    fontSize: 12,
    lineHeight: 16,
  },
  link: {
    fontSize: 14,
    fontWeight: '600',
  },
  catchUp: {
    gap: spacing.sm,
  },
  phase: {
    gap: spacing.sm,
  },
  phaseLabel: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
  },
  item: {
    gap: spacing.xs,
  },
  itemName: {
    fontSize: 15,
    fontWeight: '600',
  },
  setRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  setLabel: {
    width: 44,
    fontSize: 12,
  },
  input: {
    width: 56,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    fontSize: 15,
    textAlign: 'center',
  },
  tick: {
    width: 36,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    borderWidth: 1,
    marginLeft: spacing.xs,
  },
  done: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  finish: {
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
});
