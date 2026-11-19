#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CA_CERT="${ROOT_DIR}/certs/ca.crt"

echo "============================================================================"
echo "1. VALIDACAO INFRAESTRUTURA: DNS (vinheria.local) + DHCP (DORA / LEASES)"
echo "============================================================================"
echo "[1.1] Tabela de leases DHCP no servidor dnsmasq:"
docker exec vinheria-dns-dhcp cat /var/lib/misc/dnsmasq.leases

echo ""
echo "[1.2] Resolucao DNS autoritativa a partir do Quality & IoT Service:"
for host in dns.vinheria.local gateway.vinheria.local quality.vinheria.local notification.vinheria.local jenkins.vinheria.local prod-site.vinheria.local esp32-sensor-01.vinheria.local; do
  ip="$(docker exec vinheria-quality-iot dig +short @172.28.0.53 "$host" | tail -n 1)"
  printf "  %-34s -> %s\n" "$host" "${ip:-NAO_RESOLVIDO}"
  [ -n "$ip" ]
done

echo ""
echo "[1.3] Ping ICMP entre microsservicos resolvendo por nome DNS dinamico:"
docker exec vinheria-quality-iot ping -c 1 -W 2 notification.vinheria.local | grep -E "PING|bytes from"
docker exec vinheria-quality-iot ping -c 1 -W 2 esp32-sensor-01.vinheria.local | grep -E "PING|bytes from"

echo ""
echo "============================================================================"
echo "2. VALIDACAO AUTENTICACAO JWT RS256 + RBAC + COMUNICACAO ENTRE SERVICOS"
echo "============================================================================"
echo "[2.1] Sem token -> deve retornar HTTP 401:"
CODE_NO_AUTH="$(curl -s -o /dev/null -w "%{http_code}" --cacert "$CA_CERT" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H "Content-Type: application/json" \
  -d '{"temperatura":14.5,"umidade":68.0,"luminosidade":5.0}')"
echo "  HTTP ${CODE_NO_AUTH}"
[ "$CODE_NO_AUTH" = "401" ]

echo "[2.2] Token JWT invalido/adulterado -> deve retornar HTTP 401:"
CODE_BAD_JWT="$(curl -s -o /dev/null -w "%{http_code}" --cacert "$CA_CERT" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H "Authorization: Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhdHRhY2tlciIsInJvbGVzIjpbIlJPTEVfRU5PTE9HTyJdfQ." \
  -H "Content-Type: application/json" \
  -d '{"temperatura":14.5,"umidade":68.0,"luminosidade":5.0}')"
echo "  HTTP ${CODE_BAD_JWT}"
[ "$CODE_BAD_JWT" = "401" ]

echo "[2.3] Login com ROLE_CLIENTE -> deve receber HTTP 403 Forbidden ao tentar enviar telemetria:"
CLI_TOKEN="$(curl -sf --cacert "$CA_CERT" -X POST https://localhost:8443/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"cliente","password":"Cliente@2026"}' | jq -r '.access_token')"
CODE_RBAC="$(curl -s -o /dev/null -w "%{http_code}" --cacert "$CA_CERT" \
  -X POST https://localhost:8443/api/v1/telemetry \
  -H "Authorization: Bearer ${CLI_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"temperatura":14.5,"umidade":68.0,"luminosidade":5.0}')"
echo "  HTTP ${CODE_RBAC}"
[ "$CODE_RBAC" = "403" ]

echo "[2.4] Login com ROLE_ENOLOGO + envio de telemetria critica via HTTPS -> deve acionar Notification Service:"
ENO_TOKEN="$(curl -sf --cacert "$CA_CERT" -X POST https://localhost:8443/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"enologo","password":"Agnello@2026"}' | jq -r '.access_token')"
curl -sf --cacert "$CA_CERT" -X POST https://localhost:8443/api/v1/telemetry \
  -H "Authorization: Bearer ${ENO_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"tanqueOuAdegaId":"ADEGA-BARRIQUE-03","sensorId":"ESP32-DEV1-GPIO34","temperatura":19.8,"umidade":52.4,"luminosidade":18.5}' | jq .

echo "[2.5] Consultando alertas persistidos no Notification Service (Database per Service):"
curl -sf --cacert "$CA_CERT" -H "Authorization: Bearer ${ENO_TOKEN}" \
  https://localhost:8443/api/v1/alerts | jq '{count, latest: .items[0]}'

echo ""
echo "============================================================================"
echo "3. VALIDACAO PIPELINE JENKINS + PASTA DE PUBLICACAO (SIMULACAO IIS)"
echo "============================================================================"
"${ROOT_DIR}/scripts/trigger_jenkins_build.sh"

echo ""
echo "[3.1] Verificando artefatos publicados em http://localhost:8088/release.json:"
curl -sf http://localhost:8088/release.json | jq .

echo ""
echo "============================================================================"
echo "4. CAPTURA DE PACOTES WIRESHARK (HTTP INSEGURO vs HTTPS TLS + DHCP/DNS)"
echo "============================================================================"
"${ROOT_DIR}/scripts/run_security_demo.sh"

echo ""
echo "============================================================================"
echo "TODAS AS VALIDACOES CONCLUIDAS COM SUCESSO!"
echo "============================================================================"
