import { useCallback, useEffect, useRef, useState } from 'react';

/** Long enough to read a one-line confirmation, short enough that it never outlives the screen. */
const TOAST_VISIBLE_MS = 2600;

export function useTroveToast() {
  const [toast, setToast] = useState('');
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), TOAST_VISIBLE_MS);
  }, []);

  useEffect(() => () => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
  }, []);

  return { toast, showToast };
}
