import type { ViewStyle } from 'react-native';

/**
 * Semantic colour roles. `deep` is always the high-contrast fill (primary button, selected
 * pill, nav dock) and `surface` is always the colour of content sitting on `deep`, so the
 * two swap places between themes instead of being re-picked per component.
 *
 * `action`/`onAction` are the floating create control and the content on it. They are a
 * separate pair from `deep` because the create button sits beside the dock, which already
 * owns `deep`: the pair must keep its label at 4.5:1 and read as a distinct shape against the
 * dock. `deep` alone cannot guarantee that, since dark palettes lighten it into a near-white
 * chip. The control has no border — the fill carries its whole edge — so a palette must pick
 * an `action` that stays findable on its own page.
 */
const lightColors = {
  background: '#F6F5F9',
  surface: '#FFFFFF',
  foreground: '#22212B',
  deep: '#2A2933',
  secondary: '#4A4858',
  muted: '#5B596A',
  border: '#DCD9E4',
  borderSoft: '#EAE8F0',
  thistle: '#E7E0EF',
  petal: '#F2DAE4',
  lavender: '#D5C7E6',
  icyBlue: '#DDE9F5',
  skyBlue: '#B8D0F0',
  blueDeep: '#6B4FA0',
  action: '#6B4FA0',
  onAction: '#FFFFFF',
  green: '#3E7F5D',
  greenTint: '#DDEBE3',
  danger: '#B45055',
  dangerTint: '#F7ECEC',
  surfacePressed: '#EFECF4',
  scrim: 'rgba(48,45,59,0.38)',
  night: '#17161C',
};

/** Both palettes carry the same semantic roles; only the values swap. */
export type Palette = { [K in keyof typeof lightColors]: string };

const darkColors: Palette = {
  background: '#15141A',
  surface: '#201F27',
  foreground: '#EFECF5',
  deep: '#D9CBE8',
  secondary: '#C6C3D4',
  muted: '#B5B1C2',
  border: '#454250',
  borderSoft: '#302E39',
  thistle: '#40374D',
  petal: '#513846',
  lavender: '#54456B',
  icyBlue: '#34445F',
  skyBlue: '#456184',
  blueDeep: '#B69BE3',
  action: '#6C4BC4',
  onAction: '#EFECF5',
  green: '#79C99A',
  greenTint: '#2C4438',
  danger: '#E4929A',
  dangerTint: '#4A2C31',
  surfacePressed: '#2A2833',
  scrim: 'rgba(8,7,12,0.6)',
  night: '#0E0D12',
};

/** Warm paper tones; same semantic roles as the other light palettes. */
const sepiaColors: Palette = {
  background: '#F7F2E9',
  surface: '#FFFDF6',
  foreground: '#3A2F25',
  deep: '#4A3B2E',
  secondary: '#6B5744',
  muted: '#705C48',
  border: '#E0D2BC',
  borderSoft: '#ECE2D1',
  thistle: '#E9DFC9',
  petal: '#F0D2B8',
  lavender: '#DDC8A7',
  icyBlue: '#DFE8D2',
  skyBlue: '#CAD7B7',
  blueDeep: '#8A5A2B',
  action: '#8A5A2B',
  onAction: '#FFFDF6',
  green: '#5F7A4F',
  greenTint: '#E2E8D5',
  danger: '#A8543C',
  dangerTint: '#F3E3D7',
  surfacePressed: '#F0E5D3',
  scrim: 'rgba(58,47,37,0.38)',
  night: '#211911',
};

/** Cool night palette; deep swaps to a light fill like the other dark palettes. */
const midnightColors: Palette = {
  background: '#0F1420',
  surface: '#1A2233',
  foreground: '#E8EDF7',
  deep: '#AFC3EC',
  secondary: '#C4D0E4',
  muted: '#93A2BC',
  border: '#30405D',
  borderSoft: '#263149',
  thistle: '#3A3C5D',
  petal: '#563D63',
  lavender: '#4A5785',
  icyBlue: '#30476B',
  skyBlue: '#496B98',
  blueDeep: '#8FB0F5',
  action: '#2A63A6',
  onAction: '#E8EDF7',
  green: '#7DC0A8',
  greenTint: '#2A4152',
  danger: '#EFA1A8',
  dangerTint: '#4A2F3A',
  surfacePressed: '#222B41',
  scrim: 'rgba(5,8,15,0.6)',
  night: '#080C14',
};

/**
 * True-black OLED palette, tuned for low glare: nothing in it reaches the brightness the
 * light themes reserve for paper, so the dock and body text sit well below pure white.
 * Keeps a violet-neutral cast through every layer and a deliberate elevation ramp
 * (background < surface < pressed < chips). Its borderless create control is the exact fill
 * and ink of the selected nav pill (`lavender` under `foreground`), so it reads as the same
 * kind of object as the dock rather than as a lit accent.
 */
const ultraColors: Palette = {
  background: '#050507',
  surface: '#131219',
  foreground: '#E4DFF0',
  deep: '#A99CC4',
  secondary: '#BFB6CB',
  muted: '#A9A3B7',
  border: '#383446',
  borderSoft: '#242231',
  thistle: '#3A2F57',
  petal: '#48274A',
  lavender: '#4B3775',
  icyBlue: '#22345C',
  skyBlue: '#2E4F8A',
  blueDeep: '#B29BDE',
  action: '#4B3775',
  onAction: '#E4DFF0',
  green: '#82D3A4',
  greenTint: '#1B3A2A',
  danger: '#E9919D',
  dangerTint: '#452233',
  surfacePressed: '#211E2B',
  scrim: 'rgba(0,0,0,0.72)',
  night: '#000000',
};

/** Neutral light palette without the lilac cast. */
const slateColors: Palette = {
  background: '#F4F5F7',
  surface: '#FFFFFF',
  foreground: '#1F2328',
  deep: '#2A2E35',
  secondary: '#4C525C',
  muted: '#58616E',
  border: '#D9DDE4',
  borderSoft: '#E8EAEF',
  thistle: '#E6E8EE',
  petal: '#E9E0DA',
  lavender: '#DFE3EA',
  icyBlue: '#D6E4F1',
  skyBlue: '#BFD0E0',
  blueDeep: '#4A6FA5',
  action: '#3B5C8C',
  onAction: '#FFFFFF',
  green: '#3E7F5D',
  greenTint: '#DCE7E1',
  danger: '#B45055',
  dangerTint: '#F5EAEA',
  surfacePressed: '#ECEEF2',
  scrim: 'rgba(31,35,40,0.38)',
  night: '#14161A',
};

/** Deep-ocean dark palette built on the blue gradient family (navy → cyan). */
const abyssColors: Palette = {
  background: '#010226',
  surface: '#020338',
  foreground: '#E9F9FC',
  deep: '#90E0EF',
  secondary: '#B6D5FE',
  muted: '#89A8D9',
  border: '#16466F',
  borderSoft: '#0D2B55',
  thistle: '#12365E',
  petal: '#302A58',
  lavender: '#194777',
  icyBlue: '#0A3540',
  skyBlue: '#155A79',
  blueDeep: '#53D4FF',
  action: '#0E7490',
  onAction: '#E9F9FC',
  green: '#4DBB95',
  greenTint: '#073844',
  danger: '#FF6B9D',
  dangerTint: '#3E1637',
  surfacePressed: '#06104A',
  scrim: 'rgba(1,1,19,0.66)',
  night: '#010113',
};

/** Pale cyan light palette from the same blue gradient family. */
const lagoonColors: Palette = {
  background: '#E4F5FA',
  surface: '#F4FCFE',
  foreground: '#0A3540',
  deep: '#023E8A',
  secondary: '#2E4A66',
  muted: '#526E89',
  border: '#B4DCE7',
  borderSoft: '#D3EBF1',
  thistle: '#C6E8F1',
  petal: '#F0DDE8',
  lavender: '#B9DFEC',
  icyBlue: '#D2EFF6',
  skyBlue: '#A8D9E9',
  blueDeep: '#0077B6',
  action: '#0077B6',
  onAction: '#F4FCFE',
  green: '#1E7E6E',
  greenTint: '#D4ECE4',
  danger: '#C43D5E',
  dangerTint: '#F8E3EA',
  surfacePressed: '#C5E7F0',
  scrim: 'rgba(10,53,64,0.38)',
  night: '#082D34',
};

/** Dark highlighter palette: amber fill with neon pink and azure accents. */
const arcadeColors: Palette = {
  background: '#17102B',
  surface: '#1F1637',
  foreground: '#F4EFFE',
  deep: '#FFBE0B',
  secondary: '#CBC0EA',
  muted: '#AA9BCB',
  border: '#443568',
  borderSoft: '#30234F',
  thistle: '#392A67',
  petal: '#5C2454',
  lavender: '#4D2D7E',
  icyBlue: '#233366',
  skyBlue: '#345AA1',
  blueDeep: '#3A86FF',
  action: '#3A86FF',
  onAction: '#17102B',
  green: '#72D6A1',
  greenTint: '#173A44',
  danger: '#FF006E',
  dangerTint: '#4A1436',
  surfacePressed: '#2A1D49',
  scrim: 'rgba(12,7,24,0.66)',
  night: '#0E0919',
};

/** Dark forest palette on the evergreen → lime-cream family. */
const evergreenColors: Palette = {
  background: '#0F1F0F',
  surface: '#172917',
  foreground: '#F0F7E6',
  deep: '#ECF39E',
  secondary: '#C9DCAF',
  muted: '#9CB187',
  border: '#38552F',
  borderSoft: '#293F23',
  thistle: '#304A28',
  petal: '#51402A',
  lavender: '#405C30',
  icyBlue: '#203923',
  skyBlue: '#345C2C',
  blueDeep: '#90A955',
  action: '#90A955',
  onAction: '#0F1F0F',
  green: '#A6D975',
  greenTint: '#2C4723',
  danger: '#FF6B5E',
  dangerTint: '#44231D',
  surfacePressed: '#20351A',
  scrim: 'rgba(8,16,8,0.62)',
  night: '#0A140A',
};

/** Light cream palette with lime washes from the same green family. */
const meadowColors: Palette = {
  background: '#ECF39E',
  surface: '#FAFBE8',
  foreground: '#1A2F16',
  deep: '#132A13',
  secondary: '#3E5C33',
  muted: '#5A6C41',
  border: '#D1DEA0',
  borderSoft: '#E2EABF',
  thistle: '#DDEAB8',
  petal: '#EFDEC5',
  lavender: '#D3E3A9',
  icyBlue: '#E9F2D0',
  skyBlue: '#D2E6A0',
  blueDeep: '#31572C',
  action: '#3F6B2A',
  onAction: '#FAFBE8',
  green: '#3F6B2A',
  greenTint: '#DCE9B9',
  danger: '#C2492F',
  dangerTint: '#F6E3D5',
  surfacePressed: '#E8F0CB',
  scrim: 'rgba(26,47,22,0.38)',
  night: '#0D1B0D',
};

/** Dark violet palette on rich purple shades. */
const irisColors: Palette = {
  background: '#170F26',
  surface: '#1F1533',
  foreground: '#F2EDFB',
  deep: '#CBB7F0',
  secondary: '#CFC6E8',
  muted: '#8F83A9',
  border: '#40305F',
  borderSoft: '#2F234C',
  thistle: '#38265F',
  petal: '#542B59',
  lavender: '#4A3378',
  icyBlue: '#292650',
  skyBlue: '#3C3978',
  blueDeep: '#A78BFA',
  action: '#6C4BC4',
  onAction: '#F2EDFB',
  green: '#7CD4A8',
  greenTint: '#20402F',
  danger: '#FB7185',
  dangerTint: '#4A2030',
  surfacePressed: '#2A1E45',
  scrim: 'rgba(15,9,28,0.66)',
  night: '#0F0A1C',
};

/** Light blush palette on soft pink shades. */
const roseColors: Palette = {
  background: '#F9EDF1',
  surface: '#FDF7F9',
  foreground: '#3A2230',
  deep: '#3F2233',
  secondary: '#6B4A5A',
  muted: '#835B6B',
  border: '#E8CDD8',
  borderSoft: '#F1E0E7',
  thistle: '#F4DDE6',
  petal: '#F6CDDD',
  lavender: '#F0D3E0',
  icyBlue: '#F7E8ED',
  skyBlue: '#EFC9D7',
  blueDeep: '#C2437B',
  action: '#A83469',
  onAction: '#FDF7F9',
  green: '#4F7A5E',
  greenTint: '#E2EDE4',
  danger: '#BE3A50',
  dangerTint: '#F8E4E7',
  surfacePressed: '#F0DDE4',
  scrim: 'rgba(58,34,48,0.38)',
  night: '#24131C',
};

/** Dark wine palette on burgundy-pink shades. */
const merlotColors: Palette = {
  background: '#230D16',
  surface: '#2C111C',
  foreground: '#FBEFF3',
  deep: '#F2C4D5',
  secondary: '#D9B8C4',
  muted: '#AD8997',
  border: '#542A3C',
  borderSoft: '#3D1F2D',
  thistle: '#492438',
  petal: '#612847',
  lavender: '#55283D',
  icyBlue: '#3A202D',
  skyBlue: '#60314A',
  blueDeep: '#EB8FB0',
  action: '#B03A63',
  onAction: '#FBEFF3',
  green: '#8FCB9E',
  greenTint: '#2B4533',
  danger: '#F87171',
  dangerTint: '#4A2023',
  surfacePressed: '#3A1724',
  scrim: 'rgba(25,8,14,0.66)',
  night: '#180810',
};

/** Light butter palette on warm yellow shades. */
const honeyColors: Palette = {
  background: '#FDF6DC',
  surface: '#FFFDF2',
  foreground: '#3A3018',
  deep: '#453510',
  secondary: '#6B5A2E',
  muted: '#796830',
  border: '#E6D89E',
  borderSoft: '#F1E8C4',
  thistle: '#F5EBC2',
  petal: '#F6DEB5',
  lavender: '#EFDF9E',
  icyBlue: '#FBF1D3',
  skyBlue: '#EDD98B',
  blueDeep: '#8A6A08',
  action: '#8A6A08',
  onAction: '#FFFDF2',
  green: '#57792F',
  greenTint: '#E9EECD',
  danger: '#B84A28',
  dangerTint: '#F7E6D8',
  surfacePressed: '#F2E6BD',
  scrim: 'rgba(61,51,25,0.38)',
  night: '#241E0F',
};

export { lightColors, darkColors, sepiaColors, midnightColors, ultraColors, slateColors, abyssColors, lagoonColors, arcadeColors, evergreenColors, meadowColors, irisColors, roseColors, merlotColors, honeyColors };

export type ThemeId = 'light' | 'slate' | 'sepia' | 'dark' | 'midnight' | 'ultra' | 'abyss' | 'lagoon' | 'arcade' | 'evergreen' | 'meadow' | 'iris' | 'rose' | 'merlot' | 'honey';

/** The named themes offered in Profile. `mode` only drives system chrome like the status bar. */
export const themes: Record<ThemeId, { label: string; mode: 'light' | 'dark'; colors: Palette }> = {
  light: { label: 'Light', mode: 'light', colors: lightColors },
  slate: { label: 'Slate', mode: 'light', colors: slateColors },
  sepia: { label: 'Sepia', mode: 'light', colors: sepiaColors },
  dark: { label: 'Dark', mode: 'dark', colors: darkColors },
  midnight: { label: 'Midnight', mode: 'dark', colors: midnightColors },
  ultra: { label: 'Ultra dark', mode: 'dark', colors: ultraColors },
  abyss: { label: 'Abyss', mode: 'dark', colors: abyssColors },
  lagoon: { label: 'Lagoon', mode: 'light', colors: lagoonColors },
  arcade: { label: 'Arcade', mode: 'dark', colors: arcadeColors },
  evergreen: { label: 'Evergreen', mode: 'dark', colors: evergreenColors },
  meadow: { label: 'Meadow', mode: 'light', colors: meadowColors },
  iris: { label: 'Iris', mode: 'dark', colors: irisColors },
  rose: { label: 'Rose', mode: 'light', colors: roseColors },
  merlot: { label: 'Merlot', mode: 'dark', colors: merlotColors },
  honey: { label: 'Honey', mode: 'light', colors: honeyColors },
};

export const themeOrder: ThemeId[] = ['light', 'dark', 'ultra', 'slate', 'sepia', 'midnight', 'abyss', 'lagoon', 'arcade', 'evergreen', 'meadow', 'iris', 'rose', 'merlot', 'honey'];

export const fonts = { display: 'Georgia', mono: 'monospace' } as const;

export const radii = { xs: 10, sm: 12, md: 14, lg: 18, xl: 22, sheet: 26, pill: 999 } as const;

export const spacing = { xxs: 2, xs: 4, sm: 6, md: 8, lg: 12, xl: 14, xxl: 16, xxxl: 20, xxxxl: 24 } as const;

/** Screen gutter, card padding, and inter-element gap for every surface in the app. */
export const layout = { gutter: 20, pad: 14, gap: 10, sectionGap: 22, railGap: 8, navBar: 85, screenTop: 16, headerGap: 14 } as const;

/** Shared insets for screen content that contains its heading. */
export const screenInsets = { paddingHorizontal: layout.gutter, paddingTop: layout.screenTop } as const;

/** One control height scale. Controls that sit in the same row must use the same step. */
export const control = { compact: 38, default: 44, large: 52 } as const;

/** Generous switch touch area with an instant, theme-colored track and thumb. */
export const switchControl = { width: 64, height: 52, trackWidth: 60, trackHeight: 36, thumbSize: 28 } as const;

export const iconSize = { xs: 13, sm: 15, md: 18, lg: 20, xl: 24 } as const;

/** The tinted non-interactive well that marks a row, card, or empty state. */
export const iconBadge = { row: 38, mark: 42, preview: 56 } as const;

/** One type scale, keyed by role rather than by screen. */
export const text = {
  page: { fontFamily: fonts.display, fontSize: 28, fontWeight: '500', lineHeight: 34, letterSpacing: -0.6 },
  hero: { fontSize: 31, fontWeight: '300', lineHeight: 38, letterSpacing: -0.7 },
  display: { fontFamily: fonts.display, fontSize: 22, fontWeight: '500', lineHeight: 27, letterSpacing: -0.4 },
  section: { fontSize: 17, fontWeight: '600', lineHeight: 22, letterSpacing: -0.2 },
  eyebrow: { fontFamily: fonts.mono, fontSize: 10, lineHeight: 13, letterSpacing: 1 },
  buttonLarge: { fontSize: 15, fontWeight: '600' },
  button: { fontSize: 14, fontWeight: '600' },
  buttonSmall: { fontSize: 13, fontWeight: '600' },
  subtitle: { fontSize: 12, lineHeight: 17 },
  body: { fontSize: 13, lineHeight: 20 },
  reading: { fontSize: 15, lineHeight: 23 },
  caption: { fontSize: 11, lineHeight: 15 },
  itemTitle: { fontSize: 13, fontWeight: '600', lineHeight: 18 },
  input: { fontSize: 15, lineHeight: 21 },
  compose: { fontSize: 16, lineHeight: 24 },
  meta: { fontFamily: fonts.mono, fontSize: 10, lineHeight: 13 },
} as const;

/** The only pressed/disabled treatments in the app. */
const pressed: ViewStyle = { opacity: 0.8, transform: [{ scale: 0.99 }] };
const disabled: ViewStyle = { opacity: 0.5 };
const rowPressed: ViewStyle = { opacity: 0.72 };
export const press = { pressed, rowPressed, disabled } as const;

/**
 * Elevation for the floating dock and create button. The shadow colour is a fixed dark, not
 * a theme role: on dark palettes `deep` is a near-white chip, so using it as the shadow
 * colour renders a halo instead of a shadow.
 */
export const shadow = {
  float: { shadowColor: '#1B1A22', shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.16, shadowRadius: 12, elevation: 10 },
} as const;

/** Translucent fills used on top of tinted artwork. */
export const glass = {
  veil: 'rgba(255,255,255,0.24)',
  faint: 'rgba(255,255,255,0.4)',
  soft: 'rgba(255,255,255,0.62)',
  strong: 'rgba(255,255,255,0.86)',
  /** Small labels and badges sitting on a tinted card, where the veil has to read as solid. */
  chip: 'rgba(255,255,255,0.75)',
} as const;

/** The colours a collection cycles through when an entry supplies none of its own. */
export function collectionTints(colors: Palette): string[] {
  return [colors.petal, colors.icyBlue, colors.lavender, colors.greenTint];
}
