# ADR-043: Concreciones del dominio núcleo

- Estado: Aceptado
- Origen: Prompt 2
- Referencia: Documento Maestro v4.8, sección 6.2, 6.3, 6.6, 6.9.2

## Contexto

Al implementar el dominio del Prompt 2 aparecen puntos en los que el documento maestro se contradice o deja un detalle sin fijar. El modo de trabajo (2.9) exige registrar toda desviación como ADR.

## Decisión

1. `systems` del QueryPlan se deriva de los pasos. El esquema de 6.2 lo exige, pero el ejemplo multiagente de 6.2.3 no lo trae y es redundante con `step.system`. Al leer un plan es opcional; si viene, debe coincidir con los sistemas de los pasos (`systems_mismatch`). La forma canónica lo emite siempre, ordenado.
2. `agent` es obligatorio en cada paso, como dice el esquema, aunque los ejemplos de un solo sistema de 6.2.3 lo omiten. Los ejemplos se leen como abreviados.
3. Una `factReference` a un paso exige declarar ese paso en `depends_on` (`reference_without_dependency`). El documento pide que el paso referenciado sea anterior en orden topológico; exigirlo explícito hace que el grafo de oleadas sea la única fuente del orden.
4. Las clases de error llevan el sufijo `Error` (`McpTimeoutError`, `LlmUnavailableError`, `GroundingFailedError`…) por convención de Python; los códigos estables son los de 6.6 en minúsculas. Se añade `InvalidPlanError`, subclase de `ValidationError` con código `invalid_plan`, que reúne todos los motivos de rechazo (`PlanIssue`) porque la validación es previa y total.
5. `agents` y `join.steps` se normalizan ordenados al construir: son conjuntos (uniqueItems), y así la igualdad y la forma canónica no dependen del orden en que los escribió el modelo.
6. Los números de los argumentos son `Decimal`, nunca `float`. El JSON se lee con `parse_float=Decimal`; un `float` que llegue en un diccionario se convierte por su representación más corta y se rechazan NaN e infinitos. En la forma canónica, 10.70 y 10.7 se escriben igual.
7. El discriminador de la unión de evidencia es `evidence_type` (`fact`, `passage`, `media`), porque `kind` ya es un campo de `EvidencePassage`.
8. Un pasaje de tipo `procedure` sin `updated_at` no se puede construir: 6.9.2 lo declara "obligatorio en la práctica" y se aplica en el dominio. Un adjunto con URI `data:` tampoco: la media viaja como referencia.
9. `Unit` fija el conjunto inicial: count, percent, ratio, ms, seconds, minutes, hours, days, eur, liters. 6.3 solo da ejemplos; ampliar el conjunto es un cambio de dominio revisado.
10. Una afirmación `unsupported` o `whitelisted` exige motivo y no lleva referencia; una `supported` exige referencia y valor normalizado. `GroundingResult` solo se construye con `ok`, `checked` y `unsupported` coherentes con sus afirmaciones.

## Consecuencias

El dominio rechaza por construcción estados que el documento describe como imposibles. Un plan del modelo que omita `systems` o use otro orden de claves produce la misma forma canónica. Cualquier cambio de estas concreciones requiere un ADR nuevo.
