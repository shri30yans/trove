import dotenv from 'dotenv';
import { z } from 'zod';

const runEnvironment = z.enum(['local', 'stage', 'prod']).parse(process.env.RUN_ENV);
dotenv.config({ path: `${runEnvironment}.env` });

const optionalUrl = z.preprocess(
  (value) => (typeof value === 'string' && value.trim() === '' ? undefined : value),
  z.string().url().optional(),
);
const optionalText = z.preprocess(
  (value) => (typeof value === 'string' && value.trim() === '' ? undefined : value),
  z.string().optional(),
);

const envSchema = z.object({
  RUN_ENV: z.enum(['local', 'stage', 'prod']).default(runEnvironment),
  API_HOST: z.string().default('0.0.0.0'),
  API_PORT: z.coerce.number().int().min(1).max(65535).default(Number(process.env.PORT) || 4000),
  CORS_ORIGIN: z.string().default(runEnvironment === 'local' ? '*' : ''),
  DATABASE_URL: z.string().min(1),
  DATABASE_POOL_MAX: z.coerce.number().int().min(1).max(20).default(5),
  S3_ENDPOINT: z.string().url(),
  S3_PUBLIC_ENDPOINT: z.string().url(),
  S3_REGION: z.string().min(1),
  S3_BUCKET: z.string().min(1),
  S3_ACCESS_KEY: z.string().min(1),
  S3_SECRET_KEY: z.string().min(1),
  S3_FORCE_PATH_STYLE: z.enum(['true', 'false']).default('true').transform((v) => v === 'true'),
  UPLOAD_URL_TTL_SECONDS: z.coerce.number().int().min(60).max(3600).default(600),
  MAX_UPLOAD_BYTES: z.coerce.number().int().min(1024).default(52_428_800),
  OPENAI_API_KEY: optionalText,
  OPENAI_TEXT_MODEL: z.string().default('gpt-4.1-mini'),
  OPENAI_VISION_MODEL: z.string().default('gpt-4.1-mini'),
  OPENAI_TRANSCRIPTION_MODEL: z.string().default('gpt-4o-mini-transcribe'),
  NOMIC_EMBEDDING_SERVICE_URL: z.string().url(),
  NOMIC_SERVICE_TOKEN: optionalText,
  AUTH_JWKS_URL: optionalUrl,
  AUTH_ISSUER: optionalText,
  AUTH_AUDIENCE: z.string().default('authenticated'),
  DEV_AUTH_ENABLED: z.enum(['true', 'false']).default(runEnvironment === 'local' ? 'true' : 'false').transform((v) => v === 'true'),
  DEV_JWT_SECRET: z.string().default('local_only_change_me_before_any_shared_environment'),
});

const parsed = envSchema.safeParse(process.env);
if (!parsed.success) {
  throw new Error(`Invalid environment configuration: ${parsed.error.message}`);
}

export const config = parsed.data;

if (config.RUN_ENV !== 'local') {
  if (config.DEV_AUTH_ENABLED) throw new Error('DEV_AUTH_ENABLED must be false in production');
  if (!config.AUTH_JWKS_URL || !config.AUTH_ISSUER) {
    throw new Error('AUTH_JWKS_URL and AUTH_ISSUER are required in production');
  }
  if (!config.NOMIC_SERVICE_TOKEN) throw new Error('NOMIC_SERVICE_TOKEN is required outside RUN_ENV=local');
  if (!config.DATABASE_URL.includes('sslmode=require') && !config.DATABASE_URL.includes('sslmode=verify-full')) {
    throw new Error('DATABASE_URL must require TLS in production (sslmode=require)');
  }
  if (config.CORS_ORIGIN === '*' || !config.CORS_ORIGIN.trim()) {
    throw new Error('CORS_ORIGIN must list allowed production origins');
  }
  if (![config.S3_ENDPOINT, config.S3_PUBLIC_ENDPOINT, config.NOMIC_EMBEDDING_SERVICE_URL]
    .every((value) => value.startsWith('https://'))) {
    throw new Error('Supabase Storage and Nomic service URLs must use HTTPS outside RUN_ENV=local');
  }
}
