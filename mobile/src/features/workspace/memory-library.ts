import type { Memory } from '../../types';

export type MemoryPage = { memories: Memory[]; nextCursor: string | null; startedRevision: number };
export type ConfirmedMemory = { memory: Memory; revision: number };

/** A response can replace a confirmation only if its request started after that confirmation. */
export function projectMemoryLibrary(pages: MemoryPage[], confirmed: ConfirmedMemory[], deleted: Set<string>): Memory[] {
  const confirmations = new Map(confirmed.map((entry) => [entry.memory.id, entry]));
  const listed = new Map<string, Memory>();
  for (const page of pages) {
    for (const memory of page.memories) {
      if (deleted.has(memory.id) || listed.has(memory.id)) continue;
      const entry = confirmations.get(memory.id);
      listed.set(memory.id, entry && page.startedRevision < entry.revision
        ? entry.memory
        : { ...memory, replacesLocalId: entry?.memory.replacesLocalId });
    }
  }
  return [
    ...confirmed.filter(({ memory }) => !deleted.has(memory.id) && !listed.has(memory.id)).map(({ memory }) => memory),
    ...listed.values(),
  ];
}
