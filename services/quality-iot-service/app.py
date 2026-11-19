"""Quality & IoT Service - Vinheria Agnello.

Responsabilidades:
- Autenticacao de usuarios e emissao de tokens JWT assimetricos (RS256) + JWKS.
- Ingestao de telemetria IoT (ESP32 DevKit V1 / DHT22 / LDR - Grupo 55).
- Avaliacao bioquimica da adega (Arrhenius, desidratacao de rolha, Gout de Lumiere).
- Persistencia isolada em SQLite (Database per Service).
- Despacho de eventos AlertaQualidadeTermicaDisparado para notification.vinheria.local.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from flask import Flask, g, jsonify, request

app = Flask(__name__)

JWT_ISSUER = "vinheria-agnello-auth"
JWT_KID = "vinheria-rs256-2026"
JWT_EXP_MINUTES = 60

PRIVATE_KEY_PATH = os.environ.get("JWT_PRIVATE_KEY_PATH", "/certs/jwt_private.pem")
PUBLIC_KEY_PATH = os.environ.get("JWT_PUBLIC_KEY_PATH", "/certs/jwt_public.pem")
CA_CERT_PATH = os.environ.get("VINHERIA_CA_CERT", "/certs/ca.crt")
DB_PATH = os.environ.get("QUALITY_DB_PATH", "/data/quality_iot.db")

NOTIFICATION_HTTP_URL = os.environ.get(
    "NOTIFICATION_HTTP_URL", "http://notification.vinheria.local:5002/api/v1/alerts"
)
NOTIFICATION_HTTPS_URL = os.environ.get(
    "NOTIFICATION_HTTPS_URL", "https://notification.vinheria.local:5444/api/v1/alerts"
)

# Credenciais de laboratorio armazenadas com hash PBKDF2-SHA256 (nunca texto puro)
_LAB_SALT = b"vinheria-agnello-fiap-rm554976"


def _hash_password(raw: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), _LAB_SALT, 100_000).hex()


USERS_DB: dict[str, dict[str, Any]] = {
    "enologo": {
        "password_hash": _hash_password(os.environ.get("LAB_ENOLOGO_PASS", "Agnello@2026")),
        "roles": ["ROLE_ENOLOGO", "ROLE_OPERADOR_ADEGA"],
        "display_name": "Felipe Castro Lima (Enologo)",
    },
    "operador": {
        "password_hash": _hash_password(os.environ.get("LAB_OPERADOR_PASS", "Adega@2026")),
        "roles": ["ROLE_OPERADOR_ADEGA"],
        "display_name": "Operador Adega Barrique",
    },
    "gestor": {
        "password_hash": _hash_password(os.environ.get("LAB_GESTOR_PASS", "Gestor@2026")),
        "roles": ["ROLE_GESTOR"],
        "display_name": "Gestor Vinheria Agnello",
    },
    "cliente": {
        "password_hash": _hash_password(os.environ.get("LAB_CLIENTE_PASS", "Cliente@2026")),
        "roles": ["ROLE_CLIENTE"],
        "display_name": "Cliente B2B Restaurante",
    },
}


def init_db(db_path: str | None = None) -> None:
    path = db_path or DB_PATH
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_readings (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                adega_id TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                temperatura REAL NOT NULL,
                umidade REAL NOT NULL,
                luminosidade REAL NOT NULL,
                severidade TEXT NOT NULL,
                riscos_json TEXT NOT NULL,
                received_by TEXT NOT NULL,
                transport_mode TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _load_private_key() -> str:
    with open(PRIVATE_KEY_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _load_public_key() -> str:
    with open(PUBLIC_KEY_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _b64url_uint(val: int) -> str:
    raw = val.to_bytes((val.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def issue_jwt(subject: str, roles: list[str], exp_minutes: int = JWT_EXP_MINUTES) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": JWT_ISSUER,
        "sub": subject,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        _load_private_key(),
        algorithm="RS256",
        headers={"kid": JWT_KID},
    )


def verify_jwt_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        _load_public_key(),
        algorithms=["RS256"],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "roles"]},
    )


def require_auth(allowed_roles: set[str] | None = None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Token Bearer ausente ou malformado"}), 401
            token = auth_header.split(" ", 1)[1].strip()
            try:
                claims = verify_jwt_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token JWT expirado"}), 401
            except jwt.InvalidTokenError as exc:
                return jsonify({"error": f"Token JWT invalido: {exc}"}), 401

            user_roles = set(claims.get("roles", []))
            if allowed_roles and not user_roles.intersection(allowed_roles):
                return (
                    jsonify(
                        {
                            "error": "Acesso negado (RBAC)",
                            "required_any_role": sorted(allowed_roles),
                            "token_roles": sorted(user_roles),
                        }
                    ),
                    403,
                )
            g.claims = claims
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def evaluate_cellar_telemetry(temperatura: float, umidade: float, luminosidade: float) -> dict[str, Any]:
    """Aplica as regras bioquimicas da adega (relatorio_tecnico.md + fase6_atividade.docx)."""
    riscos: list[str] = []
    severidade = "NORMAL"

    def elevate(level: str) -> None:
        nonlocal severidade
        order = {"NORMAL": 0, "ALERTA": 1, "CRITICO": 2}
        if order[level] > order[severidade]:
            severidade = level

    if temperatura > 18.0:
        riscos.append("Aceleracao cinetica de Arrhenius severa (> 18.0 C) - oxidacao e maderizacao")
        elevate("CRITICO")
    elif temperatura > 16.0:
        riscos.append("Desvio termico acima da faixa ideal (> 16.0 C) - risco cinetico de Arrhenius")
        elevate("ALERTA")
    elif temperatura < 10.0:
        riscos.append("Temperatura abaixo da faixa toleravel (< 10.0 C) - risco de precipitacao tartarica")
        elevate("ALERTA")

    if umidade < 55.0:
        riscos.append("Risco critico de desidratacao de rolhas (< 55.0%) - oxidacao acetica")
        elevate("CRITICO")
    elif umidade < 60.0:
        riscos.append("Risco de desidratacao de rolhas (< 60.0%)")
        elevate("ALERTA")
    elif umidade > 85.0:
        riscos.append("Excesso de umidade (> 85.0%) - proliferacao de fungos e micotoxinas")
        elevate("ALERTA")

    if luminosidade > 30.0:
        riscos.append("Exposicao luminosa critica (> 30.0%) - Gout de Lumiere (riboflavina B2)")
        elevate("CRITICO")
    elif luminosidade > 15.0:
        riscos.append("Incidencia luminosa acima do limite (> 15.0%) - risco fitoquimico Gout de Lumiere")
        elevate("ALERTA")

    return {"severidade": severidade, "riscos": riscos}


def _dispatch_alert(event: dict[str, Any], transport_mode: str) -> dict[str, Any]:
    service_token = issue_jwt("quality-iot-service", ["ROLE_SERVICE_QUALITY"], exp_minutes=5)
    headers = {
        "Authorization": f"Bearer {service_token}",
        "Content-Type": "application/json",
        "X-Transport-Mode": transport_mode,
    }
    if transport_mode == "insecure":
        target_url = NOTIFICATION_HTTP_URL
        verify: bool | str = False
    else:
        target_url = NOTIFICATION_HTTPS_URL
        verify = CA_CERT_PATH if os.path.exists(CA_CERT_PATH) else False

    resp = requests.post(target_url, json=event, headers=headers, verify=verify, timeout=8)
    return {
        "dispatched": True,
        "target_url": target_url,
        "transport_mode": transport_mode,
        "status_code": resp.status_code,
        "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
    }


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "service": "quality-iot-service",
            "fqdn": "quality.vinheria.local",
            "hostname": socket.gethostname(),
            "status": "UP",
            "auth": "JWT-RS256",
            "downstream_dns": "notification.vinheria.local",
        }
    )


@app.route("/.well-known/jwks.json", methods=["GET"])
def jwks():
    pub = serialization.load_pem_public_key(_load_public_key().encode("utf-8"))
    numbers = pub.public_numbers()
    return jsonify(
        {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": JWT_KID,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            ]
        }
    )


@app.route("/api/v1/auth/login", methods=["POST"])
def login():
    username = None
    password = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return jsonify({"error": "Cabecalho Basic Auth invalido"}), 400
    else:
        body = request.get_json(silent=True) or {}
        username = body.get("username")
        password = body.get("password")

    if not username or not password:
        return jsonify({"error": "Informe username e password"}), 400

    record = USERS_DB.get(username)
    if not record or not hmac.compare_digest(record["password_hash"], _hash_password(password)):
        return jsonify({"error": "Credenciais invalidas"}), 401

    token = issue_jwt(username, record["roles"])
    return jsonify(
        {
            "access_token": token,
            "token_type": "Bearer",
            "algorithm": "RS256",
            "expires_in": JWT_EXP_MINUTES * 60,
            "user": username,
            "display_name": record["display_name"],
            "role": record["roles"][0],
            "roles": record["roles"],
        }
    )


@app.route("/api/v1/telemetry", methods=["POST"])
@require_auth({"ROLE_ENOLOGO", "ROLE_OPERADOR_ADEGA"})
def ingest_telemetry():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    try:
        temperatura = float(body["temperatura"])
        umidade = float(body["umidade"])
        luminosidade = float(body["luminosidade"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Campos numericos obrigatorios: temperatura, umidade, luminosidade"}), 400

    adega_id = str(body.get("tanqueOuAdegaId", "ADEGA-BARRIQUE-03"))
    sensor_id = str(body.get("sensorId", "ESP32-DEV1-GPIO34"))
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reading_id = f"tel-{uuid.uuid4().hex[:12]}"

    analysis = evaluate_cellar_telemetry(temperatura, umidade, luminosidade)
    transport_mode = request.headers.get("X-Transport-Mode", "secure" if request.is_secure else "insecure")

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO telemetry_readings
            (id, timestamp, adega_id, sensor_id, temperatura, umidade, luminosidade,
             severidade, riscos_json, received_by, transport_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading_id,
                now_iso,
                adega_id,
                sensor_id,
                temperatura,
                umidade,
                luminosidade,
                analysis["severidade"],
                json.dumps(analysis["riscos"], ensure_ascii=False),
                g.claims["sub"],
                transport_mode,
            ),
        )
        conn.commit()

    alert_result: dict[str, Any] = {"dispatched": False}
    if analysis["severidade"] in ("ALERTA", "CRITICO"):
        event = {
            "eventId": f"evt-{uuid.uuid4().hex[:12]}",
            "eventType": "AlertaQualidadeTermicaDisparado",
            "timestamp": now_iso,
            "origem": "QualityIoTService",
            "payload": {
                "tanqueOuAdegaId": adega_id,
                "sensorId": sensor_id,
                "leitura": {
                    "temperatura": temperatura,
                    "umidade": umidade,
                    "luminosidade": luminosidade,
                },
                "faixaEsperada": {
                    "temperaturaMin": 12.0,
                    "temperaturaMax": 16.0,
                    "umidadeMin": 60.0,
                    "umidadeMax": 75.0,
                    "luminosidadeMax": 15.0,
                },
                "riscoQuimico": " / ".join(analysis["riscos"]),
                "severidade": analysis["severidade"],
            },
        }
        try:
            alert_result = _dispatch_alert(event, transport_mode)
        except Exception as exc:
            alert_result = {"dispatched": False, "error": str(exc)}

    return (
        jsonify(
            {
                "readingId": reading_id,
                "timestamp": now_iso,
                "adegaId": adega_id,
                "sensorId": sensor_id,
                "leitura": {
                    "temperatura": temperatura,
                    "umidade": umidade,
                    "luminosidade": luminosidade,
                },
                "severidade": analysis["severidade"],
                "riscos": analysis["riscos"],
                "transportMode": transport_mode,
                "alertDispatch": alert_result,
            }
        ),
        201,
    )


@app.route("/api/v1/telemetry", methods=["GET"])
@require_auth({"ROLE_ENOLOGO", "ROLE_OPERADOR_ADEGA", "ROLE_GESTOR"})
def list_telemetry():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM telemetry_readings ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()
    return jsonify(
        {
            "count": len(rows),
            "items": [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "adegaId": r["adega_id"],
                    "sensorId": r["sensor_id"],
                    "temperatura": r["temperatura"],
                    "umidade": r["umidade"],
                    "luminosidade": r["luminosidade"],
                    "severidade": r["severidade"],
                    "riscos": json.loads(r["riscos_json"]),
                    "receivedBy": r["received_by"],
                    "transportMode": r["transport_mode"],
                }
                for r in rows
            ],
        }
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001)
