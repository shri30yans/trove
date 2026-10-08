import { z } from 'zod';
import { timestampSchema } from './common';
export const cadenceSchema = z.enum(['weekly', 'monthly', 'off']);
export const preferenceSettingsSchema = z.strictObject({ resurfacingEnabled: z.boolean(), resurfacingCadence: cadenceSchema, embeddingsEnabled: z.boolean() });
export const preferencesSchema = preferenceSettingsSchema.extend({ embeddingsAvailable: z.boolean(), updatedAt: timestampSchema.optional() });
export const preferencesResponseSchema = z.object({ preferences: preferencesSchema });
export const preferencePatchSchema = preferenceSettingsSchema.partial().refine((value) => Object.keys(value).length > 0);
export type Preferences = z.infer<typeof preferencesSchema>;
export type PreferencePatch = z.infer<typeof preferencePatchSchema>;
