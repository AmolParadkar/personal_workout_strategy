import { Text } from 'react-native';

import { PagePlaceholder } from '@/components/PagePlaceholder';
import { useProfile } from '@/features/profile/ProfileContext';

export default function Screen() {
  const { activeProfile } = useProfile();

  return (
    <PagePlaceholder page="seventyFiveHard">
      {!activeProfile.doing75Hard && (
        <Text>{activeProfile.name} isn’t doing 75 Hard, so this page has nothing to show.</Text>
      )}
    </PagePlaceholder>
  );
}
