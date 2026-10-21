import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button, ChipSelect, TextField } from '@/components/form';
import { ApiError, apiPost, type Schemas } from '@/lib/api';
import { spacing, useTheme } from '@/theme';

type Exercise = Schemas['ExerciseDetail'];

const REASONS = [
  { value: 'It shows a different exercise or variation', label: 'Wrong exercise' },
  { value: 'The form or technique looks poor', label: 'Poor form' },
  { value: 'It is not in English', label: 'Not in English' },
  { value: 'It is hard to follow or too fast', label: 'Hard to follow' },
];

// "Is this the right video?" under the video. Yes keeps it; No asks why and
// searches again, using the reason (spec: context/pages/exercise-guide.md).
export function VideoFeedback({
  exercise,
  onUpdated,
}: {
  exercise: Exercise;
  onUpdated: (exercise: Exercise) => void;
}) {
  const { colors } = useTheme();
  const video = exercise.video;
  const [asking, setAsking] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!video) return null;

  const reason = [...picked, details.trim()].filter(Boolean).join('. ');

  const send = async (verdict: 'right' | 'wrong') => {
    setBusy(true);
    setError(null);
    try {
      const updated = await apiPost<Exercise>(`/api/exercises/${exercise.id}/video-feedback`, {
        video_id: video.id,
        verdict,
        reason: verdict === 'wrong' ? reason : null,
      });
      setAsking(false);
      setPicked([]);
      setDetails('');
      onUpdated(updated);
    } catch (e) {
      setError(
        e instanceof ApiError && typeof e.detail === 'string'
          ? e.detail
          : 'Couldn’t send that. Please try again.',
      );
    } finally {
      setBusy(false);
    }
  };

  const muted = { color: colors.textMuted };

  if (asking) {
    return (
      <View style={styles.box}>
        <Text style={[styles.body, { color: colors.text }]}>What’s wrong with it?</Text>
        <ChipSelect options={REASONS} selected={picked} onChange={setPicked} multiple />
        <TextField
          label="Anything more specific"
          value={details}
          onChange={setDetails}
          placeholder="e.g. This is a front squat; I need the back squat"
        />
        <Text style={[styles.caption, muted]}>
          Your reason guides the next search, and this video won’t be shown again.
        </Text>
        <View style={styles.row}>
          <Button label="Cancel" variant="secondary" onPress={() => setAsking(false)} />
          <Button
            label={busy ? 'Sending…' : 'Find another video'}
            onPress={() => send('wrong')}
            disabled={busy || reason.length < 3}
          />
        </View>
        {error && <Text style={[styles.caption, { color: colors.alert }]}>{error}</Text>}
      </View>
    );
  }

  if (video.confirmed) {
    return (
      <View style={styles.row}>
        <Text style={[styles.caption, { color: colors.good }]}>
          ✓ Confirmed as the right video.
        </Text>
        <Button label="Not right after all?" variant="secondary" onPress={() => setAsking(true)} />
      </View>
    );
  }

  return (
    <View style={styles.box}>
      <Text style={[styles.body, { color: colors.text }]}>Is this the right video?</Text>
      <View style={styles.row}>
        <Button label="Yes" variant="secondary" onPress={() => send('right')} disabled={busy} />
        <Button label="No" variant="secondary" onPress={() => setAsking(true)} disabled={busy} />
      </View>
      {error && <Text style={[styles.caption, { color: colors.alert }]}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    gap: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.sm,
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
  caption: {
    fontSize: 13,
    lineHeight: 18,
  },
});
