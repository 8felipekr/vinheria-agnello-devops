#!/usr/bin/env python3
"""Simulador do no ESP32 DevKit V1 (Grupo55 - Vinheria Agnello).

Envia telemetria DHT22 (temperatura/umidade) e LDR (luminosidade)
para o API Gateway (gateway.vinheria.local) usando modo HTTP inseguro
ou HTTPS + JWT RS256 seguro.
"""

import argparse
import json
import os
import sys
import requests

CA_BUNDLE = os.environ.get("VINHERIA_CA_CERT", "/certs/ca.crt")


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador ESP32 Vinheria Agnello")
    parser.add_argument("--mode", choices=["insecure", "secure"], default="secure")
    parser.add_argument("--username", default="enologo")
    parser.add_argument("--password", default="Agnello@2026")
    parser.add_argument("--temp", type=float, default=19.8)
    parser.add_argument("--umidade", type=float, default=52.4)
    parser.add_argument("--luminosidade", type=float, default=18.5)
    parser.add_argument("--adega", default="ADEGA-BARRIQUE-03")
    parser.add_argument("--sensor", default="ESP32-DEV1-GPIO34")
    args = parser.parse_args()

    if args.mode == "insecure":
        base_url = "http://gateway.vinheria.local:80"
        verify = False
    else:
        base_url = "https://gateway.vinheria.local:443"
        verify = CA_BUNDLE if os.path.exists(CA_BUNDLE) else False

    print(f"[ESP32] Modo={args.mode.upper()} Destino={base_url}")
    login_resp = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": args.username, "password": args.password},
        verify=verify,
        timeout=10,
    )
    login_resp.raise_for_status()
    token = login_resp.json()["access_token"]
    print(f"[ESP32] Token JWT obtido (alg={login_resp.json()['algorithm']}, role={login_resp.json()['role']})")

    payload = {
        "tanqueOuAdegaId": args.adega,
        "sensorId": args.sensor,
        "temperatura": args.temp,
        "umidade": args.umidade,
        "luminosidade": args.luminosidade,
    }
    resp = requests.post(
        f"{base_url}/api/v1/telemetry",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        verify=verify,
        timeout=10,
    )
    print(f"[ESP32] HTTP {resp.status_code}: {json.dumps(resp.json(), ensure_ascii=False)}")
    return 0 if resp.status_code in (200, 201) else 1


if __name__ == "__main__":
    sys.exit(main())
