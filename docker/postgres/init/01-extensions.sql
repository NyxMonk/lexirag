-- Runs once, when the data volume is first initialised.
-- Installing into template1 means every database created later (e.g. the test
-- database) also has pgvector. Alembic migration 0001 enables it idempotently too.
\connect template1
CREATE EXTENSION IF NOT EXISTS vector;

\connect :"POSTGRES_DB"
CREATE EXTENSION IF NOT EXISTS vector;
