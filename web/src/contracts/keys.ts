// Tabla de claves de un tipo: qué campos tiene y cuáles son obligatorios.
// Es la parte del tipo que sobrevive en ejecución; la prueba de alineación la compara con el
// esquema. Si el tipo gana o pierde un campo y la tabla no, falla tsc; si el esquema cambia y
// el tipo no, falla la prueba (ADR-021: el esquema es la fuente, sin generación de código).

import type { SchemaVersion } from "./common";

export type Presence = "required" | "optional";

export type KeySpec<T> = {
  readonly [K in keyof T]-?: object extends Pick<T, K> ? "optional" : "required";
};

/** Raíz de contrato: el objeto más la versión del esquema (6.12.9). */
export type Versioned<T, V extends string = SchemaVersion> = T & { readonly schema_version: V };
