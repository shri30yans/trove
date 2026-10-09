import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { Alert, useColorScheme } from 'react-native';
import { useStoredPreference } from '../hooks/use-stored-preference';
import { themePreference } from '../storage/local-preferences';
import { themes, type Palette, type ThemeId } from '../theme';

type ThemeValue = {
  colors: Palette;
  theme: ThemeId;
  darkMode: boolean;
  themeLoaded: boolean;
  changeTheme: (id: ThemeId) => void;
};

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { value: storedTheme, loaded: themeLoaded, error, setValue: changeTheme } = useStoredPreference(themePreference, null);
  const systemTheme: ThemeId = useColorScheme() === 'dark' ? 'dark' : 'light';
  const theme = storedTheme ?? systemTheme;
  useEffect(() => {
    if (error) Alert.alert('Appearance settings unavailable', error);
  }, [error]);

  const value = useMemo(
    () => ({ colors: themes[theme].colors, theme, darkMode: themes[theme].mode === 'dark', themeLoaded, changeTheme }),
    [theme, changeTheme, themeLoaded],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used inside ThemeProvider.');
  return value;
}

export function useThemedStyles<T>(buildStyles: (colors: Palette) => T): T {
  const { colors } = useTheme();
  return useMemo(() => buildStyles(colors), [buildStyles, colors]);
}
