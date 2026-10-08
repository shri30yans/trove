import { readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pool } from './pool.js';

const MIGRATION_LOCK = [730013604, 42001];

async function migrate() {
  const client = await pool.connect();
  let lockHeld = false;
  let releaseError: Error | undefined;

  try {
    await client.query('SELECT pg_advisory_lock($1, $2)', MIGRATION_LOCK);
    lockHeld = true;

    await client.query(`CREATE TABLE IF NOT EXISTS schema_migrations (
      id text PRIMARY KEY,
      applied_at timestamptz NOT NULL DEFAULT now()
    )`);

    const directory = resolve(process.cwd(), 'migrations');
    const files = (await readdir(directory)).filter((name) => name.endsWith('.sql')).sort();

    for (const file of files) {
      const seen = await client.query('SELECT 1 FROM schema_migrations WHERE id = $1', [file]);
      if (seen.rowCount) continue;

      await client.query('BEGIN');
      try {
        const sql = await readFile(resolve(directory, file), 'utf8');
        await client.query(sql);
        await client.query('INSERT INTO schema_migrations (id) VALUES ($1)', [file]);
        await client.query('COMMIT');
        console.info(`Applied migration ${file}`);
      } catch (error) {
        try {
          await client.query('ROLLBACK');
        } catch (rollbackError) {
          releaseError = rollbackError instanceof Error ? rollbackError : new Error('Migration rollback failed.');
          console.error('Could not roll back the failed migration transaction', rollbackError);
        }
        throw error;
      }
    }
  } finally {
    if (lockHeld) {
      try {
        await client.query('SELECT pg_advisory_unlock($1, $2)', MIGRATION_LOCK);
      } catch (error) {
        releaseError ??= error instanceof Error ? error : new Error('Could not release the migration lock.');
        console.error('Could not release the migration lock', error);
      }
    }
    client.release(releaseError);
  }
}

migrate()
  .catch((error) => {
    console.error('Database migration failed', error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await pool.end();
  });
