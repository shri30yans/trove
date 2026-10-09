/** Browser sessions live only for the current tab; native sessions use Keychain/Keystore. */
export async function readSessionValue(key: string) {
  return typeof window === 'undefined' ? null : window.sessionStorage.getItem(key);
}

export async function writeSessionValue(key: string, value: string | null) {
  if (typeof window === 'undefined') return;
  if (value === null) window.sessionStorage.removeItem(key);
  else window.sessionStorage.setItem(key, value);
}
