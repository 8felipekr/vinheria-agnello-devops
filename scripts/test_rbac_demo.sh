#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CA="${ROOT_DIR}/certs/ca.crt"

echo "=== Teste JWT RS256 + RBAC (https://localhost:8443) ==="

C1=$(curl -s -o /dev/null -w '%{http_code}' --cacert "$CA" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H 'Content-Type: application/json' \
  -d '{"temperatura":14.5,"umidade":68,"luminosidade":5}')
echo "[1] Sem token                 -> HTTP ${C1} (esperado: 401 Unauthorized)"

C2=$(curl -s -o /dev/null -w '%{http_code}' --cacert "$CA" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H 'Authorization: Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhdHRhY2tlciIsInJvbGVzIjpbIlJPTEVfRU5PTE9HTyJdfQ.' \
  -H 'Content-Type: application/json' \
  -d '{"temperatura":14.5,"umidade":68,"luminosidade":5}')
echo "[2] JWT forjado (alg=none)    -> HTTP ${C2} (esperado: 401 Unauthorized)"

CLI=$(curl -sf --cacert "$CA" -X POST https://localhost:8443/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"cliente","password":"Cliente@2026"}' | jq -r .access_token)
C3=$(curl -s -o /dev/null -w '%{http_code}' --cacert "$CA" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H "Authorization: Bearer ${CLI}" \
  -H 'Content-Type: application/json' \
  -d '{"temperatura":14.5,"umidade":68,"luminosidade":5}')
echo "[3] ROLE_CLIENTE (sem acesso) -> HTTP ${C3} (esperado: 403 Forbidden)"

ENO=$(curl -sf --cacert "$CA" -X POST https://localhost:8443/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"enologo","password":"Agnello@2026"}' | jq -r .access_token)
C4=$(curl -s -o /dev/null -w '%{http_code}' --cacert "$CA" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H "Authorization: Bearer ${ENO}" \
  -H 'Content-Type: application/json' \
  -d '{"tanqueOuAdegaId":"ADEGA-BARRIQUE-03","sensorId":"ESP32-DEV1-GPIO34","temperatura":19.8,"umidade":52.4,"luminosidade":18.5}')
echo "[4] ROLE_ENOLOGO (autorizado) -> HTTP ${C4} (esperado: 201 Created + alerta)"
