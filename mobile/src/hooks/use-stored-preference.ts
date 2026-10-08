import { useCallback, useEffect, useRef, useState } from 'react';
import type { PreferenceStore } from '../storage/local-preferences';

type PreferenceState<T> = { state: 'loading'; value: T } | { state: 'ready'; value: T; error: string | null } | { state: 'unavailable'; value: T; error: string };
/** Shared lifecycle for the app's local choices. Values change only after a write commits. */
export function useStoredPreference<T>(store: PreferenceStore<T>, initial: T) {
  const [state, setState] = useState<PreferenceState<T>>({ state: 'loading', value: initial });
  const generation = useRef(0);
  useEffect(() => {
    let active = true;
    const version = generation.current;
    void store.read().then((value) => {
      if (active && version === generation.current) setState({ state: 'ready', value, error: null });
    }).catch((error: unknown) => {
      if (active && version === generation.current) setState((current) => ({ state: 'unavailable', value: current.value, error: error instanceof Error ? error.message : 'Could not read this setting.' }));
    });
    return () => { active = false; };
  }, [store]);
  const commit = useCallback((write: () => T) => {
    try { const value = write(); generation.current++; setState({ state: 'ready', value, error: null }); }
    catch (error) { setState((current) => ({ state: current.state === 'ready' ? 'ready' : 'unavailable', value: current.value, error: error instanceof Error ? error.message : 'Could not store this setting.' })); }
  }, []);
  const setValue = useCallback((value: T) => commit(() => { store.write(value); return value; }), [commit, store]);
  const updateValue = useCallback((change: (value: T) => T) => commit(() => store.update(change)), [commit, store]);
  return { value: state.value, loaded: state.state === 'ready', error: state.state === 'loading' ? null : state.error, setValue, updateValue };
}
