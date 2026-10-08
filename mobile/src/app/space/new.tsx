import { SpaceSheet } from '../../features/spaces/space-sheet';
import { useTroveSpaceEditor } from '../../providers/space-editor-provider';

export default function NewSpaceRoute() {
  const { spaceName, spaceDescription, spaceSaving, spaceError, setSpaceName, setSpaceDescription, closeSpace, createSpaceAction } = useTroveSpaceEditor();
  return <SpaceSheet name={spaceName} description={spaceDescription} onDescription={setSpaceDescription} saving={spaceSaving} error={spaceError} onName={setSpaceName} onClose={closeSpace} onSave={() => void createSpaceAction()} />;
}
