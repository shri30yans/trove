import { z } from 'zod';
export const authCredentialsSchema = z.strictObject({ email: z.email(), password: z.string().min(1).max(256) });
export const authSessionSchema = z.object({ accessToken: z.string().min(1), refreshToken: z.string().min(1), tokenType: z.literal('Bearer'), expiresIn: z.number().int().positive() });
export const storedAuthSessionSchema = z.object({ accessToken: z.string().min(1), refreshToken: z.string().min(1).nullable(), expiresAt: z.number().int().positive().nullable() });
export const signedInResponseSchema = z.object({ status: z.literal('authenticated'), session: authSessionSchema });
export const accountDeletionRequestSchema = z.object({ requestedAt: z.string().datetime(), deleteAfter: z.string().datetime(), deletionCancellable: z.boolean() });
export const accountDeletionStatusSchema = z.object({ deletionScheduled: z.boolean(), deleteAfter: z.string().datetime().nullable(), deletionComplete: z.boolean(), deletionCancellable: z.boolean() });
