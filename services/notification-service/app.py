"""Notification Service - Vinheria Agnello.

Responsabilidades:
- Receber eventos AlertaQualidadeTermicaDisparado via REST (HTTP/HTTPS).
- Validar assinatura criptografica JWT (RS256) e politicas RBAC.
- Deduplicar e persistir alertas em SQLite isolado (Database per Service).
- Disponibilizar historico de alertas para o painel do enologo/gestor.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from typing import Any

import jwt
from flask import Flask, g, jsonify, request

app = Flask(__name__)

JWT_ISSUER = "vinheria-agnello-auth"
PUBLIC_KEY_PATH = os.environ.get("JWT_PUBLIC_KEY_PATH", "/certs/jwt_public.pem")
DB_PATH = os.environ.get("NOTIFICATION_DB_PATH", "/data/notifications.db")


def init_db(db_path: str | None = None) -> None:
    path = db_path or DB_PATH
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                received_at TEXT NOT NULL,
                origem TEXT NOT NULL,
                adega_id TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                severidade TEXT NOT NULL,
                risco_quimico TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                dispatched_by TEXT NOT NULL,
                transport_mode TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _load_public_key() -> str:
    with open(PUBLIC_KEY_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def verify_jwt_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        _load_public_key(),
        algorithms=["RS256"],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "iat", "sub", "roles"]},
    )


def require_auth(allowed_roles: set[str]):
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
            if not user_roles.intersection(allowed_roles):
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


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "service": "notification-service",
            "fqdn": "notification.vinheria.local",
            "hostname": socket.gethostname(),
            "status": "UP",
            "auth": "JWT-RS256-Verified",
        }
    )


@app.route("/api/v1/alerts", methods=["POST"])
@require_auth({"ROLE_SERVICE_QUALITY", "ROLE_ENOLOGO"})
def receive_alert():
    event = request.get_json(silent=True)
    if not isinstance(event, dict) or "eventId" not in event or "payload" not in event:
        return jsonify({"error": "Contrato de evento invalido (eventId e payload obrigatorios)"}), 400

    payload = event["payload"]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    transport_mode = request.headers.get("X-Transport-Mode", "secure" if request.is_secure else "insecure")

    init_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO alerts
                (event_id, event_type, timestamp, received_at, origem, adega_id,
                 sensor_id, severidade, risco_quimico, payload_json, dispatched_by, transport_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event["eventId"]),
                    str(event.get("eventType", "AlertaQualidadeTermicaDisparado")),
                    str(event.get("timestamp", now_iso)),
                    now_iso,
                    str(event.get("origem", "QualityIoTService")),
                    str(payload.get("tanqueOuAdegaId", "DESCONHECIDA")),
                    str(payload.get("sensorId", "DESCONHECIDO")),
                    str(payload.get("severidade", "ALERTA")),
                    str(payload.get("riscoQuimico", "")),
                    json.dumps(payload, ensure_ascii=False),
                    g.claims["sub"],
                    transport_mode,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return (
            jsonify(
                {
                    "status": "DUPLICATE_IGNORED",
                    "eventId": event["eventId"],
                    "message": "Evento ja processado (deduplicacao ativa)",
                }
            ),
            200,
        )

    return (
        jsonify(
            {
                "status": "ALERT_DISPATCHED",
                "eventId": event["eventId"],
                "channels": ["EMAIL_ENOLOGO", "PAINEL_ADEGA", "LOG_AUDITORIA"],
                "authenticatedCaller": g.claims["sub"],
                "transportMode": transport_mode,
                "receivedAt": now_iso,
            }
        ),
        201,
    )


@app.route("/api/v1/alerts", methods=["GET"])
@require_auth({"ROLE_ENOLOGO", "ROLE_GESTOR", "ROLE_OPERADOR_ADEGA"})
def list_alerts():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM alerts ORDER BY received_at DESC LIMIT 50").fetchall()
    return jsonify(
        {
            "count": len(rows),
            "items": [
                {
                    "eventId": r["event_id"],
                    "eventType": r["event_type"],
                    "timestamp": r["timestamp"],
                    "receivedAt": r["received_at"],
                    "origem": r["origem"],
                    "adegaId": r["adega_id"],
                    "sensorId": r["sensor_id"],
                    "severidade": r["severidade"],
                    "riscoQuimico": r["risco_quimico"],
                    "payload": json.loads(r["payload_json"]),
                    "dispatchedBy": r["dispatched_by"],
                    "transportMode": r["transport_mode"],
                }
                for r in rows
            ],
        }
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5002)
