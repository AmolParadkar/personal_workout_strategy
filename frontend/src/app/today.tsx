import { PagePlaceholder } from '@/components/PagePlaceholder';
import { WaterCard } from '@/features/today/WaterCard';

// Workouts and meals arrive in M6–M7; the water card is live from M3.
export default function Screen() {
  return (
    <PagePlaceholder page="today">
      <WaterCard />
    </PagePlaceholder>
  );
}
