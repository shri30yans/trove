import type { FastifyReply, FastifyRequest } from 'fastify';
import { createRemoteJWKSet, jwtVerify, SignJWT } from 'jose';
import { config } from './config.js';
import { pool } from './db/pool.js';

let jwks: ReturnType<typeof createRemoteJWKSet> | undefined;
if (config.AUTH_JWKS_URL) jwks = createRemoteJWKSet(new URL(config.AUTH_JWKS_URL));

export async function verifyBearerToken(token: string) {
  if (jwks) {
    const verified = await jwtVerify(token, jwks, {
      issuer: config.AUTH_ISSUER,
      audience: config.AUTH_AUDIENCE,
    });
    return verified.payload;
  }
  if (config.RUN_ENV === 'local' && config.DEV_AUTH_ENABLED) {
    const verified = await jwtVerify(token, new TextEncoder().encode(config.DEV_JWT_SECRET), {
      algorithms: ['HS256'],
      issuer: 'trove-local-dev',
      audience: config.AUTH_AUDIENCE,
    });
    return verified.payload;
  }
  throw new Error('No JWT verification provider is configured');
}

export async function issueDevelopmentToken(subject: string, email?: string, name?: string) {
  if (config.RUN_ENV !== 'local' || !config.DEV_AUTH_ENABLED) {
    throw new Error('Development token endpoint is disabled');
  }
  return new SignJWT({ email, name })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject(subject)
    .setIssuer('trove-local-dev')
    .setAudience(config.AUTH_AUDIENCE)
    .setIssuedAt()
    .setExpirationTime('7d')
    .sign(new TextEncoder().encode(config.DEV_JWT_SECRET));
}

async function loadPrincipal(subject: string, email: string | null, displayName: string | null) {
  const result = await pool.query<{ id: string; email: string | null; display_name: string | null }>(
    `INSERT INTO app_users (auth_subject, email, display_name)
     VALUES ($1, $2, $3)
     ON CONFLICT (auth_subject) DO UPDATE SET
       email = COALESCE(EXCLUDED.email, app_users.email),
       display_name = COALESCE(EXCLUDED.display_name, app_users.display_name),
       updated_at = now()
     RETURNING id, email, display_name`,
    [subject, email, displayName],
  );
  return { id: result.rows[0]!.id, subject, email: result.rows[0]!.email, displayName: result.rows[0]!.display_name };
}

export async function requireAuth(request: FastifyRequest, reply: FastifyReply) {
  const header = request.headers.authorization;
  if (!header?.startsWith('Bearer ')) {
    return reply.code(401).send({ error: { code: 'unauthorized', message: 'A bearer token is required.' } });
  }
  try {
    const payload = await verifyBearerToken(header.slice(7));
    if (typeof payload.sub !== 'string' || payload.sub.length === 0) throw new Error('JWT is missing a subject');
    request.principal = await loadPrincipal(
      payload.sub,
      typeof payload.email === 'string' ? payload.email : null,
      typeof payload.name === 'string' ? payload.name : null,
    );
  } catch {
    return reply.code(401).send({ error: { code: 'invalid_token', message: 'The bearer token is invalid or expired.' } });
  }
}
