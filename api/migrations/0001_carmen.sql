-- 0001_carmen.sql — esquema propio de Carmen (7.3, 7.8.4 y 7.9.7). Requiere la extensión vector.
-- No se edita nunca: un cambio es una migración nueva. El ejecutor guarda su checksum y
-- `python -m carmen.migrations --check` falla si el fichero cambia después de aplicado.
--
-- Concreciones (ADR-048): los identificadores del dominio son texto con prefijo (cnv_, msg_,
-- mem_, gap_, top_, trn_) y se guardan tal cual, con la misma restricción de patrón que el
-- dominio. Las filas internas sin identificador de dominio (tool_calls, evidence_facts,
-- grounding_claims, glossary_history, policy_decisions) siguen siendo uuid.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS carmen;

-- Enumeraciones: las mismas que el dominio (una prueba verifica que no divergen).
CREATE TYPE carmen.msg_status AS ENUM
  ('completed', 'partial', 'rejected', 'failed', 'cancelled', 'no_data');
CREATE TYPE carmen.locale AS ENUM ('es', 'en', 'pt');
CREATE TYPE carmen.role AS ENUM ('ADMIN', 'MANAGER', 'OPERATOR', 'AUDITOR');

-- --- Conversación (agregado; unidad de trabajo 1) -------------------------------------------

CREATE TABLE carmen.conversations (
  id text PRIMARY KEY CHECK (id ~ '^cnv_[a-z0-9]{4,32}$'),
  user_id text NOT NULL,
  locale carmen.locale NOT NULL DEFAULT 'es',
  channel text NOT NULL DEFAULT 'web',
  title text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT ck_conv_channel CHECK (channel <> '')
);
CREATE INDEX ix_conv_user_updated ON carmen.conversations (user_id, updated_at DESC);

-- TEMAS (7.8.4): se crean antes que messages, que los referencia.
CREATE TABLE carmen.topics (
  id text PRIMARY KEY CHECK (id ~ '^top_[a-z0-9]{4,32}$'),
  label text NOT NULL,
  centroid vector(1024),
  asked integer NOT NULL DEFAULT 0 CHECK (asked >= 0),
  resolved integer NOT NULL DEFAULT 0 CHECK (resolved >= 0),
  unresolved integer NOT NULL DEFAULT 0 CHECK (unresolved >= 0),
  systems text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'observando'
    CHECK (status IN ('observando', 'planificado', 'fuera_alcance', 'cubierto')),
  first_seen timestamptz NOT NULL,
  last_seen timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT ck_topic_counts CHECK (resolved + unresolved <= asked)
);
CREATE INDEX ix_topics_demand ON carmen.topics (asked DESC);
CREATE INDEX ix_topics_gap ON carmen.topics (unresolved DESC) WHERE unresolved > 0;

CREATE TABLE carmen.messages (
  id text PRIMARY KEY CHECK (id ~ '^msg_[a-z0-9]{4,32}$'),
  conversation_id text NOT NULL REFERENCES carmen.conversations (id) ON DELETE CASCADE,
  seq integer NOT NULL,
  role text NOT NULL CHECK (role IN ('user', 'assistant')),
  content text NOT NULL,
  locale carmen.locale,
  intent text,
  status carmen.msg_status NOT NULL,
  partial boolean NOT NULL DEFAULT false,
  missing_systems text[] NOT NULL DEFAULT '{}',
  -- ROL OBSERVADO ≠ AUTORIZACIÓN EFECTIVA: se guardan por separado
  observed_role carmen.role,
  authz_denied integer NOT NULL DEFAULT 0,
  -- Trazabilidad de POR QUÉ salió así
  plan_id text,
  plan_schema_version text,
  round integer NOT NULL DEFAULT 0,
  repairs integer NOT NULL DEFAULT 0,
  model_id text,
  model_revision text,
  prompt_hash text,
  catalog_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  contract_version text,
  grounding_ok boolean,
  grounding_unsupported integer NOT NULL DEFAULT 0,
  tokens_in integer,
  tokens_out integer,
  latency_ms integer,
  correlation_id text NOT NULL,
  created_at timestamptz NOT NULL,
  topic_id text REFERENCES carmen.topics (id),
  CONSTRAINT uq_msg_seq UNIQUE (conversation_id, seq)
);
CREATE INDEX ix_msg_conv ON carmen.messages (conversation_id, seq);
CREATE INDEX ix_msg_corr ON carmen.messages (correlation_id);
CREATE INDEX ix_msg_bad_ground ON carmen.messages (created_at DESC) WHERE grounding_ok = false;
CREATE INDEX ix_msg_status ON carmen.messages (status, created_at DESC)
  WHERE status <> 'completed';
CREATE INDEX ix_msg_topic ON carmen.messages (topic_id, created_at DESC);

CREATE TABLE carmen.tool_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  seq integer NOT NULL,
  step_id text NOT NULL,
  call_id text NOT NULL,
  system_id text NOT NULL,
  tool_name text NOT NULL,
  arguments jsonb NOT NULL,
  ok boolean NOT NULL,
  error_code text,
  facts_count integer NOT NULL DEFAULT 0,
  partial boolean NOT NULL DEFAULT false,
  repaired boolean NOT NULL DEFAULT false,
  ms integer,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_tc UNIQUE (message_id, seq),
  CONSTRAINT ck_tc_error CHECK (ok = (error_code IS NULL))
);
CREATE INDEX ix_tc_call ON carmen.tool_calls (call_id);

-- EVIDENCIA: lo que permite que el anclaje enlace cifra con hecho (corrección C4).
CREATE TABLE carmen.evidence_facts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  tool_call_id uuid NOT NULL REFERENCES carmen.tool_calls (id) ON DELETE CASCADE,
  fact_key text NOT NULL,
  label text NOT NULL,
  value_num numeric,
  value_text text,
  unit text,
  entity_type text,
  entity_id text,
  dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
  period jsonb,
  CONSTRAINT uq_fact UNIQUE (tool_call_id, fact_key),
  CONSTRAINT ck_fact_one_value CHECK (value_num IS NULL OR value_text IS NULL)
);
CREATE INDEX ix_fact_msg ON carmen.evidence_facts (message_id);

CREATE TABLE carmen.grounding_claims (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  raw_value text NOT NULL,
  normalized numeric,
  verdict text NOT NULL CHECK (verdict IN ('supported', 'unsupported', 'whitelisted')),
  fact_id uuid REFERENCES carmen.evidence_facts (id),
  reason text
);
CREATE INDEX ix_claim_msg ON carmen.grounding_claims (message_id);

CREATE TABLE carmen.feedback (
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  user_id text NOT NULL,
  rating smallint NOT NULL CHECK (rating IN (-1, 1)),
  comment text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (message_id, user_id) -- IDEMPOTENTE por diseño
);

-- --- Memoria de planes: guarda el PLAN, jamás resultados operativos -------------------------

CREATE TABLE carmen.query_memory (
  id text PRIMARY KEY CHECK (id ~ '^mem_[a-z0-9]{4,32}$'),
  question_norm text NOT NULL,
  question text NOT NULL,
  embedding vector(1024) NOT NULL, -- FIJO (C2, ADR-014)
  plan jsonb NOT NULL,
  plan_schema_version text NOT NULL,
  systems text[] NOT NULL,
  locale carmen.locale NOT NULL,
  hits integer NOT NULL DEFAULT 1,
  validated_by text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_mem_question UNIQUE (question_norm, locale)
);
CREATE INDEX ix_mem_vec ON carmen.query_memory
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ix_mem_active ON carmen.query_memory (active) WHERE active;

-- --- Lagunas (unidad de trabajo 2) ----------------------------------------------------------

CREATE TABLE carmen.gaps (
  id text PRIMARY KEY CHECK (id ~ '^gap_[a-z0-9]{4,32}$'),
  question_norm text NOT NULL,
  question text NOT NULL,
  embedding vector(1024) NOT NULL,
  locale carmen.locale NOT NULL,
  reason text NOT NULL,
  cluster_id uuid,
  cluster_name text,
  occurrences integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  first_seen timestamptz NOT NULL,
  last_seen timestamptz NOT NULL,
  CONSTRAINT uq_gap UNIQUE (question_norm, locale) -- upsert atómico
);
CREATE INDEX ix_gap_vec ON carmen.gaps
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX ix_gap_open ON carmen.gaps (status, occurrences DESC);

-- --- Corpus organizativo y brief ------------------------------------------------------------

CREATE TABLE carmen.knowledge_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL,
  title text NOT NULL,
  chunk_ix integer NOT NULL,
  content text NOT NULL,
  embedding vector(1024) NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_kc UNIQUE (source, chunk_ix)
);
CREATE INDEX ix_kc_vec ON carmen.knowledge_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE carmen.situation_brief (
  id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  payload jsonb NOT NULL,
  generated_at timestamptz NOT NULL
);

-- --- Glosario editable con historial (7.8.4) ------------------------------------------------

CREATE TABLE carmen.glossary_terms (
  term text PRIMARY KEY,
  display text NOT NULL,
  definition text NOT NULL,
  aliases text[] NOT NULL DEFAULT '{}',
  canonical boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  source text NOT NULL DEFAULT 'seed' CHECK (source IN ('seed', 'admin')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_by text NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE carmen.glossary_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq bigint GENERATED ALWAYS AS IDENTITY, -- orden estable dentro del mismo instante
  term text NOT NULL,
  action text NOT NULL CHECK (action IN ('create', 'update', 'deactivate')),
  before jsonb,
  after jsonb,
  actor text NOT NULL,
  at timestamptz NOT NULL
);
CREATE INDEX ix_gh_term ON carmen.glossary_history (term, at DESC);

-- --- Política (7.9.7) -----------------------------------------------------------------------

CREATE TABLE carmen.principals (
  id text PRIMARY KEY,
  directory_ref text NOT NULL UNIQUE,
  display_name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE carmen.roles (
  id text PRIMARY KEY,
  name text NOT NULL,
  platform_actions text[] NOT NULL DEFAULT '{}',
  version text NOT NULL
);

CREATE TABLE carmen.role_assignments (
  principal_id text NOT NULL REFERENCES carmen.principals (id),
  role_id text NOT NULL REFERENCES carmen.roles (id),
  source text NOT NULL CHECK (source IN ('directory', 'manual')),
  granted_at timestamptz NOT NULL,
  PRIMARY KEY (principal_id, role_id)
);

CREATE TABLE carmen.role_agent_grants (
  role_id text NOT NULL REFERENCES carmen.roles (id),
  agent_id text NOT NULL,
  actions text[] NOT NULL CHECK (
    cardinality(actions) > 0 AND actions <@ ARRAY['discover', 'describe', 'invoke']::text[]
  ),
  scopes text[] NOT NULL DEFAULT '{}',
  effect text NOT NULL CHECK (effect IN ('allow', 'deny')),
  reason text,
  CONSTRAINT ck_deny_reason CHECK (effect <> 'deny' OR (reason IS NOT NULL AND btrim(reason) <> '')),
  PRIMARY KEY (role_id, agent_id)
);

CREATE TABLE carmen.policy_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  turn_id text NOT NULL,
  principal_id text NOT NULL,
  agent_id text,
  action text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('allow', 'deny')),
  reason_code text NOT NULL,
  policy_version text NOT NULL,
  decided_at timestamptz NOT NULL
);
CREATE INDEX ix_pd_turn ON carmen.policy_decisions (turn_id);
CREATE INDEX ix_pd_deny ON carmen.policy_decisions (decided_at DESC) WHERE decision = 'deny';

-- NOTA: las tablas de evaluación NO van aquí. El arnés es una herramienta, no parte del
-- runtime, y tiene su propio esquema en eval/ (ADR-020).
