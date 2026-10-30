// Códigos estables de contracts/errors.json (6.6). La traducción a HTTP y SSE es de presentación.

export const ERROR_CODES = [
  "validation_error",
  "unknown_system",
  "unknown_tool",
  "invalid_arguments",
  "invalid_plan",
  "invalid_transition",
  "metric_conflict",
  "no_coverage",
  "no_data",
  "entity_not_resolved",
  "forbidden",
  "mcp_timeout",
  "mcp_unavailable",
  "mcp_contract_violation",
  "llm_unavailable",
  "llm_timeout",
  "grounding_failed",
  "cancelled",
  "internal",
] as const;
export type ErrorCode = (typeof ERROR_CODES)[number];
