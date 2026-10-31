// Prompt 4: los tipos de TypeScript coinciden campo a campo con contracts/ (ADR-021).
// Añadir un campo obligatorio a un esquema sin tocar el tipo hace fallar esta prueba; tocar el
// tipo sin su tabla de claves hace fallar tsc.

import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, expectTypeOf, it } from "vitest";

import { ERROR_CODES } from "./errors";
import type { Presence } from "./keys";
import { CONTRACT_SPECS, ENUM_SPECS, SSE_PAYLOAD_KEYS } from "./spec";
import type { SseEvent, SseEventType, SsePayloads } from "./sse";
import { SSE_EVENT_TYPES } from "./sse";

const CONTRACTS = fileURLToPath(new URL("../../../contracts/", import.meta.url));

type Json = null | boolean | number | string | readonly Json[] | { readonly [key: string]: Json };
type JsonObject = Readonly<Record<string, Json>>;

function isObject(value: Json | undefined): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function load(name: string): JsonObject {
  const parsed = JSON.parse(readFileSync(`${CONTRACTS}${name}`, "utf-8")) as Json;
  if (!isObject(parsed)) throw new Error(`${name} no es un objeto JSON`);
  return parsed;
}

function schemaNames(dir = ""): string[] {
  return readdirSync(`${CONTRACTS}${dir}`, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory())
      return entry.name === "examples" ? [] : schemaNames(`${dir}${entry.name}/`);
    return entry.name.endsWith(".schema.json") ? [`${dir}${entry.name}`] : [];
  });
}

function resolve(name: string, pointer: string): JsonObject {
  let node: Json | undefined = load(name);
  for (const part of pointer.split("/").filter(Boolean)) {
    if (Array.isArray(node)) node = (node as readonly Json[])[Number(part)];
    else if (isObject(node)) node = node[part];
    else node = undefined;
  }
  if (!isObject(node)) throw new Error(`${name}#${pointer} no existe`);
  return node;
}

function schemaKeys(name: string, pointer: string): Record<string, Presence> {
  const node = resolve(name, pointer);
  const properties = node.properties;
  if (!isObject(properties)) throw new Error(`${name}#${pointer} no tiene properties`);
  const required = new Set(Array.isArray(node.required) ? (node.required as readonly Json[]) : []);
  return Object.fromEntries(
    Object.keys(properties).map((key) => [key, required.has(key) ? "required" : "optional"]),
  );
}

function sorted(keys: Readonly<Record<string, Presence>>): [string, Presence][] {
  return Object.entries(keys).sort(([a], [b]) => a.localeCompare(b));
}

describe("tipos frente a esquemas, campo a campo", () => {
  it.each(CONTRACT_SPECS.map((s) => [`${s.schema}#${s.pointer || "/"}`, s] as const))(
    "%s",
    (_, spec) => {
      expect(sorted(spec.keys)).toEqual(sorted(schemaKeys(spec.schema, spec.pointer)));
    },
  );

  it("todo objeto de todo esquema tiene tipo, salvo las raíces que solo añaden la versión", () => {
    const covered = new Set(CONTRACT_SPECS.map((s) => `${s.schema}#${s.pointer}`));
    const objects: string[] = [];
    for (const name of schemaNames()) {
      const schema = load(name);
      const defs = isObject(schema.$defs) ? Object.keys(schema.$defs) : [];
      for (const pointer of ["", ...defs.map((d) => `/$defs/${d}`)]) {
        const node = resolve(name, pointer);
        if (!isObject(node.properties)) continue;
        const keys = Object.keys(node.properties);
        const wrapper = pointer === "" && keys.length === 1 && keys[0] === "schema_version";
        const payload = name === "sse-events.schema.json" && pointer.endsWith("Payload");
        if (!wrapper && !payload) objects.push(`${name}#${pointer}`);
      }
    }
    expect(objects.filter((o) => !covered.has(o))).toEqual([]);
  });
});

describe("enumerados", () => {
  it.each(ENUM_SPECS.map((s) => [`${s.schema}#${s.pointer}`, s] as const))("%s", (_, spec) => {
    expect(resolve(spec.schema, spec.pointer).enum).toEqual(spec.values);
  });
});

describe("SSE 1.1", () => {
  const schema = "sse-events.schema.json";

  it("la unión discriminada cubre exactamente los tipos de evento, sin sobrar ni faltar", () => {
    expectTypeOf<SseEvent["event_type"]>().toEqualTypeOf<SseEventType>();
    expectTypeOf<keyof SsePayloads>().toEqualTypeOf<SseEventType>();
    expect(resolve(schema, "/properties/event_type").enum).toEqual(SSE_EVENT_TYPES);
    expect(Object.keys(SSE_PAYLOAD_KEYS).sort()).toEqual([...SSE_EVENT_TYPES].sort());
  });

  it("cada event_type estrecha su carga", () => {
    expectTypeOf<Extract<SseEvent, { event_type: "done" }>["payload"]>().toEqualTypeOf<
      SsePayloads["done"]
    >();
    expectTypeOf<Extract<SseEvent, { event_type: "approval_required" }>["payload"]>().toEqualTypeOf<
      SsePayloads["approval_required"]
    >();
  });

  it("el esquema enruta cada tipo a su carga", () => {
    const branches = load(schema).allOf;
    const routed: Record<string, Json> = {};
    for (const branch of Array.isArray(branches) ? (branches as readonly Json[]) : []) {
      if (!isObject(branch)) continue;
      const condition = resolveIn(branch, ["if", "properties", "event_type", "const"]);
      const target = resolveIn(branch, ["then", "properties", "payload", "$ref"]);
      if (typeof condition === "string") routed[condition] = target ?? null;
    }
    expect(routed).toEqual(
      Object.fromEntries(SSE_EVENT_TYPES.map((t) => [t, `#/$defs/${t}Payload`])),
    );
  });

  it.each(SSE_EVENT_TYPES.map((t) => [t] as const))("carga de %s", (type) => {
    expect(sorted(SSE_PAYLOAD_KEYS[type])).toEqual(
      sorted(schemaKeys(schema, `/$defs/${type}Payload`)),
    );
  });
});

function resolveIn(node: JsonObject, path: readonly string[]): Json | undefined {
  let current: Json | undefined = node;
  for (const part of path) current = isObject(current) ? current[part] : undefined;
  return current;
}

describe("errores", () => {
  it("los códigos son los de errors.json", () => {
    const errors = load("errors.json").errors;
    const codes = (Array.isArray(errors) ? (errors as readonly Json[]) : []).map((e) =>
      isObject(e) ? e.code : null,
    );
    expect(codes).toEqual(ERROR_CODES);
  });
});
