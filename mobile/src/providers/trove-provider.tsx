import { QueryProvider } from './query-provider';
import type { ReactNode } from 'react';
import { MemoryDetailsProvider } from './memory-details-provider';
import { PreferencesProvider } from './preferences-provider';
import { SearchProvider } from './search-provider';
import { SpaceEditorProvider } from './space-editor-provider';
import { ToastProvider } from './toast-provider';
import { WorkspaceProvider } from './workspace-provider';

export function TroveProvider({ children }: { children: ReactNode }) {
  return <QueryProvider>
    <ToastProvider>
      <PreferencesProvider>
        <WorkspaceProvider>
          <SearchProvider>
            <SpaceEditorProvider>
              <MemoryDetailsProvider>{children}</MemoryDetailsProvider>
            </SpaceEditorProvider>
          </SearchProvider>
        </WorkspaceProvider>
      </PreferencesProvider>
    </ToastProvider>
  </QueryProvider>;
}
