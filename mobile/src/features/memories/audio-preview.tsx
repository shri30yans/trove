import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { Button, IconButton, Notice, StatePanel } from '../../components';
import { useMediaSource } from '../../hooks/use-media-source';
import { useThemedStyles } from '../../providers/theme-provider';
import { radii, spacing, text, type Palette } from '../../theme';
import { formatDuration, WAVE_HEIGHTS } from '../../utils/media';

export function AudioPreview({ uri }: { uri: string }) {
  const styles = useThemedStyles(makeStyles);
  const source = useMediaSource(uri);
  const player = useAudioPlayer(source.data ?? null);
  const status = useAudioPlayerStatus(player);
  const [speed, setSpeed] = useState<1 | 1.5 | 2>(1);
  const togglePlayback = () => {
    if (status.playing) player.pause();
    else {
      if (status.didJustFinish) player.seekTo(0);
      player.play();
    }
  };
  const cycleSpeed = () => {
    const next = speed === 1 ? 1.5 : speed === 1.5 ? 2 : 1;
    player.setPlaybackRate(next);
    setSpeed(next);
  };
  if (source.error || status.playbackState === 'failed') return <Notice body="This audio could not be loaded. Try opening the memory again." />;
  if (source.isPending || !status.isLoaded) return <StatePanel bare loading body="Loading audio…" />;
  return <View style={styles.audioPreview}>
    <View style={styles.audioControls}><IconButton icon={status.playing ? 'pause' : 'play'} variant="tinted" onPress={togglePlayback} accessibilityLabel={status.playing ? 'Pause audio file' : 'Play audio file'} /><Button label={`${speed}×`} variant="quiet" size="compact" onPress={cycleSpeed} /></View>
    <View style={styles.audioContent}><View style={styles.waveform}>{WAVE_HEIGHTS.map((height, index) => <View key={index} style={[styles.waveBar, { height }]} />)}</View><View style={styles.audioTimes}><Text style={styles.mediaTitle}>{status.playing ? 'Playing audio file' : 'Audio file'}</Text><Text style={styles.mediaHint}>{formatDuration(status.currentTime)} / {formatDuration(status.duration)}</Text></View></View>
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    waveform: { height: 35, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.xxs },
    waveBar: { width: 2, borderRadius: radii.pill, backgroundColor: colors.blueDeep },
    audioTimes: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
    audioPreview: { minHeight: 106, flexDirection: 'row', alignItems: 'center', gap: spacing.lg, padding: spacing.xl, borderRadius: radii.lg, backgroundColor: colors.lavender },
    audioControls: { alignItems: 'center', gap: spacing.sm },
    audioContent: { flex: 1, minWidth: 0 },
    mediaTitle: { color: colors.foreground, ...text.buttonSmall },
    mediaHint: { color: colors.secondary, ...text.meta },
  });
}
