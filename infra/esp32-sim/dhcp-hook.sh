#!/bin/sh
set -eu

EVENT="${1:-unknown}"
echo "[DHCP-HOOK] Evento=${EVENT} IP=${ip:-none} SUBNET=${subnet:-none} DNS=${dns:-none} DOMAIN=${domain:-none} LEASE=${lease:-none}"

if [ "$EVENT" = "bound" ] || [ "$EVENT" = "renew" ]; then
  ip addr replace "${ip}/24" dev "${interface:-eth0}" label "${interface:-eth0}:dhcp" 2>/dev/null || true
  cat > /tmp/dhcp-lease.json <<EOF
{
  "hostname": "esp32-sensor-01",
  "fqdn": "esp32-sensor-01.${domain:-vinheria.local}",
  "ip": "${ip}",
  "subnet": "${subnet:-255.255.255.0}",
  "router": "${router:-172.28.0.1}",
  "dns": "${dns:-172.28.0.53}",
  "lease_seconds": "${lease:-43200}"
}
EOF
  echo "[DHCP-HOOK] Lease gravado em /tmp/dhcp-lease.json e IP ${ip}/24 vinculado em ${interface:-eth0}:dhcp"
fi
