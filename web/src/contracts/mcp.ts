// Sobre MCP y registro de servidores (contracts/mcp-envelope.schema.json 6.4,
// contracts/mcp-servers.schema.json 7.5).

import type {
  CallId,
  CorrelationId,
  Instant,
  LocalId,
  SchemaVersion,
  SystemId,
  Text,
} from "./common";
import type { EntityRef, FactValue, PassageKind, Period, Unit } from "./evidence";

export interface EnvelopeFact {
  readonly key: string;
  readonly label: Text;
  readonly metric?: Text;
  readonly value: FactValue;
  readonly unit?: Unit;
  readonly entity?: EntityRef;
  readonly dimensions?: Readonly<Record<string, string>>;
}

export interface EnvelopePassage {
  readonly passage_id: LocalId;
  readonly document_id: Text;
  readonly title: Text;
  readonly section?: string;
  readonly anchor?: string;
  readonly text: Text;
  readonly kind: PassageKind;
  readonly doc_version?: string;
  readonly updated_at?: Instant;
  readonly url?: string;
  readonly relevance: number;
}

export interface EnvelopeMedia {
  readonly media_id: LocalId;
  readonly document_id: Text;
  readonly mime: string;
  readonly caption: Text;
  readonly uri: string;
  readonly bytes?: number;
  readonly anchor?: string;
}

export interface EnvelopeWarning {
  readonly code: Text;
  readonly message: Text;
}

export type RowValue = string | number | boolean | null;

export interface McpEnvelope {
  readonly schema_version: SchemaVersion;
  readonly system_id: SystemId;
  readonly tool_name: string;
  readonly call_id: CallId;
  readonly correlation_id: CorrelationId;
  readonly generated_at: Instant;
  readonly catalog_version: Text;
  readonly period_interpreted?: Period;
  readonly facts: readonly EnvelopeFact[];
  /** Como mucho 500 filas (7.5). */
  readonly rows?: readonly Readonly<Record<string, RowValue>>[];
  readonly passages: readonly EnvelopePassage[];
  readonly media: readonly EnvelopeMedia[];
  /** Con partial, al menos un aviso. */
  readonly warnings: readonly EnvelopeWarning[];
  readonly partial: boolean;
  readonly next_cursor?: string | null;
}

export const CONTENT_KINDS = ["facts", "passages", "media"] as const;
export type ContentKind = (typeof CONTENT_KINDS)[number];

export interface McpTls {
  readonly client_cert: Text;
  readonly client_key: Text;
  readonly ca_bundle: Text;
  readonly verify: boolean;
}

export interface McpTransport {
  readonly kind: "streamable-http";
  readonly url: string;
  readonly tls?: McpTls;
}

export interface McpIdentity {
  readonly audience: string | null;
  readonly scopes: readonly string[];
}

export interface McpTimeouts {
  readonly connect_ms: number;
  readonly call_ms: number;
}

export interface McpLimits {
  readonly max_concurrency: number;
  readonly max_rows: number;
}

export interface McpContract {
  readonly min_envelope_version: string;
}

export interface McpServer {
  readonly id: SystemId;
  readonly display_name: Text;
  readonly routing_description: Text;
  readonly transport: McpTransport;
  readonly identity: McpIdentity;
  readonly timeouts: McpTimeouts;
  readonly limits: McpLimits;
  readonly contract: McpContract;
  readonly capabilities: readonly "read"[];
  readonly content: readonly ContentKind[];
  readonly enabled: boolean;
}

export interface McpServersFile {
  readonly schema_version: SchemaVersion;
  readonly servers: readonly McpServer[];
}
