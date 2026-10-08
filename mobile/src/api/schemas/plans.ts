import { z } from 'zod';

export const planResponseSchema = z.strictObject({
  plan: z.strictObject({
    id: z.enum(['free', 'paid']),
    name: z.string().min(1),
    storageLimitBytes: z.number().int().positive(),
    storageUsedBytes: z.number().int().nonnegative(),
    storageRemainingBytes: z.number().int().nonnegative(),
  }).refine((plan) => plan.storageRemainingBytes === Math.max(0, plan.storageLimitBytes - plan.storageUsedBytes)),
});

export type StoragePlan = z.infer<typeof planResponseSchema>['plan'];
