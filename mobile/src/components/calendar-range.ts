export type CalendarRange = { start: Date; end: Date };
export function isSameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}
export function monthCells(month: Date): (Date | null)[] {
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = Array.from({ length: new Date(month.getFullYear(), month.getMonth(), 1).getDay() }, () => null);
  for (let day = 1; day <= count; day++) cells.push(new Date(month.getFullYear(), month.getMonth(), day));
  while (cells.length % 7) cells.push(null);
  return cells;
}
export function selectDay(anchor: Date | null, day: Date): { anchor: Date | null; range: CalendarRange } {
  if (!anchor) return { anchor: day, range: { start: day, end: day } };
  return { anchor: null, range: { start: day < anchor ? day : anchor, end: day < anchor ? anchor : day } };
}
/** The API's upper bound is exclusive: include the entire selected final day. */
export function calendarBounds(range: CalendarRange) {
  const after = new Date(range.start); after.setHours(0, 0, 0, 0);
  const before = new Date(range.end); before.setHours(0, 0, 0, 0); before.setDate(before.getDate() + 1);
  return { after: after.toISOString(), before: before.toISOString() };
}
export function rangeLabel({ start, end }: CalendarRange, currentYear = new Date().getFullYear()) {
  const withYear = start.getFullYear() !== currentYear || end.getFullYear() !== currentYear;
  const format = (value: Date) => new Intl.DateTimeFormat(undefined, withYear ? { month: 'short', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric' }).format(value);
  return isSameDay(start, end) ? format(start) : `${format(start)} – ${format(end)}`;
}
