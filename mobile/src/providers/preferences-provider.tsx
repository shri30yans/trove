import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { Alert } from 'react-native';
import { useStoredPreference } from '../hooks/use-stored-preference';
import { automaticSyncPreference } from '../storage/local-preferences';
import * as Sharing from 'expo-sharing';
import { downloadMarkdownArchive } from '../api/export';
import { getPreferences } from '../api/preferences';
import { useQuery } from '@tanstack/react-query';
import type { Preferences } from '../types';


type PreferencesValue = {
  preferences: Preferences | null;
  preferencesError: string | null;
  preferencesLoading: boolean;
  backgroundSync: boolean;
  localSettingsLoaded: boolean;
  changeBackgroundSync: (value: boolean) => void;
  exportMemories: (spaceId?: string) => Promise<void>;
  reloadPreferences: () => Promise<void>;
};

const PreferencesContext = createContext<PreferencesValue | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const preferencesQuery = useQuery({ queryKey: ['preferences'], queryFn: getPreferences });
  const preferences = preferencesQuery.data?.preferences ?? null;
  const preferencesError = preferencesQuery.error?.message ?? null;
  const preferencesLoading = preferencesQuery.isPending;
  const { value: backgroundSync, loaded: localSettingsLoaded, error: localError, setValue: changeBackgroundSync } = useStoredPreference(automaticSyncPreference, false);

  const { refetch } = preferencesQuery;
  const reloadPreferences = useCallback(async () => {
    await refetch();
  }, [refetch]);

  useEffect(() => {
    if (localError) Alert.alert('Sync settings unavailable', localError);
  }, [localError]);

  const exportMemories = useCallback(async (spaceId?: string) => {
    try {
      const path = await downloadMarkdownArchive(spaceId);
      if (!(await Sharing.isAvailableAsync())) throw new Error('File sharing is not available on this device.');
      await Sharing.shareAsync(path, {
        mimeType: 'application/zip',
        dialogTitle: spaceId ? 'Export this Space as Markdown' : 'Export your Trove as Markdown',
      });
    } catch (error) {
      Alert.alert('Markdown export could not be prepared', error instanceof Error ? error.message : 'Try again in a moment.');
    }
  }, []);

  const value = useMemo(() => ({
    preferences, preferencesError, preferencesLoading, backgroundSync, localSettingsLoaded,
    changeBackgroundSync, exportMemories, reloadPreferences,
  }), [preferences, preferencesError, preferencesLoading, backgroundSync, localSettingsLoaded, changeBackgroundSync, exportMemories, reloadPreferences]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function useTrovePreferences() {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error('useTrovePreferences must be used inside PreferencesProvider.');
  return value;
}
