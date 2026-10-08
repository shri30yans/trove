import { readMedia } from '../api/media';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import * as XLSX from '@e965/xlsx';
import { Ionicons } from '@expo/vector-icons';
import { Button } from './button';
import { Eyebrow } from './eyebrow';
import { StatePanel } from './state-panel';
import { useThemedStyles, useTheme } from '../providers/theme-provider';
import { control, layout, radii, spacing, text } from '../theme';
import type { Palette } from '../theme';
import type { MemoryAsset } from '../types';

type Sheet = { name: string; rows: string[][] };
type WorkbookResult = { url: string; sheets: Sheet[]; error?: string };

const MAX_ROWS = 50;
const MAX_COLUMNS = 20;
const CELL_WIDTH = 132;
const ROW_NUMBER_WIDTH = 42;

function columnName(index: number) {
  let column = index + 1;
  let label = '';
  while (column > 0) {
    const remainder = (column - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    column = Math.floor((column - 1) / 26);
  }
  return label;
}

export function SpreadsheetPreview({ asset, onOpenExternally }: { asset?: MemoryAsset; onOpenExternally: () => void }) {
  const { colors } = useTheme();
  const styles = useThemedStyles(makeStyles);
  const [workbook, setWorkbook] = useState<WorkbookResult | null>(null);
  const [activeSheet, setActiveSheet] = useState(0);
  const [selectedCell, setSelectedCell] = useState<{ row: number; column: number; value: string } | null>(null);
  useEffect(() => {
    let active = true;
    if (!asset?.url) return () => { active = false; };
    const controller = new AbortController();
    readMedia(asset.url, asset.mimeType, controller.signal).then((buffer) => {
      const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array', cellDates: false });
      const nextSheets = workbook.SheetNames.map((name) => {
        const worksheet = workbook.Sheets[name];
        const rows = worksheet ? XLSX.utils.sheet_to_json<unknown[]>(worksheet, { header: 1, defval: '', raw: false, blankrows: false }) : [];
        return { name, rows: rows.slice(0, MAX_ROWS).map((row) => row.slice(0, MAX_COLUMNS).map((value) => String(value ?? ''))) };
      });
      if (active) {
        setWorkbook({ url: asset.url, sheets: nextSheets });
        setActiveSheet(0);
        setSelectedCell(null);
      }
    }).catch((loadError: unknown) => {
      if (active) setWorkbook({ url: asset.url, sheets: [], error: loadError instanceof Error ? loadError.message : 'This workbook could not be previewed.' });
    });
    return () => { active = false; controller.abort(); };
  }, [asset?.url, asset?.mimeType]);

  const loading = !!asset?.url && workbook?.url !== asset.url;
  const error = !asset?.url ? 'This memory does not include a workbook file.' : workbook?.url === asset.url ? workbook.error : null;
  const sheets = asset?.url && workbook?.url === asset.url ? workbook.sheets : [];
  const sheet = sheets[activeSheet];
  const columnCount = useMemo(() => Math.min(MAX_COLUMNS, Math.max(3, ...(sheet?.rows.map((row) => row.length) ?? [3]))), [sheet]);

  return <View style={styles.container}>
    <View style={styles.previewHeader}><View><Eyebrow label="Spreadsheet · view only" /><Text style={styles.previewHint}>First {MAX_ROWS} rows · Tap a cell to read it</Text></View><Ionicons name="grid-outline" size={19} color={colors.muted} /></View>
    {loading ? <StatePanel bare loading body="Opening workbook…" />
      : error ? <StatePanel bare icon="document-text-outline" body={error} action="Open in Sheets or Excel" onAction={onOpenExternally} />
        : sheet ? <>
          <ScrollView horizontal showsHorizontalScrollIndicator>
            <View style={styles.table}>
              <View style={styles.row}>
                <View style={[styles.cell, styles.cornerCell, { width: ROW_NUMBER_WIDTH }]}><Text style={styles.columnHeaderText}>#</Text></View>
                {Array.from({ length: columnCount }, (_, index) => <View key={index} style={[styles.cell, styles.headerCell, { width: CELL_WIDTH }]}><Text numberOfLines={1} style={styles.columnHeaderText}>{columnName(index)}</Text></View>)}
              </View>
              {sheet.rows.map((row, rowIndex) => <View key={rowIndex} style={styles.row}>
                <View style={[styles.cell, styles.rowHeaderCell, { width: ROW_NUMBER_WIDTH }]}><Text style={styles.rowHeaderText}>{rowIndex + 1}</Text></View>
                {Array.from({ length: columnCount }, (_, columnIndex) => {
                  const value = row[columnIndex] || '';
                  const selected = selectedCell?.row === rowIndex && selectedCell.column === columnIndex;
                  return <Pressable key={columnIndex} onPress={() => setSelectedCell({ row: rowIndex, column: columnIndex, value })} style={[styles.cell, styles.dataCell, { width: CELL_WIDTH }, selected && styles.selectedCell]} accessibilityRole="button" accessibilityLabel={`${columnName(columnIndex)}${rowIndex + 1}: ${value || 'empty'}`}>
                    <Text numberOfLines={1} style={styles.cellText}>{value}</Text>
                  </Pressable>;
                })}
              </View>)}
              {!sheet.rows.length && <View style={styles.emptySheet}><Text style={styles.emptyText}>This sheet is empty.</Text></View>}
            </View>
          </ScrollView>
          {selectedCell && <View style={styles.cellDetail}><Text style={styles.cellDetailLabel}>{columnName(selectedCell.column)}{selectedCell.row + 1}</Text><Text selectable style={styles.cellDetailValue}>{selectedCell.value || 'Empty cell'}</Text></View>}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.sheetTabs}>
            {sheets.map((item, index) => <Pressable key={item.name} onPress={() => { setActiveSheet(index); setSelectedCell(null); }} style={[styles.sheetTab, index === activeSheet && styles.activeSheetTab]} accessibilityRole="tab" accessibilityState={{ selected: index === activeSheet }}><Text style={[styles.sheetTabText, index === activeSheet && styles.activeSheetTabText]} numberOfLines={1}>{item.name}</Text></Pressable>)}
          </ScrollView>
          <View style={styles.externalFooter}><Button label="Edit in Sheets or Excel" icon="open-outline" variant="quiet" fills onPress={onOpenExternally} /></View>
        </> : null}
  </View>;
}

function makeStyles(colors: Palette) {
  return StyleSheet.create({
    container: { marginTop: layout.gutter, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, borderRadius: radii.lg, backgroundColor: colors.surface },
    previewHeader: { minHeight: control.large, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md, paddingHorizontal: layout.pad, borderBottomWidth: 1, borderBottomColor: colors.borderSoft },
    previewHint: { marginTop: spacing.xs, color: colors.muted, ...text.caption },
    table: { minWidth: '100%' },
    row: { height: 40, flexDirection: 'row' },
    cell: { height: 40, justifyContent: 'center', paddingHorizontal: spacing.md, borderRightWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
    cornerCell: { alignItems: 'center', backgroundColor: colors.background },
    headerCell: { backgroundColor: colors.background },
    columnHeaderText: { color: colors.secondary, textAlign: 'center', ...text.buttonSmall },
    rowHeaderCell: { alignItems: 'center', backgroundColor: colors.background },
    rowHeaderText: { color: colors.muted, ...text.caption },
    dataCell: { backgroundColor: colors.surface },
    cellText: { color: colors.foreground, ...text.subtitle },
    selectedCell: { borderWidth: 1, borderColor: colors.blueDeep, backgroundColor: colors.surfacePressed },
    cellDetail: { gap: spacing.xxs, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: colors.borderSoft, backgroundColor: colors.background },
    cellDetailLabel: { color: colors.muted, ...text.eyebrow },
    cellDetailValue: { color: colors.foreground, ...text.body },
    sheetTabs: { gap: spacing.xxs, paddingHorizontal: spacing.md, paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: colors.borderSoft },
    sheetTab: { minHeight: control.compact, justifyContent: 'center', paddingHorizontal: spacing.lg, borderRadius: radii.sm },
    activeSheetTab: { backgroundColor: colors.lavender },
    sheetTabText: { color: colors.muted, maxWidth: 140, ...text.buttonSmall },
    activeSheetTabText: { color: colors.foreground },
    externalFooter: { borderTopWidth: 1, borderTopColor: colors.borderSoft },
    emptySheet: { minHeight: 90, alignItems: 'center', justifyContent: 'center' },
    emptyText: { color: colors.muted, ...text.caption },
  });
}
