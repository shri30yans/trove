import type { ProcessingSummary } from '../../api/schemas/memories';

export type ProcessingView =
  | { state: 'empty' }
  | { state: 'attention'; message: string }
  | { state: 'working'; message: string }
  | { state: 'complete'; message: string };

export function processingView(counts: ProcessingSummary): ProcessingView {
  if (!counts.total) return { state: 'empty' };
  if (counts.failed) {
    return { state: 'attention', message: `${counts.failed} ${counts.failed === 1 ? 'save needs' : 'saves need'} attention.` };
  }
  const active = counts.queued + counts.processing;
  if (active) {
    return { state: 'working', message: `${active} ${active === 1 ? 'save is' : 'saves are'} being understood.` };
  }
  return { state: 'complete', message: `All ${counts.ready} ${counts.ready === 1 ? 'save was' : 'saves were'} understood.` };
}
