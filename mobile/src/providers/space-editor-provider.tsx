import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useRouter } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { createSpace } from '../api/spaces';
import { useTroveToastContext } from './toast-provider';
import { useWorkspaceActions, useWorkspaceData } from './workspace-provider';

type SpaceEditorValue = {
  spaceName: string;
  spaceDescription: string;
  spaceSaving: boolean;
  spaceError: string | null;
  setSpaceDescription: (description: string) => void;
  setSpaceName: (name: string) => void;
  closeSpace: () => void;
  createSpaceAction: () => Promise<void>;
};

const SpaceEditorContext = createContext<SpaceEditorValue | null>(null);

export function SpaceEditorProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { showToast } = useTroveToastContext();
  const { addSpace, setDefaultCaptureSpaceId } = useWorkspaceActions();
  const { defaultCaptureSpaceId } = useWorkspaceData();
  const [spaceName, setSpaceName] = useState('');
  const [spaceDescription, setSpaceDescription] = useState('');
  const creation = useMutation({ mutationFn: ({ name, description }: { name: string; description: string }) => createSpace(name, description), retry: false });
  const spaceSaving = creation.isPending;
  const spaceError = creation.error?.message ?? null;
  const { reset, mutateAsync } = creation;

  const closeSpace = useCallback(() => {
    if (spaceSaving) return;
    setSpaceName('');
    setSpaceDescription('');
    reset();
    router.back();
  }, [router, spaceSaving, reset]);

  const createSpaceAction = useCallback(async () => {
    const name = spaceName.trim();
    if (!name || spaceSaving) return;
    let result;
    try {
      result = await mutateAsync({ name, description: spaceDescription });
    } catch {
      // Mutation state retains the failure for the editor; leave the draft intact.
      return;
    }
    addSpace(result.space);
    if (!defaultCaptureSpaceId) setDefaultCaptureSpaceId(result.space.id);
    setSpaceName('');
    setSpaceDescription('');
    router.back();
    showToast(`Space “${name}” created`);

  }, [mutateAsync, spaceName, spaceDescription, spaceSaving, addSpace, defaultCaptureSpaceId, setDefaultCaptureSpaceId, router, showToast]);

  const value = useMemo(() => ({ spaceName, spaceDescription, spaceSaving, spaceError, setSpaceName, setSpaceDescription, closeSpace, createSpaceAction }), [spaceName, spaceDescription, spaceSaving, spaceError, closeSpace, createSpaceAction]);
  return <SpaceEditorContext.Provider value={value}>{children}</SpaceEditorContext.Provider>;
}

export function useTroveSpaceEditor() {
  const value = useContext(SpaceEditorContext);
  if (!value) throw new Error('useTroveSpaceEditor must be used inside SpaceEditorProvider.');
  return value;
}
