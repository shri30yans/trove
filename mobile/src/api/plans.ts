import { request } from './client';
import { planResponseSchema } from './schemas/plans';

export function getPlan() {
  return request('/v1/plan', planResponseSchema);
}
