-- 0002_orquestacion.sql — turno, agentes, aprobaciones, egreso y ciclo de vida (7.3.1).
-- La 0001 no se edita: esta migración amplía sus tablas. Enumeraciones iguales a las del dominio
-- (una prueba lo verifica).
--
-- Concreciones (ADR-049): los identificadores del dominio son texto con prefijo, como en la 0001
-- (trn_, run_, apr_). Las columnas ord fijan el orden en que el turno los contiene, para que el
-- turno se reconstruya igual desde la base. La evidencia de pasajes y adjuntos y los campos de
-- hecho y de anclaje que la 0001 no tenía se añaden aquí.

CREATE TYPE carmen.response_mode AS ENUM
  ('SUPERVISOR_DIRECT', 'DELEGATE_SINGLE', 'DELEGATE_MULTI', 'CLARIFY', 'REFUSE');
CREATE TYPE carmen.agent_state AS ENUM ('DISCOVERED', 'COMPATIBLE', 'CERTIFIED', 'QUARANTINED');
CREATE TYPE carmen.agent_result_status AS ENUM ('ok', 'partial', 'no_data', 'denied', 'failed');
CREATE TYPE carmen.approval_status AS ENUM ('pending', 'approved', 'rejected', 'expired');

-- --- El mensaje del asistente ES el registro del turno (6.12.8) -----------------------------

ALTER TABLE carmen.messages
  ADD COLUMN turn_id text UNIQUE CHECK (turn_id ~ '^trn_[a-z0-9]{4,32}$'),
  ADD COLUMN response_mode carmen.response_mode,
  ADD COLUMN policy_version text,
  ADD COLUMN delegation_plan jsonb,
  ADD COLUMN agents_used text[] NOT NULL DEFAULT '{}',
  ADD COLUMN missing_agents text[] NOT NULL DEFAULT '{}',
  ADD COLUMN redelegations integer NOT NULL DEFAULT 0,
  ADD COLUMN cost_eur numeric(12, 4) NOT NULL DEFAULT 0,
  ADD CONSTRAINT ck_direct_sin_agentes CHECK (
    response_mode IS NULL
    OR response_mode IN ('DELEGATE_SINGLE', 'DELEGATE_MULTI')
    OR (cardinality(agents_used) = 0 AND delegation_plan IS NULL)
  ),
  ADD CONSTRAINT ck_redelegations CHECK (redelegations BETWEEN 0 AND 1),
  ADD CONSTRAINT ck_turn_fields CHECK (
    (turn_id IS NULL) = (response_mode IS NULL) AND (turn_id IS NULL) = (policy_version IS NULL)
  ),
  ADD CONSTRAINT ck_cost CHECK (cost_eur >= 0);

-- --- Ejecuciones de agente ------------------------------------------------------------------

CREATE TABLE carmen.agent_runs (
  id text PRIMARY KEY CHECK (id ~ '^run_[a-z0-9]{4,32}$'),
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  ord integer NOT NULL,
  task_id text NOT NULL,
  agent_id text NOT NULL,
  agent_version text NOT NULL,
  status carmen.agent_result_status NOT NULL,
  redelegated boolean NOT NULL DEFAULT false,
  started_at timestamptz NOT NULL,
  ended_at timestamptz NOT NULL,
  tokens_in integer NOT NULL DEFAULT 0 CHECK (tokens_in >= 0),
  tokens_out integer NOT NULL DEFAULT 0 CHECK (tokens_out >= 0),
  cost_eur numeric(12, 4) NOT NULL DEFAULT 0 CHECK (cost_eur >= 0),
  CONSTRAINT uq_run_task UNIQUE (message_id, task_id),
  CONSTRAINT uq_run_ord UNIQUE (message_id, ord),
  CONSTRAINT ck_run_times CHECK (ended_at >= started_at)
);
CREATE INDEX ix_runs_agent ON carmen.agent_runs (agent_id, started_at DESC);

-- Cada llamada a herramienta pertenece a la ejecución de un agente
ALTER TABLE carmen.tool_calls
  ADD COLUMN agent_run_id text REFERENCES carmen.agent_runs (id) ON DELETE CASCADE,
  ADD COLUMN run_ord integer,
  ADD CONSTRAINT ck_tc_run CHECK ((agent_run_id IS NULL) = (run_ord IS NULL));
CREATE INDEX ix_tc_run ON carmen.tool_calls (agent_run_id, run_ord);

-- Decisiones de política tomadas dentro de una ejecución (policy_checks del AgentRun)
ALTER TABLE carmen.policy_decisions
  ADD COLUMN agent_run_id text REFERENCES carmen.agent_runs (id) ON DELETE CASCADE,
  ADD COLUMN run_ord integer,
  ADD COLUMN scopes text[] NOT NULL DEFAULT '{}',
  ADD CONSTRAINT ck_pd_run CHECK ((agent_run_id IS NULL) = (run_ord IS NULL)),
  ADD CONSTRAINT ck_pd_deny_scopes CHECK (decision = 'allow' OR cardinality(scopes) = 0);
CREATE INDEX ix_pd_run ON carmen.policy_decisions (agent_run_id, run_ord);

-- --- Evidencia completa del turno (6.3, 6.9.2) ----------------------------------------------

ALTER TABLE carmen.evidence_facts
  ADD COLUMN ord integer,
  ADD COLUMN system_id text,
  ADD COLUMN value_kind text CHECK (value_kind IN ('int', 'decimal', 'str', 'bool', 'null')),
  ADD COLUMN metric text,
  ADD COLUMN entity_name text,
  ADD COLUMN provenance_tool text,
  ADD COLUMN provenance_catalog_version text,
  ADD COLUMN provenance_generated_at timestamptz;

CREATE TABLE carmen.evidence_passages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  tool_call_id uuid NOT NULL REFERENCES carmen.tool_calls (id) ON DELETE CASCADE,
  ord integer NOT NULL,
  passage_key text NOT NULL,
  system_id text NOT NULL,
  document_id text NOT NULL,
  title text NOT NULL,
  body text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('reference', 'procedure', 'warning', 'definition')),
  relevance double precision NOT NULL CHECK (relevance BETWEEN 0 AND 1),
  section text,
  anchor text,
  doc_version text,
  updated_at timestamptz,
  url text,
  CONSTRAINT uq_passage UNIQUE (tool_call_id, passage_key),
  CONSTRAINT ck_procedure_fresh CHECK (kind <> 'procedure' OR updated_at IS NOT NULL)
);
CREATE INDEX ix_passage_msg ON carmen.evidence_passages (message_id, ord);

CREATE TABLE carmen.evidence_media (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id text NOT NULL REFERENCES carmen.messages (id) ON DELETE CASCADE,
  tool_call_id uuid NOT NULL REFERENCES carmen.tool_calls (id) ON DELETE CASCADE,
  ord integer NOT NULL,
  media_key text NOT NULL,
  system_id text NOT NULL,
  document_id text NOT NULL,
  mime text NOT NULL,
  caption text NOT NULL,
  uri text NOT NULL CHECK (lower(btrim(uri)) NOT LIKE 'data:%'),
  bytes bigint CHECK (bytes >= 0),
  anchor text,
  CONSTRAINT uq_media UNIQUE (tool_call_id, media_key)
);
CREATE INDEX ix_media_msg ON carmen.evidence_media (message_id, ord);

ALTER TABLE carmen.grounding_claims
  ADD COLUMN ord integer,
  ADD COLUMN claim_key text,
  ADD COLUMN span_start integer,
  ADD COLUMN span_end integer,
  ADD CONSTRAINT ck_claim_span CHECK (span_start IS NULL OR (0 <= span_start AND span_start < span_end)),
  ADD CONSTRAINT ck_claim_support CHECK (verdict <> 'supported' OR (fact_id IS NOT NULL AND normalized IS NOT NULL));

-- --- Aprobación humana (6.12.6) -------------------------------------------------------------
-- Nace mientras el turno espera, antes de que exista el mensaje del asistente: por eso se
-- vincula al turno y no al mensaje.

CREATE TABLE carmen.approvals (
  id text PRIMARY KEY CHECK (id ~ '^apr_[a-z0-9]{4,32}$'),
  turn_id text NOT NULL CHECK (turn_id ~ '^trn_[a-z0-9]{4,32}$'),
  agent_id text NOT NULL,
  agent_run_id text REFERENCES carmen.agent_runs (id) ON DELETE SET NULL,
  action text NOT NULL,
  impact text NOT NULL CHECK (impact IN ('high', 'critical')),
  summary text NOT NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  required_role carmen.role NOT NULL,
  status carmen.approval_status NOT NULL DEFAULT 'pending',
  decided_by text,
  decided_at timestamptz,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_decided CHECK (
    (status IN ('approved', 'rejected') AND decided_by IS NOT NULL AND decided_at IS NOT NULL)
    OR (status IN ('pending', 'expired') AND decided_by IS NULL AND decided_at IS NULL)
  )
);
CREATE INDEX ix_approvals_pending ON carmen.approvals (expires_at) WHERE status = 'pending';
CREATE INDEX ix_approvals_turn ON carmen.approvals (turn_id, created_at);

-- Solo se sale de pending, y una sola vez: la base lo impide aunque un repositorio falle.
CREATE FUNCTION carmen.approvals_only_from_pending() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status AND OLD.status <> 'pending' THEN
    RAISE EXCEPTION 'approval % ya está %: solo se sale de pending', OLD.id, OLD.status
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER tg_approvals_only_from_pending BEFORE UPDATE OF status ON carmen.approvals
  FOR EACH ROW EXECUTE FUNCTION carmen.approvals_only_from_pending();

-- --- Toda llamada externa (5.15.7). En v1 esta tabla debe seguir vacía ----------------------

CREATE TABLE carmen.external_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_run_id text NOT NULL REFERENCES carmen.agent_runs (id) ON DELETE CASCADE,
  run_ord integer NOT NULL,
  provider text,
  model text,
  model_version text,
  domains text[] NOT NULL DEFAULT '{}',
  sources_accepted jsonb NOT NULL DEFAULT '[]'::jsonb,
  sources_rejected jsonb NOT NULL DEFAULT '[]'::jsonb, -- con motivo
  egress_policy_id text NOT NULL,
  export_decision jsonb, -- 6.12.7; lo rellena el egreso cuando exista (ADR-049)
  redactions text[] NOT NULL DEFAULT '{}',
  tokens integer NOT NULL DEFAULT 0 CHECK (tokens >= 0),
  cost_eur numeric(12, 4) NOT NULL DEFAULT 0 CHECK (cost_eur >= 0),
  retrieved_at timestamptz NOT NULL,
  CONSTRAINT uq_ext_ord UNIQUE (agent_run_id, run_ord),
  CONSTRAINT ck_ext_target CHECK (provider IS NOT NULL OR cardinality(domains) > 0)
);

-- --- Ciclo de vida (7.11): estado actual e historial ----------------------------------------

CREATE TABLE carmen.agent_lifecycle (
  agent_id text PRIMARY KEY,
  state carmen.agent_state NOT NULL,
  version text NOT NULL,
  owner text,
  certified_at timestamptz,
  report_ref text, -- informe de certificación
  updated_at timestamptz NOT NULL,
  CONSTRAINT ck_certified CHECK (
    state <> 'CERTIFIED'
    OR (owner IS NOT NULL AND certified_at IS NOT NULL AND report_ref IS NOT NULL)
  )
);

CREATE TABLE carmen.agent_lifecycle_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq bigint GENERATED ALWAYS AS IDENTITY, -- orden estable dentro del mismo instante
  agent_id text NOT NULL REFERENCES carmen.agent_lifecycle (agent_id),
  from_state carmen.agent_state,
  to_state carmen.agent_state NOT NULL,
  reason text NOT NULL CHECK (btrim(reason) <> ''),
  actor text NOT NULL,
  at timestamptz NOT NULL
);
CREATE INDEX ix_alh_agent ON carmen.agent_lifecycle_history (agent_id, at DESC);
