#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAP_DIR="${ROOT_DIR}/captures"
mkdir -p "$CAP_DIR"

echo "[SNIFFER] Construindo imagem leve de captura (tcpdump)..."
docker build -q -t vinheria-sniffer "${ROOT_DIR}/infra/sniffer" >/dev/null

capture_scenario() {
  local pcap_name="$1"
  local bpf_filter="$2"
  shift 2
  local cname="vinheria-cap-$$"

  rm -f "${CAP_DIR}/${pcap_name}"
  echo "[CAPTURA] Iniciando captura na bridge br-vinheria -> captures/${pcap_name} (filtro: ${bpf_filter})"
  docker run -d --rm --name "$cname" \
    --network host \
    --cap-add NET_RAW --cap-add NET_ADMIN \
    -v "${CAP_DIR}:/captures" \
    vinheria-sniffer -i br-vinheria -s 0 -U -w "/captures/${pcap_name}" ${bpf_filter} >/dev/null

  sleep 1.5
  "$@"
  sleep 1.5

  docker kill -s INT "$cname" >/dev/null 2>&1 || true
  sleep 1
  docker rm -f "$cname" >/dev/null 2>&1 || true
  chmod 644 "${CAP_DIR}/${pcap_name}" 2>/dev/null || true
  ls -lh "${CAP_DIR}/${pcap_name}"
}

echo ""
echo "============================================================================"
echo "CENARIO 1: TRAFEGO HTTP INSEGURO (SEM TLS) - EXPOSICAO EM TEXTO CLARO"
echo "============================================================================"
capture_scenario "01_inseguro_http_plaintext.pcap" "tcp port 80 or tcp port 5001 or tcp port 5002" \
  docker exec vinheria-esp32-sensor python3 /app/simulate_esp32.py \
    --mode insecure --temp 19.8 --umidade 52.4 --luminosidade 18.5

echo ""
echo "============================================================================"
echo "CENARIO 2: TRAFEGO HTTPS SEGURO (TLS 1.3 + JWT RS256) - CRIPTOGRAFADO"
echo "============================================================================"
capture_scenario "02_seguro_https_tls_jwt.pcap" "tcp port 443 or tcp port 5443 or tcp port 5444" \
  docker exec vinheria-esp32-sensor python3 /app/simulate_esp32.py \
    --mode secure --temp 19.8 --umidade 52.4 --luminosidade 18.5

echo ""
echo "============================================================================"
echo "CENARIO 3: INFRAESTRUTURA DHCP (DORA) + DNS (vinheria.local)"
echo "============================================================================"
capture_scenario "03_dns_dhcp_infra.pcap" "udp port 53 or udp port 67 or udp port 68" \
  bash -c '
    docker exec vinheria-esp32-sensor udhcpc -i eth0 -x hostname:esp32-sensor-01 -n -q -s /usr/local/bin/dhcp-hook.sh
    docker exec vinheria-esp32-sensor dig +short @172.28.0.53 quality.vinheria.local
    docker exec vinheria-esp32-sensor dig +short @172.28.0.53 notification.vinheria.local
    docker exec vinheria-esp32-sensor dig +short @172.28.0.53 esp32-sensor-01.vinheria.local
  '

echo ""
echo "============================================================================"
echo "ANALISE FORENSE AUTOMATIZADA (TSHARK / WIRESHARK)"
echo "============================================================================"

echo "--- [01_inseguro_http_plaintext.pcap] Requisicoes HTTP capturadas em texto claro ---"
tshark -r "${CAP_DIR}/01_inseguro_http_plaintext.pcap" -Y "http.request" \
  -T fields -e ip.src -e ip.dst -e tcp.dstport -e http.request.method -e http.request.uri -e http.authorization

echo ""
echo "--- [01_inseguro_http_plaintext.pcap] Busca por dados sensiveis em texto puro ---"
strings "${CAP_DIR}/01_inseguro_http_plaintext.pcap" | grep -E "Agnello@2026|Bearer eyJ|AlertaQualidadeTermicaDisparado|ADEGA-BARRIQUE-03" | head -n 10

echo ""
echo "--- [02_seguro_https_tls_jwt.pcap] Pacotes TLS capturados ---"
tshark -r "${CAP_DIR}/02_seguro_https_tls_jwt.pcap" -Y "tls" | head -n 20

echo ""
echo "--- [02_seguro_https_tls_jwt.pcap] Busca por dados sensiveis em texto puro (esperado: 0 ocorrencias) ---"
LEAK_COUNT="$(strings "${CAP_DIR}/02_seguro_https_tls_jwt.pcap" | grep -Ec "Agnello@2026|Bearer eyJ|AlertaQualidadeTermicaDisparado|ADEGA-BARRIQUE-03" || true)"
echo "Ocorrencias em texto puro no trafego HTTPS/TLS: ${LEAK_COUNT}"

echo ""
echo "--- [03_dns_dhcp_infra.pcap] Pacotes DHCP (DORA) e DNS ---"
tshark -r "${CAP_DIR}/03_dns_dhcp_infra.pcap" -Y "dhcp or dns" | head -n 25
