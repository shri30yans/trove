import { useCallback } from 'react';
import { useRouter } from 'expo-router';

/** Internal screens can be the first route in the stack (deep link, cold restore), where back has nowhere to go. */
export function useGoBack() {
  const router = useRouter();
  return useCallback(() => {
    if (router.canGoBack()) router.back();
    else router.replace('/');
  }, [router]);
}
