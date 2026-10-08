import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import { View, type StyleProp, type ViewStyle } from 'react-native';
import { useMediaSource } from '../hooks/use-media-source';
import { Notice } from './notice';
import { StatePanel } from './state-panel';

export function VideoPlayer({ uri, style }: { uri: string; style: StyleProp<ViewStyle> }) {
  const source = useMediaSource(uri);
  const player = useVideoPlayer(source.data ?? null, (instance) => { instance.loop = false; });
  const status = useEvent(player, 'statusChange', { status: player.status });
  if (source.error || status.status === 'error') return <View style={style}><Notice body="This video could not be loaded. Try opening the memory again." /></View>;
  if (source.isPending) return <View style={style}><StatePanel bare loading body="Loading video…" /></View>;
  return <VideoView player={player} style={style} nativeControls contentFit="contain" />;
}
