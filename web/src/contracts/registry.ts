// Registros y bindings de 7.10 (contracts/registry/*.schema.json).

import type {
  AgentId,
  DataClass,
  DottedId,
  McpServerId,
  Money,
  ProviderId,
  Purpose,
  SchemaVersion,
  Text,
} from "./common";

export interface AgentMcpBinding {
  readonly agent_id: AgentId;
  readonly mcp_server: McpServerId;
  readonly scopes: readonly DottedId[];
  readonly actions: readonly "read"[];
  readonly active: boolean;
}

export interface AgentMcpBindings {
  readonly schema_version: SchemaVersion;
  readonly bindings: readonly AgentMcpBinding[];
}

export interface AgentProviderBinding {
  readonly agent_id: AgentId;
  readonly provider: ProviderId;
  readonly purposes: readonly Purpose[];
  readonly max_classification: DataClass;
  readonly region?: Text;
  readonly active: boolean;
}

export interface AgentProviderBindings {
  readonly schema_version: SchemaVersion;
  readonly bindings: readonly AgentProviderBinding[];
}

export const PROVIDER_KINDS = ["internal", "external"] as const;
export type ProviderKind = (typeof PROVIDER_KINDS)[number];

export interface ModelProvider {
  readonly id: ProviderId;
  readonly kind: ProviderKind;
  readonly region: Text;
  readonly models: readonly Text[];
  readonly retention_days: number;
  readonly contract_ref?: string | null;
  readonly active: boolean;
}

export interface ModelProviders {
  readonly schema_version: SchemaVersion;
  readonly providers: readonly ModelProvider[];
}

export const SOURCE_KINDS = ["official_bulletin", "public_data", "weather", "reference"] as const;
export type SourceKind = (typeof SOURCE_KINDS)[number];

export const RELIABILITIES = ["primary", "secondary"] as const;
export type Reliability = (typeof RELIABILITIES)[number];

export interface ExternalSource {
  readonly id: DottedId;
  readonly domains: readonly string[];
  readonly kind: SourceKind;
  readonly reliability: Reliability;
  readonly agents: readonly AgentId[];
  readonly active: boolean;
}

export interface ExternalSources {
  readonly schema_version: SchemaVersion;
  readonly sources: readonly ExternalSource[];
}

export interface EgressPolicy {
  readonly policy_id: DottedId;
  readonly agents: readonly AgentId[];
  readonly allowlist_domains: readonly string[];
  readonly methods: readonly "GET"[];
  readonly max_bytes: number;
  readonly max_requests_per_run: number;
  readonly max_cost_per_run_eur: Money;
  readonly allowed_classifications: readonly DataClass[];
  readonly redactions: readonly Text[];
  readonly retention_days: number;
  readonly region: Text;
}

/** Sin política aplicable, la salida se deniega. */
export interface EgressPolicies {
  readonly schema_version: SchemaVersion;
  readonly default: "deny";
  readonly policies: readonly EgressPolicy[];
}

export interface EntityMapping {
  readonly campo: Text;
  readonly via: string | null;
}

export interface EntityDefinition {
  readonly identificador_canonico: string;
  readonly formato?: string;
  readonly descripcion?: Text;
  readonly mapeo: Readonly<Record<AgentId, EntityMapping>>;
}

export interface EntitiesFile {
  readonly schema_version: SchemaVersion;
  readonly entidades: Readonly<Record<string, EntityDefinition>>;
}
