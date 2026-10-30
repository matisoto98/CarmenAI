// Tipos compartidos de contracts/common.schema.json.

export const SCHEMA_VERSION = "1.0";
export type SchemaVersion = typeof SCHEMA_VERSION;

export type AgentId = `agent.${string}`;
export type SystemId = string;
export type StepId = `s${number}`;
export type TaskId = `t${number}`;
export type PlanId = `pln_${string}`;
export type DelegationPlanId = `dpl_${string}`;
export type TurnId = `trn_${string}`;
export type ConversationId = `cnv_${string}`;
export type PrincipalId = `usr_${string}`;
export type RunId = `run_${string}`;
export type ApprovalId = `apr_${string}`;
export type CallId = `cal_${string}`;
export type CorrelationId = `cor_${string}`;
export type LocalId = string;
export type DottedId = string;
export type ProviderId = `provider.${string}`;
export type McpServerId = `mcp.${string}`;
export type DelegatedIdentityRef = `idr_${string}`;
/** Instante ISO 8601 con zona explícita (Z u offset). */
export type Instant = string;
/** Texto no vacío. */
export type Text = string;
/** Importe en euros, nunca negativo. */
export type Money = number;

export const LOCALES = ["es", "en", "pt"] as const;
export type Locale = (typeof LOCALES)[number];

export const ROLES = ["ADMIN", "MANAGER", "OPERATOR", "AUDITOR"] as const;
export type Role = (typeof ROLES)[number];

export const EFFECTS = ["allow", "deny"] as const;
export type Effect = (typeof EFFECTS)[number];

export const PURPOSES = ["routing", "narration", "analysis"] as const;
export type Purpose = (typeof PURPOSES)[number];

export const DATA_CLASSES = ["PUBLICO", "INTERNO", "CONFIDENCIAL"] as const;
export type DataClass = (typeof DATA_CLASSES)[number];

export const RESPONSE_MODES = [
  "SUPERVISOR_DIRECT",
  "DELEGATE_SINGLE",
  "DELEGATE_MULTI",
  "CLARIFY",
  "REFUSE",
] as const;
export type ResponseMode = (typeof RESPONSE_MODES)[number];

export const DELEGATING_MODES = ["DELEGATE_SINGLE", "DELEGATE_MULTI"] as const;
export type DelegatingMode = (typeof DELEGATING_MODES)[number];

export const DIRECT_MODES = ["SUPERVISOR_DIRECT", "CLARIFY", "REFUSE"] as const;
export type DirectMode = (typeof DIRECT_MODES)[number];
