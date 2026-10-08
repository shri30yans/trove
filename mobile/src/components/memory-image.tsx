import { useState } from 'react';
import { Image, Text, View, type ImageProps } from 'react-native';
import { useMediaSource } from '../hooks/use-media-source';
import { useTheme } from '../providers/theme-provider';
import { text } from '../theme';

type MemoryImageProps = Omit<ImageProps, 'source'> & { uri: string };
export function MemoryImage(props: MemoryImageProps) {
  return <ResolvedMemoryImage key={props.uri} {...props} />;
}
function ResolvedMemoryImage({ uri, ...props }: MemoryImageProps) {
  const source = useMediaSource(uri);
  const { colors } = useTheme();
  const [failed, setFailed] = useState(false);
  if (failed || source.error) return <View style={props.style}><Text accessibilityRole="alert" style={[text.caption, { color: colors.muted }]}>Image unavailable</Text></View>;
  if (!source.data) return <View style={props.style} accessibilityLabel="Loading image" />;
  return <Image {...props} source={source.data} onError={(event) => { setFailed(true); props.onError?.(event); }} />;
}
