import { PagePlaceholder } from '@/components/PagePlaceholder';
import { WaterCard } from '@/features/today/WaterCard';
import { WorkoutCard } from '@/features/today/WorkoutCard';

// Meals arrive in M7; the workout (M6) and water (M3) are live.
export default function Screen() {
  return (
    <PagePlaceholder page="today">
      <WorkoutCard />
      <WaterCard />
    </PagePlaceholder>
  );
}
