import { StyleSheet } from 'react-native';
import { Button } from './button';
import { spacing } from '../theme';

/** The one "there are more memories" control, shared by every list that pages. */
export function LoadMoreButton({ loading, onPress, label = 'Load more memories' }: { loading: boolean; onPress: () => void; label?: string }) {
  return (
    <Button
      style={styles.host}
      label={loading ? 'Loading more memories…' : label}
      icon="chevron-down"
      iconPosition="right"
      variant="secondary"
      fills
      loading={loading}
      onPress={onPress}
    />
  );
}

const styles = StyleSheet.create({ host: { marginTop: spacing.lg } });
