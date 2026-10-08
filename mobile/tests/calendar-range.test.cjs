const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createLoader } = require('./helpers/typescript-loader.cjs');
const { monthCells, selectDay, calendarBounds } = createLoader()('src/components/calendar-range.ts');
test('month grid contains leap day with full week rows', () => {
  const cells = monthCells(new Date(2024, 1, 1));
  assert.equal(cells.filter(Boolean).length, 29);
  assert.equal(cells.length % 7, 0);
  assert.equal(cells.find(Boolean).getDay(), 4);
});
test('two taps select a range in either direction', () => {
  const first = new Date(2026, 9, 7); const second = new Date(2026, 9, 1);
  const anchored = selectDay(null, first);
  assert.equal(anchored.anchor, first);
  const selected = selectDay(anchored.anchor, second);
  assert.equal(selected.range.start, second);
  assert.equal(selected.range.end, first);
  assert.equal(selected.anchor, null);
});
test('exclusive API bounds include every instant of the final selected day', () => {
  const selected = new Date(2026, 9, 7);
  const bounds = calendarBounds({ start: selected, end: selected });
  const finalInstant = new Date(2026, 9, 7, 23, 59, 59, 999);
  assert.ok(finalInstant.toISOString() < bounds.before);
  assert.equal(new Date(bounds.before).getDate(), 8);
  assert.equal(new Date(bounds.after).getHours(), 0);
});

test('month grid always starts at the first day regardless of the supplied day', () => {
  const first = monthCells(new Date(2026, 9, 1));
  const middle = monthCells(new Date(2026, 9, 14));
  assert.deepEqual(Array.from(middle, (day) => day?.getTime() ?? null), Array.from(first, (day) => day?.getTime() ?? null));
});
