import { request } from './client';
import { requestBody } from './schemas/common';
import { preferencesResponseSchema, preferencePatchSchema, type PreferencePatch } from './schemas/preferences';
export function getPreferences() { return request('/v1/preferences', preferencesResponseSchema); }
export function patchPreferences(patch: PreferencePatch) {
  return request('/v1/preferences', preferencesResponseSchema, { method: 'PATCH', body: requestBody(preferencePatchSchema, patch) });
}
