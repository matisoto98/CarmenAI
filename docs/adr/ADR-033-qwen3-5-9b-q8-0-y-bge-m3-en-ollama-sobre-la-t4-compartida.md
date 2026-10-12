# ADR-033: Qwen3.5-9B Q8_0 y bge-m3 en Ollama sobre la T4 compartida

- Estado: Aceptado
- Origen: v4.2
- Referencia: Documento Maestro v4.8, sección 4.1

## Contexto

Una máquina nueva con A10 cuesta unos 2.336 $ al mes; SRVAZMG002FYB01 ya existe y tiene capacidad libre.

## Decisión

La inferencia reutiliza SRVAZMG002FYB01 como segundo inquilino, con Qwen3.5-9B Q8_0 y bge-m3 en Ollama (0.17.5 o superior). En el Mac, Q4_K_M. Sin vLLM ni TEI en el MVP.

## Consecuencias

El mejor Qwen que cabe, sin coste añadido. Si el arnés no alcanza los umbrales de 10.9, el modo sombra compara Qwen3.6-35B-A3B y ese dato justifica o no la A10.
