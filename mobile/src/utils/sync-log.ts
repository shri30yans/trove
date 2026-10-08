// Do not log captures, filenames, bearer tokens, signed URLs, or storage response bodies.
export function logSync(event: string, details: Record<string, string | number | boolean | null | undefined> = {}) {
  console.info('[Trove sync]', JSON.stringify({ time: new Date().toISOString(), event, ...details }));
}
