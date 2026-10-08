import { request } from './client';
import { requestBody } from './schemas/common';
import { spacesResponseSchema, spaceResponseSchema, createSpaceSchema } from './schemas/spaces';
export function getSpaces() { return request('/v1/spaces', spacesResponseSchema); }
export function createSpace(name: string, description: string) {
  return request('/v1/spaces', spaceResponseSchema, { method: 'POST', body: requestBody(createSpaceSchema, { name, description: description.trim() || null }) });
}
