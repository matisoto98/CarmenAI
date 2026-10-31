# Evaluación de Carmen

Aquí está el criterio de «terminado» (10.4). Se escribe antes que el orquestador, para que lo que se
construya se mida contra algo fijado de antemano. El arnés que ejecuta estos casos contra Carmen
llega en el Prompt 32. Hasta entonces, `eval/tests/` comprueba que todo está bien formado.

```
uv run pytest eval/tests -v
```

## Qué hay

| Ruta | Qué es |
|---|---|
| `golden/carmen_golden_set.yaml` | Los 20 casos iniciales: 8 factuales, 3 de tendencia, 3 analíticos, 4 de negativa obligatoria y 2 de conflicto. 7 en inglés y 6 en portugués |
| `golden/vigia/catalogo.yaml` | Casos del catálogo semilla de VigIA (5.17.7), con los mensajes del simulador y sus erratas reales |
| `golden/modes_labeled.yaml` | Conjunto etiquetado de los cinco modos de respuesta (2.3.2), con los pares de 2.3.4 |
| `fixtures/catalog_vigia.json`, `fixtures/catalog_plenmind.json` | Catálogos de herramientas. Son provisionales: el Prompt 12 trae el real de VigIA |
| `fixtures/expected_plans/` | Planes esperados en forma normal canónica: `qp_*` son QueryPlan y `dp_*` son DelegationPlan |
| `schemas/` | Esquemas de un fichero de casos, del conjunto de modos y de un catálogo |
| `tests/test_golden_wellformed.py` | Comprueba los ficheros anteriores |

## Estructura de un caso

Un caso tiene tres niveles. Los dos primeros bloquean la construcción y el tercero nunca la bloquea.

```yaml
- id: A01                        # prefijo por categoría: F, T, A, N, C; VC en el catálogo
  categoria: analitica
  locale: es                     # es | en | pt
  role: MANAGER                  # ADMIN | MANAGER | OPERATOR | AUDITOR
  pregunta: "¿Por qué Getafe va mal este mes?"
  modo_esperado: DELEGATE_SINGLE # uno de los cinco modos (2.3.2)
  agentes: [agent.vigia]         # obligatorio si el modo delega; prohibido si no
  depende_de: [P12]              # opcional: el caso espera a ese prompt

  # NIVEL 1 — PLAN (aserción dura). Solo en modos que delegan.
  plan_esperado:
    intent: analytic
    systems: [vigia]
    steps_min: [site_resolver, build_dossier]          # herramientas que tiene que usar
    steps_prohibidos: [query_metric]                   # herramientas que no puede usar
    dependencias: { build_dossier: [site_resolver] }
    argumentos:                                        # herramienta.argumento: valor
      build_dossier.period: mes_actual
    conflicto: { code: metric_conflict, metric: ..., systems: [...] }  # opcional
    canonicos: [qp_a01_getafe_dossier.json]            # opcional: planes completos

  negativa: { motivo: no_se_registra, no_revela: [...] }  # obligatoria en REFUSE y negativa
  aclaracion: { falta: periodo }                          # obligatoria en CLARIFY
  catalogo: { canal, en_grupo, mencion, plantilla, parametros, respuesta }  # solo en catalogo
  variantes_por_rol: [{ role, modo_esperado, ... }]       # comportamiento diferencial por rol

  # NIVEL 2 — PROPIEDADES (verificación por programa). Claves cerradas: ver el esquema.
  propiedades:
    grounding_ok: true
    avisos_obligatorios: [alarmas_abiertas_no_es_carga]

  # NIVEL 3 — RÚBRICA (muestreo humano; nunca bloquea la construcción)
  rubrica:
    - no afirma causalidad como hecho
  k_de_n: [3, 3]                 # tiene que pasar k de n ejecuciones
```

Un mensaje de grupo sin mención no abre turno, así que no lleva `modo_esperado`.

## Qué se comprueba

- Cada fichero valida contra su esquema. Además hay casos rotos a propósito, para comprobar que el
  esquema los rechaza.
- El reparto por categoría y por idioma es el del Prompt 6, y los identificadores no se repiten.
- Toda pregunta sobre incidencias depende del Prompt 12, porque el MCP de VigIA aún no las expone. Ningún otro caso depende de él.
- Las herramientas, argumentos y valores de cada `plan_esperado` existen en el catálogo del sistema.
  Cada herramienta obligatoria admite el rol del caso. Por ejemplo, `correlate_events` es solo
  para ADMIN.
- Cada plan esperado valida contra `plan.schema.json` o `delegation-plan.schema.json`. Su fichero ya
  está en forma normal canónica (6.2.2), así que volver a escribirlo no cambia nada. Un
  DelegationPlan se lee además con el tipo del dominio, que aplica sus invariantes.
- Las aserciones de un caso coinciden con sus planes canónicos. Todo plan canónico está referenciado
  por algún caso.
- El conjunto de modos tiene al menos cuatro casos de cada modo. Contiene la tabla de 2.3.4, con
  «¿qué es VigIA?» frente a «¿cómo está VigIA?». Las dos preguntas de cada par se resuelven por
  modos distintos.

## Cómo se añade un caso

1. Elige el prefijo de su categoría y el siguiente número libre.
2. Rellena los tres niveles. Si el caso delega, nombra herramientas del catálogo. Si el catálogo no
   las tiene todavía, marca `depende_de`.
3. Si el plan importa entero, añade su fichero canónico a `fixtures/expected_plans/` y referéncialo
   en `canonicos`.
4. Ejecuta `uv run pytest eval/tests -v`.

Ningún sistema ni funcionalidad se da por terminado sin sus casos aquí (10.9).
