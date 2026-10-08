import { z } from 'zod';
import { parseContract } from './common';

const archivePrefixSchema = z.literal('UEsDBA==');
/** A complete archive must begin with a ZIP local file header. */
export function validateArchivePrefix(prefix: unknown): void {
  parseContract(archivePrefixSchema, prefix);
}
