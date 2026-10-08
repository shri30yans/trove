import { useStoredPreference } from '../../hooks/use-stored-preference';
import { searchHistoryPreference } from '../../storage/local-preferences';
export function useSearchHistory() {
  const stored = useStoredPreference(searchHistoryPreference, []);
  const rememberQuery = (value: string) => {
    const query = value.trim();
    if (!query) return;
    stored.updateValue((history) => [query, ...history.filter((entry) => entry.toLowerCase() !== query.toLowerCase())].slice(0, 8));
  };
  return { history: stored.value, historyError: stored.error, rememberQuery, clearHistory: () => stored.setValue([]) };
}
