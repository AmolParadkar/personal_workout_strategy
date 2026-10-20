import { useLocalSearchParams } from 'expo-router';
import { Text } from 'react-native';

import { PagePlaceholder } from '@/components/PagePlaceholder';

// One exercise in detail, e.g. /exercises/barbell-squat.
export default function Screen() {
  const { id } = useLocalSearchParams<{ id: string }>();

  return (
    <PagePlaceholder page="exerciseGuide">
      <Text>Exercise: {id}</Text>
    </PagePlaceholder>
  );
}
