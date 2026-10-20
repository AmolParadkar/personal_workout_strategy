import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Button, Field, TextField } from '@/components/form';
import { useProfile } from '@/features/profile/ProfileContext';
import { ApiError, apiGet, apiPost, apiPut, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import { formatDay, type Item, itemLabels } from './items';

type State = Schemas['SeventyFiveHardState'];
type Day = Schemas['DayChecklist'];

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; state: State };

const errorText = (error: unknown) =>
  error instanceof ApiError ? error.message : 'Something went wrong. Please try again.';

export function SeventyFiveHardScreen() {
  const { activeProfile, reload } = useProfile();
  const { colors } = useTheme();
  const [loaded, setLoaded] = useState<{ profileId: string; load: LoadState } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<State>(`/api/profiles/${activeProfile.id}/seventy-five-hard`)
      .then((state): LoadState => ({ status: 'ready', state }))
      .catch((error): LoadState => ({ status: 'error', message: errorText(error) }))
      .then((load) => {
        if (!cancelled) setLoaded({ profileId: activeProfile.id, load });
      });
    return () => {
      cancelled = true;
    };
  }, [activeProfile.id]);

  const load: LoadState =
    loaded?.profileId === activeProfile.id ? loaded.load : { status: 'loading' };

  const show = (state: State) => setLoaded({ profileId: activeProfile.id, load: { status: 'ready', state } });

  // Runs a change, shows the new state, and refreshes the profile list
  // (so the 75 Hard link appears or disappears for the other person).
  const act = async (request: () => Promise<State>, refreshProfiles = false) => {
    setMessage(null);
    try {
      show(await request());
      if (refreshProfiles) reload();
    } catch (error) {
      setMessage(errorText(error));
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: colors.primary }]}>
          {activeProfile.display_name.toUpperCase()}
        </Text>
        <Text style={[styles.title, { color: colors.text }]}>75 Hard</Text>

        {message && (
          <Text accessibilityRole="alert" style={[styles.message, { color: colors.alert }]}>
            {message}
          </Text>
        )}

        {load.status === 'loading' && <ActivityIndicator color={colors.primary} />}
        {load.status === 'error' && <Text style={{ color: colors.alert }}>{load.message}</Text>}
        {load.status === 'ready' && load.state.status === 'not_started' && (
          <NotStarted
            name={activeProfile.display_name}
            canEdit={load.state.can_edit}
            onStart={(currentDay) =>
              act(
                () =>
                  apiPost<State>('/api/me/seventy-five-hard/start', {
                    current_day: currentDay,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                  }),
                true,
              )
            }
          />
        )}
        {load.status === 'ready' && load.state.status === 'active' && (
          <Active
            state={load.state}
            onToggle={(day, item, checked) =>
              act(() =>
                apiPut<State>('/api/me/seventy-five-hard/checks', { date: day.date, item, checked }),
              )
            }
            onOptimistic={show}
            onStop={() => act(() => apiPost<State>('/api/me/seventy-five-hard/stop'), true)}
          />
        )}
        {load.status === 'ready' && load.state.status === 'completed' && (
          <Completed
            state={load.state}
            onStartAgain={() => act(() => apiPost<State>('/api/me/seventy-five-hard/stop'), true)}
          />
        )}
      </View>
    </ScrollView>
  );
}

function NotStarted({
  name,
  canEdit,
  onStart,
}: {
  name: string;
  canEdit: boolean;
  onStart: (currentDay: number) => void;
}) {
  const { colors } = useTheme();
  const [day, setDay] = useState('1');
  const [problem, setProblem] = useState<string | null>(null);

  if (!canEdit) {
    return (
      <Card>
        <Text style={[styles.body, { color: colors.textMuted }]}>
          {name} isn’t doing 75 Hard right now.
        </Text>
      </Card>
    );
  }

  const start = () => {
    const value = Number(day);
    if (!Number.isInteger(value) || value < 1 || value > 75) {
      setProblem('Enter a day between 1 and 75.');
      return;
    }
    onStart(value);
  };

  return (
    <Card>
      <Text style={[styles.body, { color: colors.text }]}>
        Six rules, every day, for 75 days. Tick each one off here. If a day isn’t complete, the count
        starts again at Day 1. Forgot to tick? Yesterday stays open until 12:00.
      </Text>
      <Field label="What day are you on?" hint="Already started? Enter today’s day number.">
        <TextField
          label="What day are you on?"
          value={day}
          onChange={(value) => {
            setDay(value);
            setProblem(null);
          }}
          inputMode="numeric"
        />
      </Field>
      {problem && (
        <Text accessibilityRole="alert" style={[styles.message, { color: colors.alert }]}>
          {problem}
        </Text>
      )}
      <View style={styles.actionsRight}>
        <Button label="Start 75 Hard" onPress={start} />
      </View>
    </Card>
  );
}

function Active({
  state,
  onToggle,
  onOptimistic,
  onStop,
}: {
  state: State;
  onToggle: (day: Day, item: Item, checked: boolean) => void;
  onOptimistic: (state: State) => void;
  onStop: () => void;
}) {
  const { colors } = useTheme();
  const [confirmStop, setConfirmStop] = useState(false);
  const day = state.day ?? 1;

  // Tick straight away on screen, then confirm with the server.
  const toggle = (which: 'today' | 'yesterday', checklist: Day, item: Item, checked: boolean) => {
    const updated: Day = {
      ...checklist,
      items: checklist.items.map((i) => (i.item === item ? { ...i, checked } : i)),
    };
    onOptimistic({ ...state, [which]: updated });
    onToggle(checklist, item, checked);
  };

  return (
    <>
      <Card>
        <View style={styles.counterRow}>
          <Text style={[styles.counter, { color: colors.text }]}>Day {day}</Text>
          <Text style={[styles.counterTotal, { color: colors.textMuted }]}>
            of {state.total_days}
          </Text>
        </View>
        <View
          style={[styles.track, { backgroundColor: colors.border }]}
          accessibilityLabel={`Day ${day} of ${state.total_days}`}
        >
          <View
            style={[
              styles.fill,
              { backgroundColor: colors.primary, width: `${(day / state.total_days) * 100}%` },
            ]}
          />
        </View>
        {state.last_missed_on && (
          <Text style={[styles.note, { color: colors.textMuted }]}>
            Restarted at Day 1 because {formatDay(state.last_missed_on)} wasn’t complete.
          </Text>
        )}
      </Card>

      {state.yesterday && (
        <Checklist
          title={`Yesterday · Day ${state.yesterday.day}`}
          checklist={state.yesterday}
          warning="Tick yesterday’s items before 12:00, or the count starts again at Day 1."
          onToggle={(item, checked) => toggle('yesterday', state.yesterday!, item, checked)}
        />
      )}
      {state.today && (
        <Checklist
          title={`Today · Day ${state.today.day}`}
          checklist={state.today}
          onToggle={(item, checked) => toggle('today', state.today!, item, checked)}
        />
      )}

      {state.can_edit && (
        <View style={styles.stopRow}>
          {confirmStop ? (
            <>
              <Text style={[styles.note, { color: colors.text }]}>
                Stop the challenge? Your ticks are kept, but the count ends.
              </Text>
              <View style={styles.actionsRight}>
                <Button label="Cancel" variant="secondary" onPress={() => setConfirmStop(false)} />
                <Button label="Stop challenge" onPress={onStop} />
              </View>
            </>
          ) : (
            <Pressable accessibilityRole="button" onPress={() => setConfirmStop(true)}>
              <Text style={[styles.link, { color: colors.textMuted }]}>Stop challenge</Text>
            </Pressable>
          )}
        </View>
      )}
    </>
  );
}

function Checklist({
  title,
  checklist,
  warning,
  onToggle,
}: {
  title: string;
  checklist: Day;
  warning?: string;
  onToggle: (item: Item, checked: boolean) => void;
}) {
  const { colors } = useTheme();
  const done = checklist.items.filter((i) => i.checked).length;
  const complete = done === checklist.items.length;

  return (
    <Card>
      <View style={styles.checklistHeader}>
        <View>
          <Text style={[styles.cardTitle, { color: colors.text }]}>{title}</Text>
          <Text style={[styles.note, { color: colors.textMuted }]}>
            {formatDay(checklist.date)}
          </Text>
        </View>
        <Text style={[styles.done, { color: complete ? colors.good : colors.textMuted }]}>
          {complete ? 'Complete ✓' : `${done} of ${checklist.items.length}`}
        </Text>
      </View>
      {warning && !complete && checklist.editable && (
        <Text style={[styles.note, { color: colors.caution }]}>{warning}</Text>
      )}
      <View style={styles.items}>
        {checklist.items.map(({ item, checked }) => (
          <Pressable
            key={item}
            role="checkbox"
            aria-checked={checked}
            aria-disabled={!checklist.editable}
            disabled={!checklist.editable}
            onPress={() => onToggle(item, !checked)}
            style={[styles.itemRow, { borderColor: colors.border }]}
          >
            <View
              style={[
                styles.box,
                checked
                  ? { backgroundColor: colors.primary, borderColor: colors.primary }
                  : { borderColor: colors.textMuted },
              ]}
            >
              {checked && <Text style={[styles.tick, { color: colors.onPrimary }]}>✓</Text>}
            </View>
            <View style={styles.itemText}>
              <Text style={[styles.itemLabel, { color: colors.text }]}>{itemLabels[item].label}</Text>
              {itemLabels[item].hint !== '' && (
                <Text style={[styles.note, { color: colors.textMuted }]}>{itemLabels[item].hint}</Text>
              )}
            </View>
          </Pressable>
        ))}
      </View>
    </Card>
  );
}

function Completed({ state, onStartAgain }: { state: State; onStartAgain: () => void }) {
  const { colors } = useTheme();
  return (
    <Card>
      <Text style={[styles.counter, { color: colors.good }]}>75 Hard complete 🎉</Text>
      {state.completed_on && (
        <Text style={[styles.body, { color: colors.text }]}>
          All 75 days done, finishing on {formatDay(state.completed_on)}.
        </Text>
      )}
      {state.can_edit && (
        <View style={styles.actionsRight}>
          <Button label="Start a new challenge" onPress={onStartAgain} />
        </View>
      )}
    </Card>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
    paddingVertical: spacing.lg,
  },
  content: {
    width: '100%',
    maxWidth: 640,
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
    marginTop: -spacing.sm,
  },
  card: {
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  note: {
    fontSize: 13,
    lineHeight: 18,
  },
  message: {
    fontSize: 14,
    fontWeight: '600',
  },
  counterRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.sm,
  },
  counter: {
    fontSize: 40,
    fontWeight: '800',
    letterSpacing: -1,
  },
  counterTotal: {
    fontSize: 18,
    fontWeight: '600',
  },
  track: {
    height: 8,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: radius.pill,
  },
  checklistHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  done: {
    fontSize: 14,
    fontWeight: '700',
  },
  items: {
    gap: spacing.sm,
  },
  itemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  box: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tick: {
    fontSize: 14,
    fontWeight: '800',
  },
  itemText: {
    flex: 1,
    gap: 2,
  },
  itemLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  stopRow: {
    gap: spacing.sm,
    alignItems: 'flex-end',
  },
  link: {
    fontSize: 14,
    textDecorationLine: 'underline',
  },
  actionsRight: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: spacing.sm,
  },
});
