import { useLocalSearchParams } from 'expo-router';

import { ExerciseDetailScreen } from '@/features/exercises/ExerciseDetailScreen';

// One exercise in detail, e.g. /exercises/Barbell_Squat.
export default function Screen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <ExerciseDetailScreen id={id} />;
}
