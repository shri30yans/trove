export function formatLastSynced(value: string | null) {
  if (!value) return 'No saves synced yet';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Last sync time unavailable';
  return `Last synced ${new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date)}`;
}
