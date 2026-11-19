"""Testes unitarios dos microsservicos da Vinheria Agnello.

Valida:
1. Regras bioquimicas da adega (Arrhenius, desidratacao de rolha, Gout de Lumiere).
2. Emissao e validacao criptografica de JWT RS256 e endpoint JWKS.
3. Enforcement de RBAC (401 sem token/invalido, 403 papel nao autorizado, 201 autorizado).
4. Deduplicacao de alertas no Notification Service.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VinheriaServicesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmpdir.name)

        # Gera par RSA-2048 efemero isolado para os testes unitarios
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        cls.priv_path = tmp / "jwt_private.pem"
        cls.pub_path = tmp / "jwt_public.pem"
        cls.priv_path.write_bytes(priv_pem)
        cls.pub_path.write_bytes(pub_pem)

        os.environ["JWT_PRIVATE_KEY_PATH"] = str(cls.priv_path)
        os.environ["JWT_PUBLIC_KEY_PATH"] = str(cls.pub_path)
        os.environ["QUALITY_DB_PATH"] = str(tmp / "quality.db")
        os.environ["NOTIFICATION_DB_PATH"] = str(tmp / "notification.db")

        cls.quality_mod = _load_module(
            "quality_app", REPO_ROOT / "services" / "quality-iot-service" / "app.py"
        )
        cls.notif_mod = _load_module(
            "notif_app", REPO_ROOT / "services" / "notification-service" / "app.py"
        )

        cls.quality_mod.init_db()
        cls.notif_mod.init_db()
        cls.quality_client = cls.quality_mod.app.test_client()
        cls.notif_client = cls.notif_mod.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmpdir.cleanup()

    def test_ideal_cellar_conditions_return_normal(self) -> None:
        res = self.quality_mod.evaluate_cellar_telemetry(14.5, 68.2, 8.0)
        self.assertEqual(res["severidade"], "NORMAL")
        self.assertEqual(res["riscos"], [])

    def test_critical_cellar_conditions_detect_all_three_degradation_risks(self) -> None:
        res = self.quality_mod.evaluate_cellar_telemetry(19.8, 52.4, 35.0)
        self.assertEqual(res["severidade"], "CRITICO")
        combined = " ".join(res["riscos"])
        self.assertIn("Arrhenius", combined)
        self.assertIn("rolhas", combined)
        self.assertIn("Gout de Lumiere", combined)

    def test_login_issues_rs256_jwt_and_jwks_exposes_rsa_key(self) -> None:
        resp = self.quality_client.post(
            "/api/v1/auth/login",
            json={"username": "enologo", "password": os.environ.get("LAB_ENOLOGO_PASS", "Agnello@2026")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["algorithm"], "RS256")
        self.assertIn("ROLE_ENOLOGO", data["roles"])

        header = jwt.get_unverified_header(data["access_token"])
        self.assertEqual(header["alg"], "RS256")

        jwks_resp = self.quality_client.get("/.well-known/jwks.json")
        self.assertEqual(jwks_resp.status_code, 200)
        keys = jwks_resp.get_json()["keys"]
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["kty"], "RSA")
        self.assertEqual(keys[0]["alg"], "RS256")

    def test_telemetry_requires_auth_and_enforces_rbac(self) -> None:
        # 1) Sem token -> 401
        r_no_auth = self.quality_client.post(
            "/api/v1/telemetry",
            json={"temperatura": 14.5, "umidade": 68.0, "luminosidade": 5.0},
        )
        self.assertEqual(r_no_auth.status_code, 401)

        # 2) Token forjado (alg=none) -> 401
        forged = jwt.encode({"sub": "attacker", "roles": ["ROLE_ENOLOGO"]}, key="", algorithm="none")
        r_forged = self.quality_client.post(
            "/api/v1/telemetry",
            headers={"Authorization": f"Bearer {forged}"},
            json={"temperatura": 14.5, "umidade": 68.0, "luminosidade": 5.0},
        )
        self.assertEqual(r_forged.status_code, 401)

        # 3) Papel cliente -> 403 Forbidden
        cli_token = self.quality_mod.issue_jwt("cliente", ["ROLE_CLIENTE"])
        r_forbidden = self.quality_client.post(
            "/api/v1/telemetry",
            headers={"Authorization": f"Bearer {cli_token}"},
            json={"temperatura": 14.5, "umidade": 68.0, "luminosidade": 5.0},
        )
        self.assertEqual(r_forbidden.status_code, 403)

        # 4) Papel enologo com leitura critica -> 201 e dispara alerta para Notification Service
        eno_token = self.quality_mod.issue_jwt("enologo", ["ROLE_ENOLOGO"])
        with patch.object(
            self.quality_mod,
            "_dispatch_alert",
            return_value={"dispatched": True, "status_code": 201},
        ) as mocked_dispatch:
            r_ok = self.quality_client.post(
                "/api/v1/telemetry",
                headers={"Authorization": f"Bearer {eno_token}"},
                json={
                    "tanqueOuAdegaId": "ADEGA-BARRIQUE-03",
                    "sensorId": "ESP32-DEV1-GPIO34",
                    "temperatura": 19.8,
                    "umidade": 52.4,
                    "luminosidade": 18.0,
                },
            )
            self.assertEqual(r_ok.status_code, 201)
            self.assertEqual(r_ok.get_json()["severidade"], "CRITICO")
            mocked_dispatch.assert_called_once()

    def test_notification_service_validates_rs256_rbac_and_deduplicates(self) -> None:
        svc_token = self.quality_mod.issue_jwt("quality-iot-service", ["ROLE_SERVICE_QUALITY"])
        cli_token = self.quality_mod.issue_jwt("cliente", ["ROLE_CLIENTE"])

        event = {
            "eventId": "evt-unit-test-001",
            "eventType": "AlertaQualidadeTermicaDisparado",
            "timestamp": "2026-11-19T12:00:00Z",
            "origem": "QualityIoTService",
            "payload": {
                "tanqueOuAdegaId": "ADEGA-BARRIQUE-03",
                "sensorId": "ESP32-DEV1-GPIO34",
                "severidade": "CRITICO",
                "riscoQuimico": "Aceleracao cinetica de Arrhenius",
            },
        }

        # Cliente nao pode postar alertas -> 403
        r_denied = self.notif_client.post(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {cli_token}"},
            json=event,
        )
        self.assertEqual(r_denied.status_code, 403)

        # Servico Quality autorizado -> 201
        r_first = self.notif_client.post(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {svc_token}"},
            json=event,
        )
        self.assertEqual(r_first.status_code, 201)
        self.assertEqual(r_first.get_json()["status"], "ALERT_DISPATCHED")

        # Mesmo eventId -> 200 DUPLICATE_IGNORED
        r_dup = self.notif_client.post(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {svc_token}"},
            json=event,
        )
        self.assertEqual(r_dup.status_code, 200)
        self.assertEqual(r_dup.get_json()["status"], "DUPLICATE_IGNORED")


if __name__ == "__main__":
    unittest.main()
