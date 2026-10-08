import { z } from 'zod';
import LegacyStorage from '@react-native-async-storage/async-storage';
import Storage from 'expo-sqlite/kv-store';
import { themes, type ThemeId } from '../theme';
import { logSync } from '../utils/sync-log';

export type PreferenceStore<T> = { read: () => Promise<T>; write: (value: T) => void; update: (change: (value: T) => T) => T };
function decode<T>(schema: z.ZodType<T>, value: unknown): T {
  const parsed = schema.safeParse(value);
  if (!parsed.success) throw new Error('A setting on this device is invalid. Its stored data has been kept.');
  return parsed.data;
}
function preference<T>(key: string, schema: z.ZodType<T>, readLegacy: () => Promise<T>): PreferenceStore<T> {
  const readCurrent = () => {
    const raw = Storage.getItemSync(key);
    return raw === null ? null : { value: decode(schema, JSON.parse(raw)) };
  };
  const write = (value: T) => Storage.setItemSync(key, JSON.stringify(decode(schema, value)));
  const update = (change: (value: T) => T): T => {
    const current = readCurrent();
    if (!current) throw new Error('This setting is still loading. Try again in a moment.');
    const next = decode(schema, change(current.value));
    write(next);
    return next;
  };
  return { write, update, read: async () => {
    const current = readCurrent();
    if (current) return current.value;
    const imported = await readLegacy();
    // A preference changed while legacy storage was loading wins over the old read.
    const updated = readCurrent();
    if (updated) return updated.value;
    write(imported);
    // Persisted null is a value: old selections cannot resurrect after being cleared.
    await LegacyStorage.removeItem(key).catch(() => logSync('settings.legacy-cleanup-failed'));
    return imported;
  } };
}
const defaultSpaceKey = 'trove.default-capture-space.v1';
const syncKey = 'trove.setting.background-sync.v1';
const historyKey = 'trove.search.history.v1';
const themeKey = 'trove.theme.v1';
const themeSchema = z.custom<ThemeId>((value) => typeof value === 'string' && Object.hasOwn(themes, value));
const spaceSchema = z.uuid().nullable();
const historySchema = z.array(z.string().trim().min(1).max(1000)).max(8);
export const defaultSpacePreference = preference(defaultSpaceKey, spaceSchema, async () => decode(spaceSchema, await LegacyStorage.getItem(defaultSpaceKey)));
export const automaticSyncPreference = preference(syncKey, z.boolean(), async () => {
  const raw = await LegacyStorage.getItem(syncKey);
  return raw === null ? true : decode(z.enum(['true', 'false']).transform((value) => value === 'true'), raw);
});
export const searchHistoryPreference = preference(historyKey, historySchema, async () => {
  const raw = await LegacyStorage.getItem(historyKey);
  return raw === null ? [] : decode(historySchema, JSON.parse(raw));
});
export const themePreference = preference(themeKey, themeSchema, async () => {
  const raw = await LegacyStorage.getItem(themeKey);
  if (raw !== null) return decode(themeSchema, raw);
  const legacy = await LegacyStorage.getItem('trove.setting.dark-mode.v1');
  if (legacy === null) return 'light';
  return decode(z.enum(['true', 'false']).transform((value): ThemeId => value === 'true' ? 'dark' : 'light'), legacy);
});

export async function clearAccountLocalPreferences() {
  defaultSpacePreference.write(null);
  automaticSyncPreference.write(true);
  searchHistoryPreference.write([]);
  themePreference.write('light');
  await Promise.all([
    LegacyStorage.removeItem(defaultSpaceKey),
    LegacyStorage.removeItem(syncKey),
    LegacyStorage.removeItem(historyKey),
    LegacyStorage.removeItem(themeKey),
    LegacyStorage.removeItem('trove.setting.dark-mode.v1'),
  ]);
}
