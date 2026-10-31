// Qué objeto de qué esquema corresponde a cada tipo, con su tabla de claves.
// Una tabla mal escrita no compila: KeySpec<T> exige exactamente las claves de T con su
// obligatoriedad. La prueba de alineación compara cada tabla con su esquema.

import {
  DATA_CLASSES,
  DELEGATING_MODES,
  DIRECT_MODES,
  EFFECTS,
  LOCALES,
  PURPOSES,
  RESPONSE_MODES,
  ROLES,
} from "./common";
import type * as Ev from "./evidence";
import { PASSAGE_KINDS, UNITS, VERDICTS } from "./evidence";
import type { KeySpec, Presence } from "./keys";
import type * as Mcp from "./mcp";
import { CONTENT_KINDS } from "./mcp";
import type * as Orc from "./orchestration";
import {
  AGENT_ACTIONS,
  AGENT_DOMAINS,
  AGENT_RESULT_STATUSES,
  APPROVAL_STATUSES,
  COMPOSITION_KINDS,
  CONNECTIVITIES,
  EXPECTS,
  IMPACTS,
  LIFECYCLE_STATES,
  NEED_DELEGATION_REASONS,
  PLATFORM_ACTIONS,
  TURN_STATUSES,
  VISIBILITIES,
} from "./orchestration";
import type * as Plan from "./plan";
import { FACT_FIELDS, INTENTS } from "./plan";
import type * as Reg from "./registry";
import { PROVIDER_KINDS, RELIABILITIES, SOURCE_KINDS } from "./registry";
import type { SseEnvelope, SseEventType, SsePayloads, UnsupportedClaim } from "./sse";
import { DELTA_SECTIONS, SSE_EVENT_TYPES } from "./sse";

export interface ContractSpec {
  readonly schema: string;
  readonly pointer: string;
  readonly keys: Readonly<Record<string, Presence>>;
}

function spec<T>(schema: string, pointer: string, keys: KeySpec<T>): ContractSpec {
  return { schema, pointer, keys };
}

const PLAN = "plan.schema.json";
const EVIDENCE = "evidence.schema.json";
const ENVELOPE = "mcp-envelope.schema.json";
const SERVERS = "mcp-servers.schema.json";
const TASK = "agent-task.schema.json";
const DELEGATION = "delegation-plan.schema.json";
const RESULT = "agent-result.schema.json";
const CARD = "agent-card.schema.json";
const TURN = "conversation-turn.schema.json";
const SSE = "sse-events.schema.json";
const R = "registry/";

export const CONTRACT_SPECS: readonly ContractSpec[] = [
  spec<Plan.QueryPlan>(PLAN, "", {
    schema_version: "required",
    plan_id: "required",
    intent: "required",
    systems: "optional",
    agents: "optional",
    join: "optional",
    steps: "required",
    catalog_versions: "required",
    limits: "required",
    round: "optional",
  }),
  spec<Plan.PlanLimits>(PLAN, "/$defs/limits", {
    max_rounds: "required",
    max_tool_calls: "required",
    max_repairs: "required",
  }),
  spec<Plan.CrossJoin>(PLAN, "/$defs/crossJoin", {
    entity: "required",
    canonical_id: "required",
    steps: "required",
    on_missing: "optional",
  }),
  spec<Plan.PlanStep>(PLAN, "/$defs/planStep", {
    step_id: "required",
    agent: "required",
    system: "required",
    tool: "required",
    arguments: "required",
    depends_on: "optional",
    optional: "optional",
  }),
  spec<Plan.StepDependency>(PLAN, "/$defs/stepDependency", {
    step_id: "required",
    hard: "optional",
  }),
  spec<Plan.FactReference>(PLAN, "/$defs/factReference", {
    $ref_step: "required",
    $ref_fact: "required",
    $ref_field: "optional",
  }),

  spec<Ev.EntityRef>(EVIDENCE, "/$defs/entityRef", {
    type: "required",
    id: "required",
    name: "optional",
  }),
  spec<Ev.Period>(EVIDENCE, "/$defs/period", {
    expression: "required",
    from: "required",
    to: "required",
    text: "required",
  }),
  spec<Ev.Provenance>(EVIDENCE, "/$defs/provenance", {
    tool_name: "required",
    catalog_version: "required",
    generated_at: "required",
  }),
  spec<Ev.EvidenceFact>(EVIDENCE, "/$defs/fact", {
    type: "required",
    fact_id: "required",
    call_id: "required",
    system_id: "required",
    metric: "optional",
    label: "required",
    value: "required",
    unit: "optional",
    entity: "optional",
    dimensions: "optional",
    period: "optional",
    provenance: "required",
  }),
  spec<Ev.EvidencePassage>(EVIDENCE, "/$defs/passage", {
    type: "required",
    passage_id: "required",
    call_id: "required",
    system_id: "required",
    document_id: "required",
    title: "required",
    section: "optional",
    anchor: "optional",
    text: "required",
    kind: "required",
    doc_version: "optional",
    updated_at: "optional",
    url: "optional",
    relevance: "required",
  }),
  spec<Ev.EvidenceMedia>(EVIDENCE, "/$defs/media", {
    type: "required",
    media_id: "required",
    call_id: "required",
    system_id: "required",
    document_id: "required",
    mime: "required",
    caption: "required",
    uri: "required",
    bytes: "optional",
    anchor: "optional",
  }),
  spec<Ev.EvidenceReference>(EVIDENCE, "/$defs/evidenceReference", {
    call_id: "required",
    fact_id: "required",
  }),
  spec<Ev.TextSpan>(EVIDENCE, "/$defs/textSpan", { start: "required", end: "required" }),
  spec<Ev.GroundingClaim>(EVIDENCE, "/$defs/groundingClaim", {
    claim_id: "required",
    text_span: "required",
    raw_value: "required",
    normalized: "required",
    supported_by: "required",
    verdict: "required",
    reason: "optional",
  }),
  spec<Ev.GroundingResult>(EVIDENCE, "/$defs/groundingResult", {
    ok: "required",
    checked: "required",
    claims: "required",
    unsupported: "required",
  }),

  spec<Mcp.McpEnvelope>(ENVELOPE, "", {
    schema_version: "required",
    system_id: "required",
    tool_name: "required",
    call_id: "required",
    correlation_id: "required",
    generated_at: "required",
    catalog_version: "required",
    period_interpreted: "optional",
    facts: "required",
    rows: "optional",
    passages: "required",
    media: "required",
    warnings: "required",
    partial: "required",
    next_cursor: "optional",
  }),
  spec<Mcp.EnvelopeFact>(ENVELOPE, "/$defs/fact", {
    key: "required",
    label: "required",
    metric: "optional",
    value: "required",
    unit: "optional",
    entity: "optional",
    dimensions: "optional",
  }),
  spec<Mcp.EnvelopePassage>(ENVELOPE, "/$defs/passage", {
    passage_id: "required",
    document_id: "required",
    title: "required",
    section: "optional",
    anchor: "optional",
    text: "required",
    kind: "required",
    doc_version: "optional",
    updated_at: "optional",
    url: "optional",
    relevance: "required",
  }),
  spec<Mcp.EnvelopeMedia>(ENVELOPE, "/$defs/media", {
    media_id: "required",
    document_id: "required",
    mime: "required",
    caption: "required",
    uri: "required",
    bytes: "optional",
    anchor: "optional",
  }),
  spec<Mcp.EnvelopeWarning>(ENVELOPE, "/$defs/warning", {
    code: "required",
    message: "required",
  }),

  spec<Mcp.McpServersFile>(SERVERS, "", { schema_version: "required", servers: "required" }),
  spec<Mcp.McpServer>(SERVERS, "/$defs/server", {
    id: "required",
    display_name: "required",
    routing_description: "required",
    transport: "required",
    identity: "required",
    timeouts: "required",
    limits: "required",
    contract: "required",
    capabilities: "required",
    content: "required",
    enabled: "required",
  }),
  spec<Mcp.McpTransport>(SERVERS, "/$defs/transport", {
    kind: "required",
    url: "required",
    tls: "optional",
  }),
  spec<Mcp.McpTls>(SERVERS, "/$defs/tls", {
    client_cert: "required",
    client_key: "required", // pragma: allowlist secret (nombre de campo, no un secreto)
    ca_bundle: "required",
    verify: "required",
  }),
  spec<Mcp.McpIdentity>(SERVERS, "/$defs/identity", { audience: "required", scopes: "required" }),
  spec<Mcp.McpTimeouts>(SERVERS, "/$defs/timeouts", {
    connect_ms: "required",
    call_ms: "required",
  }),
  spec<Mcp.McpLimits>(SERVERS, "/$defs/limits", {
    max_concurrency: "required",
    max_rows: "required",
  }),
  spec<Mcp.McpContract>(SERVERS, "/$defs/contract", { min_envelope_version: "required" }),

  spec<Orc.TaskBudgets>(TASK, "/$defs/taskBudgets", {
    max_wall_ms: "required",
    max_tokens: "required",
    max_cost_eur: "required",
  }),
  spec<Orc.AgentTask>(TASK, "/$defs/agentTask", {
    task_id: "required",
    agent_id: "required",
    objective: "required",
    entities: "required",
    expects: "required",
    locale: "required",
    budgets: "required",
    delegated_identity: "required",
    depends_on: "optional",
    optional: "optional",
  }),
  spec<Orc.DelegationPlan>(DELEGATION, "", {
    schema_version: "required",
    plan_id: "required",
    turn_id: "required",
    response_mode: "required",
    principal_id: "required",
    policy_version: "required",
    tasks: "required",
    composition: "required",
    budgets: "required",
    requires_human_approval: "optional",
  }),
  spec<Orc.Composition>(DELEGATION, "/$defs/composition", {
    kind: "required",
    tasks: "required",
    entity: "optional",
    canonical_id: "optional",
    on_missing: "optional",
  }),
  spec<Orc.Budgets>(DELEGATION, "/$defs/budgets", {
    max_wall_ms: "required",
    max_tokens: "required",
    max_cost_eur: "required",
    max_agents: "required",
  }),
  spec<Orc.AgentWarning>(RESULT, "/$defs/warning", { code: "required", message: "required" }),
  spec<Orc.NeedDelegation>(RESULT, "/$defs/needDelegation", {
    reason: "required",
    suggested_domain: "required",
    context_ref: "required",
    rationale: "required",
  }),
  spec<Orc.ModelOutput>(RESULT, "/$defs/modelOutput", {
    provider: "required",
    model: "required",
    model_version: "required",
    purpose: "required",
    text: "required",
    tokens_in: "required",
    tokens_out: "required",
    cost_eur: "required",
    produced_at: "required",
  }),
  spec<Orc.ToolCallTrace>(RESULT, "/$defs/toolCallTrace", {
    call_id: "required",
    system_id: "required",
    tool_name: "required",
    ms: "required",
    ok: "required",
  }),
  spec<Orc.ExternalCallTrace>(RESULT, "/$defs/externalCallTrace", {
    policy_id: "required",
    at: "required",
    provider: "optional",
    domain: "optional",
    redactions: "optional",
    tokens: "optional",
    cost_eur: "optional",
  }),
  spec<Orc.PolicyDecision>(RESULT, "/$defs/policyDecision", {
    turn_id: "required",
    principal_id: "required",
    action: "required",
    decision: "required",
    reason_code: "required",
    policy_version: "required",
    decided_at: "required",
    agent_id: "optional",
    scopes: "optional",
  }),
  spec<Orc.ApprovalRecord>(RESULT, "/$defs/approvalRecord", {
    request_id: "required",
    status: "required",
    evidence_refs: "optional",
    decided_by: "optional",
    decided_at: "optional",
  }),
  spec<Orc.AgentRun>(RESULT, "/$defs/agentRun", {
    run_id: "required",
    agent_id: "required",
    started_at: "required",
    ended_at: "required",
    tokens_in: "optional",
    tokens_out: "optional",
    cost_eur: "optional",
    tool_calls: "optional",
    external: "optional",
    policy_checks: "optional",
    approvals: "optional",
  }),
  spec<Orc.AgentResult>(RESULT, "/$defs/agentResult", {
    task_id: "required",
    agent_id: "required",
    agent_version: "required",
    status: "required",
    run: "required",
    evidence: "optional",
    warnings: "optional",
    need_delegation: "optional",
    model_outputs: "optional",
  }),
  spec<Orc.AgentSlo>(CARD, "/$defs/slo", { p95_ms: "required", availability: "required" }),
  spec<Orc.AgentBudgets>(CARD, "/$defs/budgets", {
    max_tokens_per_run: "required",
    max_cost_per_run_eur: "required",
    max_wall_ms: "required",
  }),
  spec<Orc.AgentCard>(CARD, "/$defs/agentCard", {
    agent_id: "required",
    version: "required",
    display_name: "required",
    owner: "required",
    status: "required",
    connectivity: "required",
    visibility: "required",
    safe_description: "required",
    public_capabilities: "required",
    routing_description: "required",
    allowed_actions: "required",
    scopes: "required",
    entities_exposed: "required",
    mcp_bindings: "required",
    provider_bindings: "required",
    slo: "required",
    budgets: "required",
    golden_set: "required",
    kill_switch: "required",
  }),
  spec<Orc.TokenUsage>(TURN, "/$defs/tokenUsage", {
    tokens_in: "optional",
    tokens_out: "optional",
  }),
  spec<Orc.ConversationTurn>(TURN, "/$defs/conversationTurn", {
    turn_id: "required",
    conversation_id: "required",
    principal_id: "required",
    question: "required",
    response_mode: "required",
    policy_version: "required",
    status: "required",
    agents_used: "optional",
    delegation_plan: "optional",
    runs: "optional",
    evidence: "optional",
    grounding: "optional",
    approvals: "optional",
    tokens: "optional",
    cost_eur: "optional",
    latency_ms: "optional",
    missing_agents: "optional",
    redelegations: "optional",
  }),

  spec<SseEnvelope<SseEventType>>(SSE, "", {
    schema_version: "required",
    event_id: "required",
    event_type: "required",
    correlation_id: "required",
    sequence: "required",
    timestamp: "required",
    payload: "required",
  }),
  spec<UnsupportedClaim>(SSE, "/$defs/groundingPayload/properties/unsupported/items", {
    claim_id: "required",
    raw_value: "required",
  }),

  spec<Reg.AgentMcpBindings>(`${R}agent-mcp-bindings.schema.json`, "", {
    schema_version: "required",
    bindings: "required",
  }),
  spec<Reg.AgentMcpBinding>(`${R}agent-mcp-bindings.schema.json`, "/$defs/binding", {
    agent_id: "required",
    mcp_server: "required",
    scopes: "required",
    actions: "required",
    active: "required",
  }),
  spec<Reg.AgentProviderBindings>(`${R}agent-provider-bindings.schema.json`, "", {
    schema_version: "required",
    bindings: "required",
  }),
  spec<Reg.AgentProviderBinding>(`${R}agent-provider-bindings.schema.json`, "/$defs/binding", {
    agent_id: "required",
    provider: "required",
    purposes: "required",
    max_classification: "required",
    region: "optional",
    active: "required",
  }),
  spec<Reg.ModelProviders>(`${R}model-providers.schema.json`, "", {
    schema_version: "required",
    providers: "required",
  }),
  spec<Reg.ModelProvider>(`${R}model-providers.schema.json`, "/$defs/provider", {
    id: "required",
    kind: "required",
    region: "required",
    models: "required",
    retention_days: "required",
    contract_ref: "optional",
    active: "required",
  }),
  spec<Reg.ExternalSources>(`${R}external-sources.schema.json`, "", {
    schema_version: "required",
    sources: "required",
  }),
  spec<Reg.ExternalSource>(`${R}external-sources.schema.json`, "/$defs/source", {
    id: "required",
    domains: "required",
    kind: "required",
    reliability: "required",
    agents: "required",
    active: "required",
  }),
  spec<Reg.EgressPolicies>(`${R}egress-policy.schema.json`, "", {
    schema_version: "required",
    default: "required",
    policies: "required",
  }),
  spec<Reg.EgressPolicy>(`${R}egress-policy.schema.json`, "/$defs/policy", {
    policy_id: "required",
    agents: "required",
    allowlist_domains: "required",
    methods: "required",
    max_bytes: "required",
    max_requests_per_run: "required",
    max_cost_per_run_eur: "required",
    allowed_classifications: "required",
    redactions: "required",
    retention_days: "required",
    region: "required",
  }),
  spec<Reg.EntitiesFile>(`${R}entities.schema.json`, "", {
    schema_version: "required",
    entidades: "required",
  }),
  spec<Reg.EntityDefinition>(`${R}entities.schema.json`, "/$defs/entity", {
    identificador_canonico: "required",
    formato: "optional",
    descripcion: "optional",
    mapeo: "required",
  }),
  spec<Reg.EntityMapping>(`${R}entities.schema.json`, "/$defs/mapping", {
    campo: "required",
    via: "required",
  }),
];

/** Carga de cada evento SSE: la clave del objeto es el event_type. */
export const SSE_PAYLOAD_KEYS: { readonly [K in SseEventType]: KeySpec<SsePayloads[K]> } = {
  mode: { response_mode: "required" },
  stage: { stage: "required", detail: "optional", step_id: "optional" },
  delegation: { task_id: "required", agent_id: "required", depends_on: "required" },
  tool_call: {
    agent_id: "required",
    task_id: "required",
    step_id: "required",
    call_id: "required",
    system_id: "required",
    tool_name: "required",
    arguments_digest: "required",
  },
  tool_result: {
    agent_id: "required",
    task_id: "required",
    step_id: "required",
    call_id: "required",
    ok: "required",
    facts_count: "required",
    ms: "required",
    partial: "required",
  },
  agent_result: {
    task_id: "required",
    agent_id: "required",
    status: "required",
    evidence_count: "required",
    ms: "required",
  },
  approval_required: {
    request_id: "required",
    agent_id: "required",
    summary: "required",
    impact: "required",
    expires_at: "required",
  },
  delta: { section: "required", text: "required" },
  grounding: { ok: "required", checked: "required", unsupported: "required" },
  warning: { code: "required", message: "required", system_id: "optional", agent_id: "optional" },
  error: { code: "required", message: "required", recoverable: "required" },
  done: {
    message_id: "required",
    conversation_id: "required",
    status: "required",
    partial: "required",
    missing_systems: "required",
    grounding_ok: "required",
    plan_id: "required",
    round: "required",
    repairs: "required",
    latency_ms: "required",
    model: "required",
    catalog_versions: "required",
    response_mode: "required",
    agents_used: "required",
    missing_agents: "required",
  },
};

export interface EnumSpec {
  readonly schema: string;
  readonly pointer: string;
  readonly values: readonly (string | number)[];
}

const COMMON = "common.schema.json";

export const ENUM_SPECS: readonly EnumSpec[] = [
  { schema: COMMON, pointer: "/$defs/locale", values: LOCALES },
  { schema: COMMON, pointer: "/$defs/role", values: ROLES },
  { schema: COMMON, pointer: "/$defs/effect", values: EFFECTS },
  { schema: COMMON, pointer: "/$defs/purpose", values: PURPOSES },
  { schema: COMMON, pointer: "/$defs/dataClass", values: DATA_CLASSES },
  { schema: COMMON, pointer: "/$defs/responseMode", values: RESPONSE_MODES },
  { schema: PLAN, pointer: "/$defs/intent", values: INTENTS },
  { schema: PLAN, pointer: "/$defs/factReference/properties/$ref_field", values: FACT_FIELDS },
  { schema: EVIDENCE, pointer: "/$defs/unit", values: UNITS },
  { schema: EVIDENCE, pointer: "/$defs/passageKind", values: PASSAGE_KINDS },
  { schema: EVIDENCE, pointer: "/$defs/groundingClaim/properties/verdict", values: VERDICTS },
  { schema: SERVERS, pointer: "/$defs/server/properties/content/items", values: CONTENT_KINDS },
  { schema: TASK, pointer: "/$defs/expects", values: EXPECTS },
  { schema: DELEGATION, pointer: "/properties/response_mode", values: DELEGATING_MODES },
  {
    schema: DELEGATION,
    pointer: "/$defs/composition/properties/kind",
    values: COMPOSITION_KINDS,
  },
  { schema: RESULT, pointer: "/$defs/status", values: AGENT_RESULT_STATUSES },
  {
    schema: RESULT,
    pointer: "/$defs/needDelegation/properties/reason",
    values: NEED_DELEGATION_REASONS,
  },
  {
    schema: RESULT,
    pointer: "/$defs/needDelegation/properties/suggested_domain",
    values: AGENT_DOMAINS,
  },
  {
    schema: RESULT,
    pointer: "/$defs/policyDecision/properties/action",
    values: [...AGENT_ACTIONS, ...PLATFORM_ACTIONS],
  },
  {
    schema: RESULT,
    pointer: "/$defs/approvalRecord/properties/status",
    values: APPROVAL_STATUSES,
  },
  { schema: CARD, pointer: "/$defs/lifecycle", values: LIFECYCLE_STATES },
  { schema: CARD, pointer: "/$defs/visibility", values: VISIBILITIES },
  { schema: CARD, pointer: "/$defs/connectivity", values: CONNECTIVITIES },
  { schema: TURN, pointer: "/$defs/status", values: TURN_STATUSES },
  {
    schema: TURN,
    pointer: "/$defs/conversationTurn/allOf/0/if/properties/response_mode",
    values: DIRECT_MODES,
  },
  { schema: SSE, pointer: "/properties/event_type", values: SSE_EVENT_TYPES },
  {
    schema: SSE,
    pointer: "/$defs/approval_requiredPayload/properties/impact",
    values: IMPACTS,
  },
  { schema: SSE, pointer: "/$defs/deltaPayload/properties/section", values: DELTA_SECTIONS },
  {
    schema: `${R}model-providers.schema.json`,
    pointer: "/$defs/provider/properties/kind",
    values: PROVIDER_KINDS,
  },
  {
    schema: `${R}external-sources.schema.json`,
    pointer: "/$defs/source/properties/kind",
    values: SOURCE_KINDS,
  },
  {
    schema: `${R}external-sources.schema.json`,
    pointer: "/$defs/source/properties/reliability",
    values: RELIABILITIES,
  },
];
