import { useCallback, useRef } from 'react';
import type { TextInput } from 'react-native';
import { useFocusEffect } from 'expo-router';

/**
 * The single owner of "this screen's composer owns the keyboard on entry".
 *
 * A TextInput keeps native focus after the keyboard was dismissed on navigation away,
 * so an `isFocused()` guard silently skips refocusing and the keyboard never returns.
 * Blur then focus on the next frame forces the keyboard back on every entry.
 */
export function useKeyboardOnScreenFocus() {
  const inputRef = useRef<TextInput | null>(null);
  useFocusEffect(useCallback(() => {
    let frame = 0;
    const settle = setTimeout(() => {
      const input = inputRef.current;
      if (!input) return;
      input.blur();
      frame = requestAnimationFrame(() => inputRef.current?.focus());
    }, 60);
    return () => { clearTimeout(settle); cancelAnimationFrame(frame); };
  }, []));
  return inputRef;
}
