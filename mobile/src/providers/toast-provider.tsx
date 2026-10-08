import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useTroveToast } from './use-trove-toast';

type ToastValue = ReturnType<typeof useTroveToast>;
const ToastContext = createContext<ToastValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { toast, showToast } = useTroveToast();
  const contextValue = useMemo(() => ({ toast, showToast }), [toast, showToast]);
  return <ToastContext.Provider value={contextValue}>{children}</ToastContext.Provider>;
}

export function useTroveToastContext() {
  const value = useContext(ToastContext);
  if (!value) throw new Error('useTroveToastContext must be used inside ToastProvider.');
  return value;
}
