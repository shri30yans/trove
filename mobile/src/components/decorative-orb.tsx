import type { ViewStyle } from 'react-native';
import { View } from 'react-native';

type DecorativeOrbProps = {
  seed: string | number;
  color: string;
  size?: number;
  placement?: number;
  style?: ViewStyle;
};

const anchors = [
  (size: number): ViewStyle => ({ top: -size * 0.44, right: -size * 0.1 }),
  (size: number): ViewStyle => ({ top: -size * 0.4, left: -size * 0.16 }),
  (size: number): ViewStyle => ({ bottom: -size * 0.43, right: -size * 0.08 }),
  (size: number): ViewStyle => ({ bottom: -size * 0.4, left: -size * 0.14 }),
  (size: number): ViewStyle => ({ top: -size * 0.32, left: size * 0.62 }),
  (size: number): ViewStyle => ({ bottom: -size * 0.34, right: size * 0.3 }),
  (size: number): ViewStyle => ({ top: size * 0.18, right: -size * 0.44 }),
  (size: number): ViewStyle => ({ bottom: size * 0.08, left: -size * 0.42 }),
];

function stableHash(value: string | number) {
  let hash = 2166136261;
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/** A softly cropped circle with a repeatable, card-specific placement. */
export function DecorativeOrb({ seed, color, size = 90, placement, style }: DecorativeOrbProps) {
  const hash = stableHash(seed);
  const diameter = Math.round(size * (0.84 + (hash % 4) * 0.08));
  const anchorIndex = placement ?? (hash >>> 3);
  const anchor = anchors[anchorIndex % anchors.length](diameter);

  return <View pointerEvents="none" style={[{ position: 'absolute', width: diameter, height: diameter, borderRadius: diameter / 2, backgroundColor: color }, anchor, style]} />;
}
