// QueryPlan local de un agente (contracts/plan.schema.json, 6.2).

import type { AgentId, PlanId, SchemaVersion, StepId, SystemId, Text } from "./common";

export const INTENTS = [
  "social",
  "manifest",
  "glossary",
  "factual",
  "trend",
  "analytic",
  "knowledge",
  "documental",
  "procedural",
  "write_blocked",
] as const;
export type Intent = (typeof INTENTS)[number];

export const FACT_FIELDS = ["value", "entity_id", "label"] as const;
export type FactField = (typeof FACT_FIELDS)[number];

/** Referencia a un hecho de un paso anterior; nunca texto pegado de un resultado. */
export interface FactReference {
  readonly $ref_step: StepId;
  readonly $ref_fact: string;
  readonly $ref_field?: FactField;
}

export type Scalar = string | number | boolean;
export type ArgumentValue = Scalar | readonly Scalar[] | FactReference;

export interface StepDependency {
  readonly step_id: StepId;
  readonly hard?: boolean;
}

export interface PlanStep {
  readonly step_id: StepId;
  readonly agent: AgentId;
  readonly system: SystemId;
  readonly tool: string;
  readonly arguments: Readonly<Record<string, ArgumentValue>>;
  readonly depends_on?: readonly StepDependency[];
  readonly optional?: boolean;
}

export interface CrossJoin {
  readonly entity: Text;
  readonly canonical_id: Text;
  readonly steps: readonly StepId[];
  readonly on_missing?: "hueco_explicito";
}

export interface PlanLimits {
  readonly max_rounds: number;
  readonly max_tool_calls: number;
  readonly max_repairs: number;
}

export interface QueryPlan {
  readonly schema_version: SchemaVersion;
  readonly plan_id: PlanId;
  readonly intent: Intent;
  /** Se deriva de los pasos; si llega, debe coincidir (ADR-043). */
  readonly systems?: readonly SystemId[];
  readonly agents?: readonly AgentId[];
  readonly join?: CrossJoin;
  readonly steps: readonly PlanStep[];
  readonly catalog_versions: Readonly<Record<SystemId, string>>;
  readonly limits: PlanLimits;
  readonly round?: number;
}
