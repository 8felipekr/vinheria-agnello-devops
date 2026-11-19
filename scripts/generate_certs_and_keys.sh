#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"
mkdir -p "$CERT_DIR"

echo "[1/4] Gerando CA Interna da Vinheria Agnello..."
openssl genrsa -out "$CERT_DIR/ca.key" 2048 2>/dev/null
openssl req -x509 -new -nodes -key "$CERT_DIR/ca.key" -sha256 -days 365 \
  -subj "/C=BR/ST=SP/L=SaoPaulo/O=Vinheria Agnello/OU=DevSecOps/CN=Vinheria Agnello Internal CA" \
  -out "$CERT_DIR/ca.crt"

generate_service_cert() {
  local name="$1"
  local cn="$2"
  local san="$3"

  echo "  -> Gerando certificado X.509 para ${cn} (${san})..."
  cat > "$CERT_DIR/${name}.cnf" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C = BR
ST = SP
L = SaoPaulo
O = Vinheria Agnello
OU = Microservices
CN = ${cn}

[v3_req]
subjectAltName = ${san}
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
EOF

  openssl genrsa -out "$CERT_DIR/${name}.key" 2048 2>/dev/null
  openssl req -new -key "$CERT_DIR/${name}.key" -out "$CERT_DIR/${name}.csr" -config "$CERT_DIR/${name}.cnf"
  openssl x509 -req -in "$CERT_DIR/${name}.csr" \
    -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" -CAcreateserial \
    -out "$CERT_DIR/${name}.crt" -days 365 -sha256 \
    -extfile "$CERT_DIR/${name}.cnf" -extensions v3_req 2>/dev/null
  rm -f "$CERT_DIR/${name}.csr" "$CERT_DIR/${name}.cnf"
}

echo "[2/4] Gerando certificados TLS com SAN para Gateway e Microsservicos..."
generate_service_cert "gateway" "gateway.vinheria.local" \
  "DNS:gateway.vinheria.local,DNS:localhost,IP:172.28.0.10,IP:127.0.0.1"
generate_service_cert "quality" "quality.vinheria.local" \
  "DNS:quality.vinheria.local,DNS:quality-iot-service,IP:172.28.0.20"
generate_service_cert "notification" "notification.vinheria.local" \
  "DNS:notification.vinheria.local,DNS:notification-service,IP:172.28.0.30"

echo "[3/4] Gerando par de chaves RSA-2048 para assinatura JWT (RS256)..."
openssl genrsa -out "$CERT_DIR/jwt_private.pem" 2048 2>/dev/null
openssl rsa -in "$CERT_DIR/jwt_private.pem" -pubout -out "$CERT_DIR/jwt_public.pem" 2>/dev/null

echo "[4/4] Ajustando permissoes de leitura para containers..."
chmod 644 "$CERT_DIR"/*.crt "$CERT_DIR/jwt_public.pem"
chmod 644 "$CERT_DIR"/gateway.key "$CERT_DIR"/quality.key "$CERT_DIR"/notification.key "$CERT_DIR/jwt_private.pem"
chmod 600 "$CERT_DIR/ca.key"

echo "PKI e chaves JWT geradas com sucesso em: $CERT_DIR"
ls -la "$CERT_DIR"
