import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { Button, ChipSelect, Field, TextField } from '@/components/form';
import { pages } from '@/features/navigation/pages';
import { ApiError, apiGet, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import { equipmentOptions, muscleLabel, muscles } from './muscles';
import { WeekExercises } from './WeekExercises';

type ExerciseList = Schemas['ExerciseList'];
type Summary = Schemas['ExerciseSummary'];

const SEARCH_DELAY_MS = 300;

// The whole exercise library, searchable and filterable. From M6 the plan's
// exercises will be listed above it, grouped by day and phase.
export function ExerciseLibraryScreen() {
  const { colors } = useTheme();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [muscle, setMuscle] = useState<string[]>([]);
  const [equipment, setEquipment] = useState<string[]>([]);
  const [results, setResults] = useState<{
    key: string;
    items: Summary[];
    hasMore: boolean;
    suggestions: Summary[];
  } | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const activeFilters = muscle.length + equipment.length;
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Search once typing pauses, not on every key.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const params = new URLSearchParams();
  if (query) params.set('search', query);
  if (muscle[0]) params.set('muscle', muscle[0]);
  if (equipment[0]) params.set('equipment', equipment[0]);
  const key = params.toString();

  useEffect(() => {
    let cancelled = false;
    apiGet<ExerciseList>(`/api/exercises?${key}`)
      .then((list) => {
        if (!cancelled) {
          setResults({
            key,
            items: list.items,
            hasMore: list.has_more,
            suggestions: list.suggestions ?? [],
          });
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Couldn’t load exercises.');
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  const current = results?.key === key ? results : null;

  const loadMore = async () => {
    if (!current) return;
    setLoadingMore(true);
    try {
      const more = new URLSearchParams(key);
      more.set('offset', String(current.items.length));
      const list = await apiGet<ExerciseList>(`/api/exercises?${more}`);
      setResults({ ...current, items: [...current.items, ...list.items], hasMore: list.has_more });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Couldn’t load more.');
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Text style={[styles.title, { color: colors.text }]}>{pages.exerciseGuide.title}</Text>
        <Text style={[styles.description, { color: colors.textMuted }]}>
          How to do each exercise: muscles worked, form cues, precautions and a short video.
        </Text>

        <WeekExercises />

        <TextField
          label="Search exercises"
          value={search}
          onChange={setSearch}
          placeholder="e.g. squat, push-up, plank"
        />
        {/* Folded by default, so results show right under the search box on phones. */}
        <View style={styles.filterBar}>
          <Button
            label={`${showFilters ? 'Hide filters' : 'Filters'}${activeFilters ? ` (${activeFilters})` : ''}`}
            variant="secondary"
            onPress={() => setShowFilters((shown) => !shown)}
          />
          {activeFilters > 0 && (
            <Button
              label="Clear"
              variant="secondary"
              onPress={() => {
                setMuscle([]);
                setEquipment([]);
              }}
            />
          )}
        </View>
        {showFilters && (
          <>
            <Field label="Muscle">
              <ChipSelect
                options={muscles.map((m) => ({ value: m, label: muscleLabel(m) }))}
                selected={muscle}
                onChange={setMuscle}
              />
            </Field>
            <Field label="Equipment">
              <ChipSelect
                options={equipmentOptions.map((e) => ({ value: e, label: muscleLabel(e) }))}
                selected={equipment}
                onChange={setEquipment}
              />
            </Field>
          </>
        )}

        {error && (
          <Text accessibilityRole="alert" style={{ color: colors.alert }}>
            {error}
          </Text>
        )}
        {!current && !error && <ActivityIndicator color={colors.primary} />}
        {current && current.items.length === 0 && current.suggestions.length > 0 && (
          <Text style={{ color: colors.textMuted }}>
            No exact match for “{query}”. Closest matches:
          </Text>
        )}
        {current && current.items.length === 0 && current.suggestions.length === 0 && (
          <Text style={{ color: colors.textMuted }}>
            {query
              ? `Nothing close to “${query}”. Try another word, or fewer filters.`
              : 'No exercises match. Try fewer filters.'}
          </Text>
        )}

        <View style={styles.list}>
          {current?.items.map((exercise) => (
            <ExerciseRow key={exercise.id} exercise={exercise} />
          ))}
          {current?.items.length === 0 &&
            current.suggestions.map((exercise) => (
              <ExerciseRow key={exercise.id} exercise={exercise} />
            ))}
        </View>
        {current?.hasMore && (
          <Button
            label={loadingMore ? 'Loading…' : 'Show more'}
            variant="secondary"
            onPress={loadMore}
            disabled={loadingMore}
          />
        )}
      </View>
    </ScrollView>
  );
}

function ExerciseRow({ exercise }: { exercise: Summary }) {
  const { colors } = useTheme();
  const details = [
    exercise.primary_muscles.map(muscleLabel).join(', '),
    exercise.equipment && muscleLabel(exercise.equipment),
    exercise.level && muscleLabel(exercise.level),
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <Link href={`/exercises/${exercise.id}`} asChild>
      <Pressable
        style={StyleSheet.flatten([
          styles.row,
          { borderColor: colors.border, backgroundColor: colors.surface },
        ])}
      >
        {exercise.image ? (
          <Image
            source={{ uri: exercise.image }}
            style={styles.thumb}
            accessibilityIgnoresInvertColors
          />
        ) : (
          <View style={[styles.thumb, { backgroundColor: colors.border }]} />
        )}
        <View style={styles.rowText}>
          <Text style={[styles.name, { color: colors.text }]}>{exercise.name}</Text>
          <Text style={[styles.meta, { color: colors.textMuted }]}>{details}</Text>
        </View>
      </Pressable>
    </Link>
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
  title: {
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  description: {
    fontSize: 16,
    lineHeight: 22,
  },
  list: {
    gap: spacing.sm,
  },
  filterBar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  thumb: {
    width: 64,
    height: 64,
    borderRadius: radius.sm,
  },
  rowText: {
    flex: 1,
    gap: 2,
  },
  name: {
    fontSize: 16,
    fontWeight: '700',
  },
  meta: {
    fontSize: 13,
    lineHeight: 18,
  },
});
