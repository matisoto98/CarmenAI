// Orquestación supervisor/agentes (contracts/agent-task, delegation-plan, agent-result,
// agent-card y conversation-turn, 6.12 y 5.14.3).

import type {
  AgentId,
  ApprovalId,
  CallId,
  ConversationId,
  DelegatedIdentityRef,
  DelegatingMode,
  DelegationPlanId,
  DottedId,
  Effect,
  Instant,
  Locale,
  McpServerId,
  Money,
  PrincipalId,
  ProviderId,
  Purpose,
  ResponseMode,
  RunId,
  SchemaVersion,
  SystemId,
  TaskId,
  Text,
  TurnId,
} from "./common";
import type { Evidence, EvidenceReference, GroundingResult } from "./evidence";
import type { Versioned } from "./keys";

export const EXPECTS = ["facts", "passages", "media", "mixed"] as const;
export type Expects = (typeof EXPECTS)[number];

export interface TaskBudgets {
  readonly max_wall_ms: number;
  readonly max_tokens: number;
  readonly max_cost_eur: Money;
}

/** Lo que Carmen encarga a un agente: autocontenido, sin herramientas ni credenciales. */
export interface AgentTask {
  readonly task_id: TaskId;
  readonly agent_id: AgentId;
  readonly objective: string;
  readonly entities: Readonly<Record<string, Text>>;
  readonly expects: Expects;
  readonly locale: Locale;
  readonly budgets: TaskBudgets;
  readonly delegated_identity: DelegatedIdentityRef;
  readonly depends_on?: readonly TaskId[];
  readonly optional?: boolean;
}

export const COMPOSITION_KINDS = ["single", "blocks", "join"] as const;
export type CompositionKind = (typeof COMPOSITION_KINDS)[number];

export interface Composition {
  readonly kind: CompositionKind;
  readonly tasks: readonly TaskId[];
  readonly entity?: Text;
  readonly canonical_id?: Text;
  readonly on_missing?: "hueco_explicito";
}

export interface Budgets {
  readonly max_wall_ms: number;
  readonly max_tokens: number;
  readonly max_cost_eur: Money;
  readonly max_agents: number;
}

export interface DelegationPlan {
  readonly schema_version: SchemaVersion;
  readonly plan_id: DelegationPlanId;
  readonly turn_id: TurnId;
  readonly response_mode: DelegatingMode;
  readonly principal_id: PrincipalId;
  readonly policy_version: Text;
  readonly tasks: readonly AgentTask[];
  readonly composition: Composition;
  readonly budgets: Budgets;
  readonly requires_human_approval?: boolean;
}

export const AGENT_RESULT_STATUSES = ["ok", "partial", "no_data", "denied", "failed"] as const;
export type AgentResultStatus = (typeof AGENT_RESULT_STATUSES)[number];

export const NEED_DELEGATION_REASONS = [
  "needs_procedure",
  "needs_complementary_data",
  "needs_legal_review",
  "out_of_scope",
] as const;
export type NeedDelegationReason = (typeof NEED_DELEGATION_REASONS)[number];

export const AGENT_DOMAINS = [
  "monitorizacion",
  "economico",
  "documental",
  "soporte",
  "legal",
  "contractual",
] as const;
export type AgentDomain = (typeof AGENT_DOMAINS)[number];

export const AGENT_ACTIONS = ["discover", "describe", "invoke"] as const;
export type AgentAction = (typeof AGENT_ACTIONS)[number];

export const PLATFORM_ACTIONS = [
  "carmen.admin",
  "agents.manage",
  "glossary.write",
  "policy.write",
  "kpis.read",
  "topics.read",
  "audit.read",
] as const;
export type PlatformAction = (typeof PLATFORM_ACTIONS)[number];

export const APPROVAL_STATUSES = ["pending", "approved", "rejected", "expired"] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

export const IMPACTS = ["high", "critical"] as const;
export type Impact = (typeof IMPACTS)[number];

export interface AgentWarning {
  readonly code: Text;
  readonly message: Text;
}

/** El agente pide ayuda por dominio; nunca nombra a otro agente. */
export interface NeedDelegation {
  readonly reason: NeedDelegationReason;
  readonly suggested_domain: AgentDomain;
  readonly context_ref: string;
  readonly rationale: string;
}

/** Texto de un modelo: nunca es evidencia ni respalda una cifra. */
export interface ModelOutput {
  readonly provider: ProviderId;
  readonly model: Text;
  readonly model_version: Text;
  readonly purpose: Purpose;
  readonly text: string;
  readonly tokens_in: number;
  readonly tokens_out: number;
  readonly cost_eur: Money;
  readonly produced_at: Instant;
}

export interface ToolCallTrace {
  readonly call_id: CallId;
  readonly system_id: SystemId;
  readonly tool_name: Text;
  readonly ms: number;
  readonly ok: boolean;
}

export interface ExternalCallTrace {
  readonly policy_id: Text;
  readonly at: Instant;
  readonly provider?: ProviderId;
  readonly domain?: Text;
  readonly redactions?: readonly Text[];
  readonly tokens?: number;
  readonly cost_eur?: Money;
}

export interface PolicyDecision {
  readonly turn_id: TurnId;
  readonly principal_id: PrincipalId;
  readonly action: AgentAction | PlatformAction;
  readonly decision: Effect;
  readonly reason_code: Text;
  readonly policy_version: Text;
  readonly decided_at: Instant;
  /** Obligatorio en las acciones sobre agentes; ausente en las de plataforma. */
  readonly agent_id?: AgentId;
  readonly scopes?: readonly DottedId[];
}

export interface ApprovalRecord {
  readonly request_id: ApprovalId;
  readonly status: ApprovalStatus;
  readonly evidence_refs?: readonly EvidenceReference[];
  readonly decided_by?: PrincipalId;
  readonly decided_at?: Instant;
}

export interface AgentRun {
  readonly run_id: RunId;
  readonly agent_id: AgentId;
  readonly started_at: Instant;
  readonly ended_at: Instant;
  readonly tokens_in?: number;
  readonly tokens_out?: number;
  readonly cost_eur?: Money;
  readonly tool_calls?: readonly ToolCallTrace[];
  readonly external?: readonly ExternalCallTrace[];
  readonly policy_checks?: readonly PolicyDecision[];
  readonly approvals?: readonly ApprovalRecord[];
}

export interface AgentResult {
  readonly task_id: TaskId;
  readonly agent_id: AgentId;
  readonly agent_version: Text;
  readonly status: AgentResultStatus;
  readonly run: AgentRun;
  /** Con ok o partial, al menos una; con el resto, ninguna. */
  readonly evidence?: readonly Evidence[];
  readonly warnings?: readonly AgentWarning[];
  readonly need_delegation?: NeedDelegation | null;
  readonly model_outputs?: readonly ModelOutput[];
}

export const LIFECYCLE_STATES = ["DISCOVERED", "COMPATIBLE", "CERTIFIED", "QUARANTINED"] as const;
export type LifecycleState = (typeof LIFECYCLE_STATES)[number];

export const VISIBILITIES = [
  "PUBLIC_CATALOG",
  "DISCOVERABLE",
  "AUTHORIZED_ONLY",
  "HIDDEN",
] as const;
export type Visibility = (typeof VISIBILITIES)[number];

export const CONNECTIVITIES = ["INTERNAL_ONLY", "EXTERNAL_GOVERNED", "HYBRID_GOVERNED"] as const;
export type Connectivity = (typeof CONNECTIVITIES)[number];

export interface AgentSlo {
  readonly p95_ms: number;
  readonly availability: number;
}

export interface AgentBudgets {
  readonly max_tokens_per_run: number;
  readonly max_cost_per_run_eur: Money;
  readonly max_wall_ms: number;
}

export interface AgentCard {
  readonly agent_id: AgentId;
  readonly version: string;
  readonly display_name: Text;
  readonly owner: Text;
  readonly status: LifecycleState;
  readonly connectivity: Connectivity;
  readonly visibility: Visibility;
  readonly safe_description: Text;
  readonly public_capabilities: readonly Text[];
  readonly routing_description: Text;
  /** Solo lectura en v1. */
  readonly allowed_actions: readonly "read"[];
  readonly scopes: readonly DottedId[];
  readonly entities_exposed: readonly Text[];
  readonly mcp_bindings: readonly McpServerId[];
  readonly provider_bindings: readonly ProviderId[];
  readonly slo: AgentSlo;
  readonly budgets: AgentBudgets;
  readonly golden_set: Text;
  readonly kill_switch: boolean;
}

export const TURN_STATUSES = [
  "completed",
  "partial",
  "rejected",
  "failed",
  "cancelled",
  "no_data",
] as const;
export type TurnStatus = (typeof TURN_STATUSES)[number];

export interface TokenUsage {
  readonly tokens_in?: number;
  readonly tokens_out?: number;
}

export interface ConversationTurn {
  readonly turn_id: TurnId;
  readonly conversation_id: ConversationId;
  readonly principal_id: PrincipalId;
  readonly question: Text;
  readonly response_mode: ResponseMode;
  readonly policy_version: Text;
  readonly status: TurnStatus;
  readonly agents_used?: readonly AgentId[];
  readonly delegation_plan?: DelegationPlan | null;
  readonly runs?: readonly AgentRun[];
  readonly evidence?: readonly Evidence[];
  readonly grounding?: GroundingResult | null;
  readonly approvals?: readonly ApprovalRecord[];
  readonly tokens?: TokenUsage;
  readonly cost_eur?: Money;
  readonly latency_ms?: number;
  readonly missing_agents?: readonly AgentId[];
  readonly redelegations?: number;
}

/** Documentos raíz: el objeto con su versión de esquema (6.12.9). */
export type AgentTaskDocument = Versioned<AgentTask>;
export type AgentResultDocument = Versioned<AgentResult>;
export type AgentCardDocument = Versioned<AgentCard>;
export type ConversationTurnDocument = Versioned<ConversationTurn>;
