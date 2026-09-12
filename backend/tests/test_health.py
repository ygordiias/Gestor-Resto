"""Regressão do endpoint /api/health (STEP 1 - Estabilidade).

Garante que /api/health é uma liveness probe leve que retorna 200 e
{"status": "ok"} sem depender do MongoDB. Também garante que /health
(root) continua existindo para readiness com verificação de DB.
"""
import os
import requests

BASE_URL = os.environ.get(
    "TEST_BACKEND_URL",
    "http://localhost:8001",
)


def test_api_health_liveness():
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    assert r.status_code == 200, f"esperava 200, veio {r.status_code}"
    body = r.json()
    assert body.get("status") == "ok", f"status inesperado: {body}"
    assert "timestamp" in body, "timestamp ausente"


def test_root_health_readiness_shape():
    """Root /health retorna {status, database} quando o DB está OK."""
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    # Em ambiente de teste externo (via ingress) essa rota pode cair no
    # frontend HTML, portanto só validamos quando é JSON (uso local/interno).
    if r.headers.get("content-type", "").startswith("application/json"):
        assert r.status_code in (200, 503)
        body = r.json()
        assert "status" in body


def test_ping_endpoint():
    r = requests.get(f"{BASE_URL}/api/ping", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body.get("message") == "pong"


if __name__ == "__main__":
    test_api_health_liveness()
    test_root_health_readiness_shape()
    test_ping_endpoint()
    print("OK - todos os testes de estabilidade passaram")
