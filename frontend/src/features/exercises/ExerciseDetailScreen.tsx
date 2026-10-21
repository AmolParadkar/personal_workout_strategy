import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { useWorkerStatus } from '@/features/jobs/jobs';
import { useProfile } from '@/features/profile/ProfileContext';
import { useProfileSettings } from '@/features/settings/useProfileSettings';
import { ApiError, apiGet, apiPost, type Schemas } from '@/lib/api';
import { radius, spacing, useTheme } from '@/theme';

import { BodyMap } from './BodyMap';
import { muscleLabel } from './muscles';
import { VideoFeedback } from './VideoFeedback';

type Exercise = Schemas['ExerciseDetail'];

const POLL_MS = 2000;

const isPreparing = (e: Exercise) =>
  e.guide_status === 'preparing' || e.video_status === 'preparing';
const needsPreparing = (e: Exercise) =>
  e.guide_status === 'missing' || e.video_status === 'missing';

// One exercise in detail (spec: context/pages/exercise-guide.md). The guide
// text and video are prepared by the Mac worker the first time it's opened.
export function ExerciseDetailScreen({ id }: { id: string }) {
  const { colors } = useTheme();
  const { activeProfile } = useProfile();
  const { state: settings } = useProfileSettings(activeProfile.id);
  const worker = useWorkerStatus();
  const [loaded, setLoaded] = useState<{ id: string; exercise: Exercise } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const exercise = loaded?.id === id ? loaded.exercise : null;

  // Load it; if the guide or video is missing, ask the worker to prepare them.
  useEffect(() => {
    let cancelled = false;
    apiGet<Exercise>(`/api/exercises/${id}`)
      .then((found) =>
        needsPreparing(found) ? apiPost<Exercise>(`/api/exercises/${id}/prepare`) : found,
      )
      .then((found) => {
        if (!cancelled) setLoaded({ id, exercise: found });
      })
      .catch((e) => {
        if (!cancelled)
          setError(
            e instanceof ApiError && e.status === 404
              ? 'This exercise isn’t in the library.'
              : 'Couldn’t load the exercise.',
          );
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // While the worker prepares it, check back every few seconds.
  useEffect(() => {
    if (!exercise || !isPreparing(exercise)) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      apiGet<Exercise>(`/api/exercises/${id}`)
        .then((next) => {
          if (!cancelled) setLoaded({ id, exercise: next });
        })
        .catch(() => {
          if (!cancelled) setLoaded({ id, exercise: { ...exercise } });
        });
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id, exercise]);

  const sex = settings.status === 'ready' ? settings.settings.profile.sex : null;
  const muted = { color: colors.textMuted };
  const text = { color: colors.text };
  const card = [styles.card, { borderColor: colors.border, backgroundColor: colors.surface }];
  const workerOffline = worker !== null && !worker.online;

  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      <View style={styles.content}>
        <Link href="/exercises" style={[styles.back, { color: colors.primary }]}>
          ← All exercises
        </Link>
        {error && (
          <Text accessibilityRole="alert" style={{ color: colors.alert }}>
            {error}
          </Text>
        )}
        {!exercise && !error && <ActivityIndicator color={colors.primary} />}

        {exercise && (
          <>
            <Text style={[styles.title, text]}>{exercise.name}</Text>
            <Text style={[styles.body, muted]}>
              {[exercise.category, exercise.equipment, exercise.level, exercise.mechanic]
                .filter(Boolean)
                .map((s) => muscleLabel(String(s)))
                .join(' · ')}
            </Text>

            {/* 1. Diagram: start and end positions */}
            {exercise.images.length > 0 && (
              <View style={styles.images}>
                {exercise.images.slice(0, 2).map((uri, index) => (
                  <View key={uri} style={styles.imageBox}>
                    <Image
                      source={{ uri }}
                      style={[styles.image, { backgroundColor: colors.border }]}
                      resizeMode="contain"
                      accessibilityLabel={`${exercise.name}, ${index === 0 ? 'start' : 'end'} position`}
                    />
                    <Text style={[styles.caption, muted]}>{index === 0 ? 'Start' : 'End'}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* 2. Muscles */}
            <View style={card}>
              <Text style={[styles.heading, text]}>Muscles worked</Text>
              <BodyMap
                primary={exercise.primary_muscles}
                secondary={exercise.secondary_muscles}
                gender={sex === 'female' ? 'female' : 'male'}
              />
              <Text style={[styles.body, text]}>
                <Text style={styles.strong}>Primary: </Text>
                {exercise.primary_muscles.map(muscleLabel).join(', ') || '—'}
              </Text>
              {exercise.secondary_muscles.length > 0 && (
                <Text style={[styles.body, text]}>
                  <Text style={styles.strong}>Secondary: </Text>
                  {exercise.secondary_muscles.map(muscleLabel).join(', ')}
                </Text>
              )}
            </View>

            {/* 3–5. About, form cues, precautions */}
            <View style={card}>
              <Text style={[styles.heading, text]}>About</Text>
              {exercise.guide_status === 'ready' ? (
                <>
                  <Text style={[styles.body, text]}>{exercise.about}</Text>
                  <Text style={[styles.subheading, text]}>Good form looks like</Text>
                  <Bullets items={exercise.form_cues ?? []} />
                  <Text style={[styles.subheading, text]}>Precautions</Text>
                  <Bullets items={exercise.precautions ?? []} />
                  <Text style={[styles.caption, muted]}>
                    Written by AI and saved for everyone. Personal precautions from your health
                    records will appear here once Personal Artifacts is built.
                  </Text>
                </>
              ) : exercise.guide_status === 'failed' ? (
                <Failed what="the form cues" reason={exercise.guide_error} />
              ) : (
                <Preparing what="form cues and precautions" workerOffline={workerOffline} />
              )}
              <Text style={[styles.subheading, text]}>How to do it</Text>
              {exercise.instructions.map((step, index) => (
                <Text key={index} style={[styles.body, text]}>
                  {index + 1}. {step}
                </Text>
              ))}
            </View>

            {/* 6. Video */}
            <View style={card}>
              <Text style={[styles.heading, text]}>Video</Text>
              {exercise.video_status === 'preparing' || exercise.video_status === 'missing' ? (
                <Preparing
                  what={
                    exercise.videos_rejected > 0
                      ? 'a better video, using your feedback'
                      : 'a short video'
                  }
                  workerOffline={workerOffline}
                />
              ) : exercise.video ? (
                <>
                  <VideoCard video={exercise.video} />
                  <VideoFeedback
                    exercise={exercise}
                    onUpdated={(updated) => setLoaded({ id, exercise: updated })}
                  />
                </>
              ) : exercise.video_status === 'none_found' ? (
                <Text style={[styles.body, muted]}>
                  {exercise.videos_rejected > 0
                    ? 'No other short video matched your feedback. We’ll look again next month.'
                    : 'No short video (under 3 minutes) found for this one. We’ll look again next month.'}
                </Text>
              ) : (
                <Failed what="a video" reason={exercise.video_error} />
              )}
            </View>
          </>
        )}
      </View>
    </ScrollView>
  );
}

function Bullets({ items }: { items: string[] }) {
  const { colors } = useTheme();
  return (
    <View style={styles.bullets}>
      {items.map((item) => (
        <Text key={item} style={[styles.body, { color: colors.text }]}>
          • {item}
        </Text>
      ))}
    </View>
  );
}

function Preparing({ what, workerOffline }: { what: string; workerOffline: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={styles.preparing}>
      {!workerOffline && <ActivityIndicator color={colors.primary} />}
      <Text style={[styles.body, { color: workerOffline ? colors.caution : colors.textMuted }]}>
        {workerOffline
          ? `The Mac worker is offline, so ${what} will be added when it’s back.`
          : `Finding ${what}… this takes a few seconds.`}
      </Text>
    </View>
  );
}

function Failed({ what, reason }: { what: string; reason: string | null | undefined }) {
  const { colors } = useTheme();
  return (
    <Text style={[styles.body, { color: colors.caution }]}>
      Couldn’t prepare {what}
      {reason ? ` (${reason})` : ''}. It will be tried again tomorrow.
    </Text>
  );
}

function VideoCard({ video }: { video: NonNullable<Exercise['video']> }) {
  const { colors } = useTheme();
  const minutes = video.duration_seconds
    ? `${Math.floor(video.duration_seconds / 60)}:${String(video.duration_seconds % 60).padStart(2, '0')}`
    : null;
  const views = video.views
    ? `${Intl.NumberFormat(undefined, { notation: 'compact' }).format(video.views)} views`
    : null;
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={`Watch on YouTube: ${video.title ?? 'video'}`}
      onPress={() => Linking.openURL(video.url)}
      style={styles.video}
    >
      <Image source={{ uri: video.thumbnail }} style={styles.thumbnail} resizeMode="cover" />
      <View style={styles.videoText}>
        <Text style={[styles.body, styles.strong, { color: colors.text }]}>{video.title}</Text>
        <Text style={[styles.caption, { color: colors.textMuted }]}>
          {[video.channel, minutes, views].filter(Boolean).join(' · ')}
        </Text>
        <Text style={[styles.body, styles.strong, { color: colors.primary }]}>
          Watch on YouTube →
        </Text>
      </View>
    </Pressable>
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
  back: {
    fontSize: 15,
    fontWeight: '600',
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  images: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  imageBox: {
    flex: 1,
    gap: spacing.xs,
    alignItems: 'center',
  },
  image: {
    width: '100%',
    aspectRatio: 4 / 3,
    borderRadius: radius.md,
  },
  card: {
    padding: spacing.lg,
    gap: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  heading: {
    fontSize: 18,
    fontWeight: '700',
  },
  subheading: {
    fontSize: 15,
    fontWeight: '700',
    marginTop: spacing.xs,
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  strong: {
    fontWeight: '700',
  },
  caption: {
    fontSize: 13,
    lineHeight: 18,
  },
  bullets: {
    gap: spacing.xs,
  },
  preparing: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  video: {
    gap: spacing.sm,
  },
  thumbnail: {
    width: '100%',
    aspectRatio: 16 / 9,
    borderRadius: radius.md,
  },
  videoText: {
    gap: spacing.xs,
  },
});
