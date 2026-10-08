import 'fastify';

declare module 'fastify' {
  interface FastifyRequest {
    principal: { id: string; subject: string; email: string | null; displayName: string | null } | null;
  }
}
