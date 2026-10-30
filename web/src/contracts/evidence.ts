// Evidencia y grounding (contracts/evidence.schema.json, 6.3 y 6.9.2).

import type { CallId, Instant, LocalId, SystemId, Text } from "./common";

export const UNITS = [
  "count",
  "percent",
  "ratio",
  "ms",
  "seconds",
  "minutes",
  "hours",
  "days",
  "eur",
  "liters",
] as const;
export type Unit = (typeof UNITS)[number];

export const PASSAGE_KINDS = ["reference", "procedure", "warning", "definition"] as const;
export type PassageKind = (typeof PASSAGE_KINDS)[number];

export const VERDICTS = ["supported", "unsupported", "whitelisted"] as const;
export type Verdict = (typeof VERDICTS)[number];

export type FactValue = number | string | boolean | null;

export interface EntityRef {
  readonly type: Text;
  readonly id: Text;
  readonly name?: string;
}

export interface Period {
  readonly expression: Text;
  readonly from: Instant;
  readonly to: Instant;
  readonly text: Text;
}

export interface Provenance {
  readonly tool_name: Text;
  readonly catalog_version: Text;
  readonly generated_at: Instant;
}

export interface EvidenceFact {
  readonly type: "fact";
  readonly fact_id: LocalId;
  readonly call_id: CallId;
  readonly system_id: SystemId;
  readonly metric?: Text;
  readonly label: Text;
  readonly value: FactValue;
  readonly unit?: Unit;
  readonly entity?: EntityRef;
  readonly dimensions?: Readonly<Record<string, string>>;
  readonly period?: Period;
  readonly provenance: Provenance;
}

export interface EvidencePassage {
  readonly type: "passage";
  readonly passage_id: LocalId;
  readonly call_id: CallId;
  readonly system_id: SystemId;
  readonly document_id: Text;
  readonly title: Text;
  readonly section?: string;
  readonly anchor?: string;
  readonly text: Text;
  readonly kind: PassageKind;
  readonly doc_version?: string;
  /** Obligatorio cuando kind es procedure. */
  readonly updated_at?: Instant;
  readonly url?: string;
  readonly relevance: number;
}

export interface EvidenceMedia {
  readonly type: "media";
  readonly media_id: LocalId;
  readonly call_id: CallId;
  readonly system_id: SystemId;
  readonly document_id: Text;
  readonly mime: string;
  readonly caption: Text;
  /** Referencia autenticada; nunca data:. */
  readonly uri: string;
  readonly bytes?: number;
  readonly anchor?: string;
}

/** Unión discriminada por type. Un pasaje nunca respalda una cifra. */
export type Evidence = EvidenceFact | EvidencePassage | EvidenceMedia;

export interface EvidenceReference {
  readonly call_id: CallId;
  readonly fact_id: LocalId;
}

export interface TextSpan {
  readonly start: number;
  readonly end: number;
}

export interface GroundingClaim {
  readonly claim_id: LocalId;
  readonly text_span: TextSpan;
  readonly raw_value: Text;
  readonly normalized: number | null;
  readonly supported_by: EvidenceReference | null;
  readonly verdict: Verdict;
  readonly reason?: string | null;
}

export interface GroundingResult {
  readonly ok: boolean;
  readonly checked: number;
  readonly claims: readonly GroundingClaim[];
  readonly unsupported: readonly LocalId[];
}
