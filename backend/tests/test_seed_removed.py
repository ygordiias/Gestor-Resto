"""Segurança (Etapa 1, item 4): a rota POST /api/setup/seed foi removida.

Requer o backend rodando em TEST_BACKEND_URL (padrão http://localhost:8001)
apontando para um banco de TESTE.
"""
import os

import requests

BASE_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8001")


def test_seed_route_does_not_exist():
    r = requests.post(f"{BASE_URL}/api/setup/seed", timeout=10)
    assert r.status_code in (404, 405), f"esperava 404/405, veio {r.status_code}"
