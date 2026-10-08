import { useLocalSearchParams, useRouter } from 'expo-router';
import { CaptureScreen } from '../features/capture/capture-screen';
import { useWorkspaceActions, useWorkspaceData } from '../providers/workspace-provider';

export default function CaptureRoute() {
  const router = useRouter();
  const { spaceId } = useLocalSearchParams<{ spaceId?: string }>();
  const { spaces, defaultCaptureSpaceId } = useWorkspaceData();
  const { saveCapture } = useWorkspaceActions();
  const destinationId = spaceId || defaultCaptureSpaceId || undefined;
  const destination = spaces.find((space) => space.id === destinationId);
  return <CaptureScreen spaceId={destination?.id} spaces={spaces} onClose={() => router.back()} onSave={saveCapture} />;
}
