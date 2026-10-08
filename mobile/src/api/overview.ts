import { request } from './client';
import { exploreSchema, updatesResponseSchema } from './schemas/overview';
export function getExplore() { return request('/v1/explore', exploreSchema); }
export function getUpdates() { return request('/v1/updates', updatesResponseSchema); }
