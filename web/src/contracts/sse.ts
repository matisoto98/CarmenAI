// Eventos SSE 1.1 (contracts/sse-events.schema.json, 6.5): unión discriminada por event_type.

import type {
  AgentId,
  ApprovalId,
  CallId,
  ConversationId,
  CorrelationId,
  DelegationPlanId,
  Instant,
  LocalId,
  ResponseMode,
  StepId,
  SystemId,
  TaskId,
  Text,
} from "./common";
import type { AgentResultStatus, Impact, TurnStatus } from "./orchestration";

export const SSE_SCHEMA_VERSION = "1.1";

export const SSE_EVENT_TYPES = [
  "mode",
  "stage",
  "delegation",
  "tool_call",
  "tool_result",
  "agent_result",
  "approval_required",
  "delta",
  "grounding",
  "warning",
  "error",
  "done",
] as const;
export type SseEventType = (typeof SSE_EVENT_TYPES)[number];

export const DELTA_SECTIONS = ["data", "reading"] as const;
export type DeltaSection = (typeof DELTA_SECTIONS)[number];

export interface ModePayload {
  readonly response_mode: ResponseMode;
}

export interface StagePayload {
  readonly stage: Text;
  readonly detail?: string;
  readonly step_id?: StepId;
}

export interface DelegationPayload {
  readonly task_id: TaskId;
  readonly agent_id: AgentId;
  readonly depends_on: readonly TaskId[];
}

export interface ToolCallPayload {
  readonly agent_id: AgentId;
  readonly task_id: TaskId;
  readonly step_id: StepId;
  readonly call_id: CallId;
  readonly system_id: SystemId;
  readonly tool_name: string;
  readonly arguments_digest: string;
}

export interface ToolResultPayload {
  readonly agent_id: AgentId;
  readonly task_id: TaskId;
  readonly step_id: StepId;
  readonly call_id: CallId;
  readonly ok: boolean;
  readonly facts_count: number;
  readonly ms: number;
  readonly partial: boolean;
}

export interface AgentResultPayload {
  readonly task_id: TaskId;
  readonly agent_id: AgentId;
  readonly status: AgentResultStatus;
  readonly evidence_count: number;
  readonly ms: number;
}

export interface ApprovalRequiredPayload {
  readonly request_id: ApprovalId;
  readonly agent_id: AgentId;
  readonly summary: Text;
  readonly impact: Impact;
  readonly expires_at: Instant;
}

export interface DeltaPayload {
  readonly section: DeltaSection;
  readonly text: string;
}

export interface UnsupportedClaim {
  readonly claim_id: LocalId;
  readonly raw_value: Text;
}

export interface GroundingPayload {
  readonly ok: boolean;
  readonly checked: number;
  readonly unsupported: readonly UnsupportedClaim[];
}

export interface WarningPayload {
  readonly code: Text;
  readonly message: Text;
  readonly system_id?: SystemId;
  readonly agent_id?: AgentId;
}

export interface ErrorPayload {
  readonly code: Text;
  readonly message: Text;
  readonly recoverable: boolean;
}

export interface DonePayload {
  readonly message_id: Text;
  readonly conversation_id: ConversationId;
  readonly status: TurnStatus;
  readonly partial: boolean;
  readonly missing_systems: readonly SystemId[];
  readonly grounding_ok: boolean | null;
  readonly plan_id: DelegationPlanId | null;
  readonly round: number;
  readonly repairs: number;
  readonly latency_ms: number;
  readonly model: Text;
  readonly catalog_versions: Readonly<Record<SystemId, string>>;
  readonly response_mode: ResponseMode;
  readonly agents_used: readonly AgentId[];
  readonly missing_agents: readonly AgentId[];
}

/** Carga de cada tipo de evento. Debe tener exactamente una entrada por SseEventType. */
export interface SsePayloads {
  readonly mode: ModePayload;
  readonly stage: StagePayload;
  readonly delegation: DelegationPayload;
  readonly tool_call: ToolCallPayload;
  readonly tool_result: ToolResultPayload;
  readonly agent_result: AgentResultPayload;
  readonly approval_required: ApprovalRequiredPayload;
  readonly delta: DeltaPayload;
  readonly grounding: GroundingPayload;
  readonly warning: WarningPayload;
  readonly error: ErrorPayload;
  readonly done: DonePayload;
}

export interface SseEnvelope<K extends SseEventType> {
  readonly schema_version: typeof SSE_SCHEMA_VERSION;
  readonly event_id: `evt_${string}`;
  readonly event_type: K;
  readonly correlation_id: CorrelationId;
  readonly sequence: number;
  readonly timestamp: Instant;
  readonly payload: SsePayloads[K];
}

export type SseEvent = { [K in SseEventType]: SseEnvelope<K> }[SseEventType];
