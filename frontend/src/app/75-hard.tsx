import { Text } from 'react-native';

import { PagePlaceholder } from '@/components/PagePlaceholder';
import { useProfile } from '@/features/profile/ProfileContext';
import { useTheme } from '@/theme';

export default function Screen() {
  const { activeProfile } = useProfile();
  const { colors } = useTheme();

  return (
    <PagePlaceholder page="seventyFiveHard">
      {!activeProfile.doing75Hard && (
        <Text style={{ color: colors.textMuted }}>
          {activeProfile.name} isn’t doing 75 Hard, so this page has nothing to show.
        </Text>
      )}
    </PagePlaceholder>
  );
}
