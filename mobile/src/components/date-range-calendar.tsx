import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useThemedStyles } from '../providers/theme-provider';
import { IconButton } from './icon-button';
import { radii, spacing, text, type Palette } from '../theme';

import { isSameDay, monthCells, selectDay, type CalendarRange } from './calendar-range';
export type { CalendarRange } from './calendar-range';

const weekdayLabels = Array.from({ length: 7 }, (_, index) => new Intl.DateTimeFormat(undefined, { weekday: 'narrow' }).format(new Date(2024, 0, 7 + index)));

/** In-house month calendar. First tap anchors a day, second tap completes the range either direction. */
export function DateRangeCalendar({ value, onChange }: { value: CalendarRange | null; onChange: (range: CalendarRange) => void }) {
  const styles = useThemedStyles(makeStyles);
  const [today] = useState(() => new Date());
  const [viewMonth, setViewMonth] = useState(() => {
    const base = value?.start ?? today;
    return new Date(base.getFullYear(), base.getMonth(), 1);
  });
  const [anchor, setAnchor] = useState<Date | null>(null);

  const cells = useMemo(() => monthCells(viewMonth), [viewMonth]);

  const monthLabel = useMemo(() => new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(viewMonth), [viewMonth]);

  const shiftMonth = (delta: number) => {
    setViewMonth((month) => new Date(month.getFullYear(), month.getMonth() + delta, 1));
    setAnchor(null);
  };

  const pickDay = (day: Date) => {
    const selected = selectDay(anchor, day);
    setAnchor(selected.anchor);
    onChange(selected.range);
  };

  return <View style={styles.calendar}>
    <View style={styles.monthRow}>
      <IconButton icon="chevron-back" size="small" variant="plain" onPress={() => shiftMonth(-1)} accessibilityLabel="Previous month" />
      <Text style={styles.monthLabel}>{monthLabel}</Text>
      <IconButton icon="chevron-forward" size="small" variant="plain" onPress={() => shiftMonth(1)} accessibilityLabel="Next month" />
    </View>
    <View style={styles.weekRow}>
      {weekdayLabels.map((label, index) => <Text key={`weekday-${index}`} style={styles.weekdayLabel}>{label}</Text>)}
    </View>
    <View style={styles.daysGrid}>
      {cells.map((day, index) => {
        if (!day) return <View key={`empty-${index}`} style={styles.daySlot} />;
        const isEdge = !!value && (isSameDay(day, value.start) || isSameDay(day, value.end));
        const inRange = !!value && value.start !== value.end && day > value.start && day < value.end;
        return <Pressable key={day.toISOString()} onPress={() => pickDay(day)} accessibilityRole="button" accessibilityState={{ selected: isEdge || inRange }} accessibilityLabel={new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(day)} style={({ pressed }) => [styles.daySlot, pressed && styles.dayPressed]}>
          <View style={[styles.dayCell, isEdge && styles.dayEdge, inRange && styles.dayInRange, !value && isSameDay(day, today) && styles.dayToday]}>
            <Text style={[styles.dayText, isEdge && styles.dayTextEdge, inRange && styles.dayTextInRange]}>{day.getDate()}</Text>
          </View>
        </Pressable>;
      })}
    </View>
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    calendar: { borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, backgroundColor: colors.surface, padding: spacing.md },
    monthRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
    monthLabel: { color: colors.foreground, ...text.section },
    weekRow: { flexDirection: 'row', marginBottom: spacing.xs },
    weekdayLabel: { width: '14.28%', textAlign: 'center', color: colors.muted, ...text.meta },
    daysGrid: { flexDirection: 'row', flexWrap: 'wrap' },
    daySlot: { width: '14.28%', minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingVertical: spacing.xxs },
    dayPressed: { opacity: 0.7 },
    dayCell: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center', borderRadius: radii.pill },
    dayEdge: { backgroundColor: colors.deep },
    dayInRange: { backgroundColor: colors.thistle, borderRadius: 0 },
    dayToday: { borderWidth: 1, borderColor: colors.muted },
    dayText: { color: colors.foreground, ...text.buttonSmall },
    dayTextEdge: { color: colors.surface, fontWeight: '700' },
    dayTextInRange: { color: colors.foreground },
  });
}
