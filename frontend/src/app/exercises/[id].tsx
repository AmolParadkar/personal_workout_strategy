import { useLocalSearchParams } from 'expo-router';
import { Text } from 'react-native';

import { PagePlaceholder } from '@/components/PagePlaceholder';
import { useTheme } from '@/theme';

// One exercise in detail, e.g. /exercises/barbell-squat.
export default function Screen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();

  return (
    <PagePlaceholder page="exerciseGuide">
      <Text style={{ color: colors.textMuted }}>Exercise: {id}</Text>
    </PagePlaceholder>
  );
}
