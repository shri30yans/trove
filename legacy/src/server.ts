import Fastify from 'fastify';
import cors from '@fastify/cors';
import helmet from '@fastify/helmet';
import rateLimit from '@fastify/rate-limit';
import { z } from 'zod';
import { config } from './config.js';
import { pool } from './db/pool.js';
import { requireAuth, issueDevelopmentToken } from './auth.js';
import { ensureBucket } from './storage.js';
import { registerAccountRoutes } from './routes/account-routes.js';
import { registerMemoryRoutes } from './routes/memory-routes.js';
import { registerSearchRoutes } from './routes/search-routes.js';
import { registerSpaceRoutes } from './routes/space-routes.js';
import { startMemoryQueue } from './worker.js';

const app = Fastify({
  bodyLimit: 1_000_000,
  logger: {
    level: config.RUN_ENV === 'local' ? 'info' : 'warn',
    serializers: {
      req(request) { return { id: request.id, method: request.method, hostname: request.hostname }; },
      res(reply) { return { statusCode: reply.statusCode }; },
    },
  },
});

let stopMemoryQueue: (() => Promise<void>) | undefined;

app.decorateRequest('principal', null);

await app.register(cors, {
  origin: config.CORS_ORIGIN === '*' ? true : config.CORS_ORIGIN.split(',').map((origin) => origin.trim()),
  credentials: true,
  methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
});
await app.register(helmet, { contentSecurityPolicy: false });
await app.register(rateLimit, { max: 240, timeWindow: '1 minute' });

app.addHook('onRequest', async (request, reply) => {
  const path = request.url.split('?')[0] ?? '';
  if (path.startsWith('/v1/') && path !== '/v1/auth/dev-token') await requireAuth(request, reply);
});

app.get('/health/live', async () => ({ status: 'ok' }));
app.get('/health/ready', async (_request, reply) => {
  try {
    await pool.query('SELECT 1');
    return { status: 'ready' };
  } catch {
    return reply.code(503).send({ status: 'not_ready' });
  }
});

app.post('/v1/auth/dev-token', async (request, reply) => {
  if (config.RUN_ENV !== 'local' || !config.DEV_AUTH_ENABLED) {
    return reply.code(404).send({ error: { code: 'not_found', message: 'Not found.' } });
  }
  const parsed = z.object({
    subject: z.string().trim().min(1).max(120).default('local-user'),
    email: z.string().email().optional(),
    name: z.string().trim().max(120).optional(),
  }).safeParse(request.body ?? {});
  if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_dev_login', message: parsed.error.issues[0]?.message ?? 'Invalid development identity.' } });
  const token = await issueDevelopmentToken(parsed.data.subject, parsed.data.email, parsed.data.name);
  return { accessToken: token, tokenType: 'Bearer', expiresIn: 604800 };
});

await registerAccountRoutes(app);
await registerSpaceRoutes(app);
await registerMemoryRoutes(app);
await registerSearchRoutes(app);

app.setNotFoundHandler((_request, reply) => reply.code(404).send({ error: { code: 'not_found', message: 'Route not found.' } }));
app.setErrorHandler((error, request, reply) => {
  request.log.error({ err: error }, 'Request failed');
  const statusCode = typeof error === 'object' && error !== null && 'statusCode' in error && typeof error.statusCode === 'number'
    ? error.statusCode
    : undefined;
  const status = statusCode && statusCode >= 400 && statusCode < 500 ? statusCode : 500;
  const message = error instanceof Error ? error.message : 'The request could not be completed.';
  return reply.code(status).send({
    error: {
      code: status === 500 ? 'internal_error' : 'request_error',
      message: status === 500 ? 'The request could not be completed.' : message,
    },
  });
});

async function start() {
  await pool.query('SELECT 1');
  await ensureBucket();
  stopMemoryQueue = await startMemoryQueue();
  await app.listen({ host: config.API_HOST, port: config.API_PORT });
  app.log.info(`Trove API listening on ${config.API_HOST}:${config.API_PORT}`);
}

async function shutdown() {
  await app.close();
  await stopMemoryQueue?.();
  await pool.end();
}

process.on('SIGINT', () => { void shutdown(); });
process.on('SIGTERM', () => { void shutdown(); });

start().catch(async (error) => {
  app.log.error({ err: error }, 'Could not start Trove API');
  await pool.end();
  process.exitCode = 1;
});
