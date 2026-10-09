import * as SecureStore from 'expo-secure-store';

export function readSessionValue(key: string) {
  return SecureStore.getItemAsync(key);
}

export function writeSessionValue(key: string, value: string | null) {
  return value === null ? SecureStore.deleteItemAsync(key) : SecureStore.setItemAsync(key, value);
}
