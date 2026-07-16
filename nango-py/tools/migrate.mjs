// Runs the authoritative Knex migrations (packages/database/lib/migrations)
// against a target Postgres so the Python integration-test harness operates on
// the exact same schema the TypeScript backend produces.
//
// Usage:
//   node nango-py/tools/migrate.mjs "postgresql://user:pass@host:5432/db" [schema]
//
// Also creates the keystore (private_keys) and records (nango_records schema)
// tables that have their own .ts migration files not runnable by the .cjs
// Knex CLI alongside the app migrations.

import knex from 'knex';
import { resolve } from 'node:path';

const connectionString = process.argv[2];
const schema = process.argv[3] || process.env.NANGO_DB_SCHEMA || 'nango';

if (!connectionString) {
    console.error('usage: node migrate.mjs <connectionString> [schema]');
    process.exit(1);
}

const migrationsDir = resolve(new URL('../../packages/database/lib/migrations', import.meta.url).pathname);

const db = knex({
    client: 'pg',
    connection: connectionString,
    searchPath: [schema, 'public']
});

try {
    await db.raw(`CREATE SCHEMA IF NOT EXISTS ${schema}`);
    await db.raw(`CREATE EXTENSION IF NOT EXISTS "uuid-ossp"`);
    await db.raw(`SET search_path TO ${schema}, public`);
    const [_, pending] = await db.migrate.list({ directory: migrationsDir });
    if (pending.length === 0) {
        console.log('no pending migrations');
    } else {
        await db.migrate.latest({
            directory: migrationsDir,
            tableName: '_nango_auth_migrations',
            schemaName: schema
        });
        console.log(`migrations complete (${pending.length} applied)`);
    }

    // Keystore schema (packages/keystore/lib/db/migrations).
    await db.raw(`
        DO $$ BEGIN
            CREATE TYPE private_key_entity_types AS ENUM
                ('connect_session', 'connection', 'environment');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await db.raw(`
        CREATE TABLE IF NOT EXISTS private_keys (
            id SERIAL PRIMARY KEY,
            display_name VARCHAR(255) NOT NULL,
            account_id INTEGER NOT NULL,
            environment_id INTEGER NOT NULL,
            encrypted BYTEA,
            hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            last_access_at TIMESTAMP WITH TIME ZONE,
            entity_type private_key_entity_types NOT NULL,
            entity_id INTEGER NOT NULL
        );
    `);
    console.log('keystore schema ready');

    // Records DB schema (packages/records/lib/db/migrations).
    // Non-partitioned for test simplicity; queries work identically.
    await db.raw(`CREATE SCHEMA IF NOT EXISTS nango_records`);
    await db.raw(`
        CREATE TABLE IF NOT EXISTS nango_records.records (
            id UUID NOT NULL,
            external_id VARCHAR(255) NOT NULL,
            json JSONB,
            data_hash VARCHAR(255) NOT NULL,
            connection_id INTEGER NOT NULL,
            model VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP WITH TIME ZONE,
            sync_id UUID,
            sync_job_id INTEGER,
            pruned_at TIMESTAMP WITH TIME ZONE
        );
    `);
    await db.raw(`
        CREATE UNIQUE INDEX IF NOT EXISTS idx_records_conn_model_ext
            ON nango_records.records (connection_id, model, external_id);
    `);
    await db.raw(`
        CREATE UNIQUE INDEX IF NOT EXISTS idx_records_conn_model_id
            ON nango_records.records (connection_id, model, id);
    `);
    await db.raw(`
        CREATE INDEX IF NOT EXISTS idx_records_conn_model_updated
            ON nango_records.records (connection_id, model, updated_at, id);
    `);
    await db.raw(`
        CREATE TABLE IF NOT EXISTS nango_records.records_data (
            id UUID NOT NULL,
            connection_id INTEGER NOT NULL,
            model VARCHAR(255) NOT NULL,
            data JSONB NOT NULL,
            PRIMARY KEY (connection_id, model, id)
        );
    `);
    await db.raw(`
        CREATE TABLE IF NOT EXISTS nango_records.record_counts (
            environment_id INTEGER NOT NULL,
            connection_id INTEGER NOT NULL,
            model VARCHAR(255) NOT NULL,
            count BIGINT NOT NULL DEFAULT 0,
            size_bytes BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (connection_id, model)
        );
    `);
    console.log('records schema ready');

    // Scheduler schema (packages/scheduler/lib/db/migrations).
    await db.raw(`
        DO $$ BEGIN
            CREATE TYPE task_states AS ENUM
                ('CREATED', 'STARTED', 'SUCCEEDED', 'FAILED', 'EXPIRED', 'CANCELLED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await db.raw(`
        DO $$ BEGIN
            CREATE TYPE schedule_states AS ENUM
                ('PAUSED', 'STARTED', 'DELETED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    `);
    await db.raw(`
        CREATE TABLE IF NOT EXISTS tasks (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            payload JSON NOT NULL,
            group_key VARCHAR(255) NOT NULL,
            group_max_concurrency INT NOT NULL DEFAULT 0,
            retry_max INT NOT NULL DEFAULT 0,
            retry_count INT NOT NULL DEFAULT 0,
            retry_key UUID,
            owner_key VARCHAR(64),
            starts_after TIMESTAMPTZ NOT NULL,
            created_to_started_timeout_secs INT NOT NULL,
            started_to_completed_timeout_secs INT NOT NULL,
            heartbeat_timeout_secs INT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            state task_states NOT NULL,
            last_state_transition_at TIMESTAMPTZ NOT NULL,
            last_heartbeat_at TIMESTAMPTZ NOT NULL,
            output JSON NULL,
            terminated BOOLEAN,
            schedule_id UUID
        );
    `);
    await db.raw(`
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_name ON tasks (name);
        CREATE INDEX IF NOT EXISTS idx_tasks_group_created ON tasks (group_key) WHERE state = 'CREATED';
        CREATE INDEX IF NOT EXISTS idx_tasks_created_starts ON tasks (starts_after) WHERE state = 'CREATED';
        CREATE INDEX IF NOT EXISTS idx_tasks_retry_key ON tasks (retry_key);
    `);
    await db.raw(`
        CREATE TABLE IF NOT EXISTS schedules (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            state schedule_states NOT NULL,
            starts_at TIMESTAMPTZ NOT NULL,
            frequency INTERVAL NOT NULL,
            payload JSON NOT NULL,
            group_key VARCHAR(255) NOT NULL,
            retry_max INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            deleted_at TIMESTAMPTZ NULL,
            last_scheduled_task_id UUID NULL,
            last_scheduled_task_state task_states DEFAULT NULL,
            next_execution_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    `);
    await db.raw(`
        CREATE UNIQUE INDEX IF NOT EXISTS idx_schedules_name ON schedules (name);
        CREATE INDEX IF NOT EXISTS idx_schedules_ready ON schedules (next_execution_at) WHERE state = 'STARTED';
    `);
    console.log('scheduler schema ready');
} catch (err) {
    console.error('migration failed:', err.message || err);
    process.exitCode = 1;
} finally {
    await db.destroy();
}