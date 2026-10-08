import type { FastifyInstance } from 'fastify';
import { pool } from '../db/pool.js';
import { createSpaceSchema, updateSpaceSchema } from '../schemas.js';

export async function registerSpaceRoutes(app: FastifyInstance) {
  app.get('/v1/spaces', async (request) => {
    const userId = request.principal!.id;
    const result = await pool.query(
      `SELECT s.id, s.name, s.description, s.color, s.icon, s.created_at, s.updated_at,
        count(ms.memory_id)::int AS memory_count
       FROM spaces s LEFT JOIN memory_spaces ms ON ms.space_id = s.id AND ms.user_id = s.user_id
       LEFT JOIN memories m ON m.id = ms.memory_id AND m.deleted_at IS NULL
       WHERE s.user_id = $1 AND s.deleted_at IS NULL
       GROUP BY s.id ORDER BY s.created_at ASC`,
      [userId],
    );
    return { spaces: result.rows.map((row) => ({
      id: row.id, name: row.name, description: row.description, color: row.color, icon: row.icon,
      memoryCount: row.memory_count, createdAt: row.created_at, updatedAt: row.updated_at,
    })) };
  });

  app.post('/v1/spaces', async (request, reply) => {
    const parsed = createSpaceSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_request', message: parsed.error.issues[0]?.message ?? 'Invalid Space.' } });
    const { name, description, color, icon } = parsed.data;
    try {
      const result = await pool.query(
        `INSERT INTO spaces(user_id, name, description, color, icon) VALUES($1,$2,$3,$4,$5)
         RETURNING id, name, description, color, icon, created_at, updated_at`,
        [request.principal!.id, name, description ?? null, color ?? null, icon ?? null],
      );
      return reply.code(201).send({ space: result.rows[0] });
    } catch (error) {
      if (typeof error === 'object' && error && 'code' in error && error.code === '23505') {
        return reply.code(409).send({ error: { code: 'space_name_exists', message: 'A Space with that name already exists.' } });
      }
      throw error;
    }
  });

  app.patch('/v1/spaces/:id', async (request, reply) => {
    const parsed = updateSpaceSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: { code: 'invalid_request', message: parsed.error.issues[0]?.message ?? 'Invalid Space.' } });
    const { id } = request.params as { id: string };
    const userId = request.principal!.id;
    const patch = parsed.data;
    try {
      const result = await pool.query(
        `UPDATE spaces SET name = COALESCE($3,name), description = CASE WHEN $4 THEN $5 ELSE description END,
          color = CASE WHEN $6 THEN $7 ELSE color END, icon = CASE WHEN $8 THEN $9 ELSE icon END, updated_at = now()
         WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL
         RETURNING id, name, description, color, icon, created_at, updated_at`,
        [id, userId, patch.name ?? null, 'description' in patch, patch.description ?? null,
          'color' in patch, patch.color ?? null, 'icon' in patch, patch.icon ?? null],
      );
      if (!result.rowCount) return reply.code(404).send({ error: { code: 'space_not_found', message: 'Space not found.' } });
      return { space: result.rows[0] };
    } catch (error) {
      if (typeof error === 'object' && error && 'code' in error && error.code === '23505') {
        return reply.code(409).send({ error: { code: 'space_name_exists', message: 'A Space with that name already exists.' } });
      }
      throw error;
    }
  });

  app.delete('/v1/spaces/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const result = await pool.query(
      'UPDATE spaces SET deleted_at = now(), updated_at = now() WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL RETURNING id',
      [id, request.principal!.id],
    );
    if (!result.rowCount) return reply.code(404).send({ error: { code: 'space_not_found', message: 'Space not found.' } });
    return reply.code(204).send();
  });
}
