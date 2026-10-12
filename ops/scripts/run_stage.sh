#!/usr/bin/env bash
# Ejecuta una etapa de pruebas de CI (8.4) sobre api/tests/<directorio>.
# Si la etapa aún no tiene pruebas (pytest sale con 5), pasa e indica qué prompt la llena.
# Uso: ops/scripts/run_stage.sh <directorio> "<prompt que la llena>"
set -uo pipefail

dir="$1"
prompt="$2"
root="$(cd "$(dirname "$0")/../.." && pwd)"

if [ ! -d "$root/api/tests/$dir" ]; then
  echo "Etapa sin pruebas todavía en api/tests/$dir: llegan en el $prompt."
  exit 0
fi

pytest "$root/api/tests/$dir" -v
status=$?
if [ "$status" -eq 5 ]; then
  echo "Etapa sin pruebas todavía en api/tests/$dir: llegan en el $prompt."
  exit 0
fi
exit "$status"
