"""Segurança (Etapa 1, item 1): não existe cadastro público de usuário.

As rotas POST /api/auth/register e POST /api/register foram removidas.
Usuários só são criados por admin/superadmin via POST /api/users.

Requer o backend rodando em TEST_BACKEND_URL (padrão http://localhost:8001)
apontando para um banco de TESTE. Nenhuma credencial fica neste arquivo.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8001")

REMOVED_ROUTES = ["/api/auth/register", "/api/register"]


def _payload(role):
    return {
        "name": "Teste Cadastro Removido",
        "email": f"removed-register-{uuid.uuid4().hex[:10]}@example.invalid",
        "password": uuid.uuid4().hex,
        "role": role,
    }


@pytest.mark.parametrize("path", REMOVED_ROUTES)
@pytest.mark.parametrize("role", ["superadmin", "admin", "waiter"])
def test_register_routes_do_not_exist(path, role):
    r = requests.post(f"{BASE_URL}{path}", json=_payload(role), timeout=10)
    assert r.status_code in (404, 405), (
        f"{path} deveria não existir; veio {r.status_code}"
    )
    assert "access_token" not in r.text


def test_create_user_requires_auth():
    """POST /api/users sem token não cria usuário."""
    r = requests.post(f"{BASE_URL}/api/users", json=_payload("waiter"), timeout=10)
    assert r.status_code in (401, 403), f"esperava 401/403, veio {r.status_code}"
