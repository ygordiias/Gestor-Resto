"""Segurança (Etapa 1, item 5): login e perfil exigidos nas rotas antes abertas.

Teste OFFLINE: não precisa de servidor rodando nem de MongoDB.
- Importa o app com MONGO_URL apontando para um endereço inexistente
  (o driver só conecta quando usado; o startup não é executado).
- Troca o banco por um falso em memória, só com os usuários de teste.
- Chama o app ASGI direto, sem rede.

Rodar: cd backend && python -m pytest tests/test_route_permissions.py
"""
import asyncio
import json
import os
import secrets
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ambiente isolado para o import: nunca usar o banco real neste teste.
_saved_env = {k: os.environ.get(k) for k in ("MONGO_URL", "DB_NAME", "SECRET_KEY")}
os.environ["MONGO_URL"] = "mongodb://127.0.0.1:1"
os.environ["DB_NAME"] = "teste_offline_permissoes"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
import server  # noqa: E402

for _k, _v in _saved_env.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v

ROLES = ["superadmin", "admin", "waiter", "cashier", "kitchen", "bar"]
USERS = {r: {"id": f"user-{r}", "name": r, "email": f"{r}@example.invalid", "role": r} for r in ROLES}


class _Users:
    async def find_one(self, query, projection=None):
        for u in USERS.values():
            if u["id"] == query.get("id"):
                return dict(u)
        return None


class _Empty:
    async def find_one(self, *a, **k):
        return None


class _FakeDB:
    users = _Users()
    tables = _Empty()
    orders = _Empty()

    def __getattr__(self, name):  # qualquer outra coleção: vazia
        return _Empty()


server.db = _FakeDB()


def _call(method, path, token=None, body=None):
    """Executa uma requisição HTTP no app ASGI e devolve o status."""
    headers = [(b"content-type", b"application/json")]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    raw = json.dumps(body if body is not None else {}).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": headers,
        "client": ("127.0.0.1", 1), "server": ("testserver", 80),
    }
    sent = {"done": False}
    result = {}

    async def receive():
        if not sent["done"]:
            sent["done"] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]

    asyncio.run(server.app(scope, receive, send))
    return result["status"]


def _token(role):
    return server.create_access_token({"sub": USERS[role]["id"]})


X = uuid.uuid4().hex  # id inexistente: a checagem de perfil vem antes da busca

# (método, caminho, perfis permitidos além do superadmin, corpo)
STAFF = {"admin", "waiter", "cashier", "kitchen", "bar"}
PROTECTED = [
    ("GET", "/api/categories", STAFF, None),
    ("GET", "/api/products", STAFF, None),
    ("GET", f"/api/products/{X}", STAFF, None),
    ("GET", "/api/tables", STAFF, None),
    ("PUT", f"/api/tables/{X}", {"admin", "waiter", "cashier"}, {"status": "available"}),
    ("PUT", f"/api/tables/{X}/status", {"admin", "waiter", "cashier"}, {"status": "available"}),
    ("POST", f"/api/tables/{X}/request-cleaning", {"admin", "waiter", "cashier"}, None),
    ("GET", "/api/orders", {"admin"}, None),
    ("GET", "/api/orders/open", STAFF, None),
    ("GET", f"/api/orders/table/{X}", STAFF, None),
    ("GET", f"/api/orders/{X}", STAFF, None),
    ("PUT", f"/api/orders/{X}/item/{X}/status", {"admin", "kitchen", "bar", "waiter"}, {"status": "ready"}),
    ("POST", f"/api/orders/{X}/close", {"admin", "cashier"}, {"payments": []}),
    ("POST", f"/api/orders/{X}/cancel-quick", {"admin"}, None),
    ("GET", "/api/stock", {"admin"}, None),
    ("GET", "/api/stock/alerts", {"admin"}, None),
    ("GET", "/api/cash-register/current", {"admin", "cashier"}, None),
    ("GET", "/api/invoices", {"admin", "cashier"}, None),
    ("POST", "/api/invoices", {"admin", "cashier"}, {"order_id": X}),
]


@pytest.mark.parametrize("method,path,allowed,body", PROTECTED, ids=[f"{m} {p}" for m, p, _, _ in PROTECTED])
def test_without_token_is_refused(method, path, allowed, body):
    assert _call(method, path, body=body) in (401, 403)


@pytest.mark.parametrize("method,path,allowed,body", PROTECTED, ids=[f"{m} {p}" for m, p, _, _ in PROTECTED])
def test_wrong_role_is_forbidden(method, path, allowed, body):
    for role in ROLES:
        if role == "superadmin" or role in allowed:
            continue
        status = _call(method, path, token=_token(role), body=body)
        assert status == 403, f"{role} em {method} {path}: esperava 403, veio {status}"


def test_invalid_token_is_refused():
    assert _call("GET", "/api/orders/open", token="token-invalido") == 401


@pytest.mark.parametrize("role", ["waiter", "cashier"])
@pytest.mark.parametrize("field,value", [("capacity", 8), ("table_type", "event"), ("note", "x"), ("number", 99)])
def test_waiter_and_cashier_cannot_change_table_fields(role, field, value):
    status = _call("PUT", f"/api/tables/{X}", token=_token(role), body={"status": "available", field: value})
    assert status == 403


@pytest.mark.parametrize("role", ["waiter", "cashier", "admin", "superadmin"])
def test_status_only_update_passes_permission(role):
    # Mesa inexistente no banco falso: passar da permissão resulta em 404.
    assert _call("PUT", f"/api/tables/{X}", token=_token(role), body={"status": "available"}) == 404


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_admin_can_send_other_table_fields(role):
    status = _call("PUT", f"/api/tables/{X}", token=_token(role), body={"capacity": 8})
    assert status == 404  # passou da permissão; mesa inexistente


@pytest.mark.parametrize("path", ["/api/health", "/api/ping", "/api/"])
def test_public_routes_stay_public(path):
    assert _call("GET", path) == 200


def test_seed_route_removed():
    assert _call("POST", "/api/setup/seed") in (404, 405)


@pytest.mark.parametrize("path", ["/api/auth/register", "/api/register"])
def test_register_routes_removed(path):
    assert _call("POST", path, body={"name": "x", "email": "x@example.invalid", "password": "x", "role": "admin"}) in (404, 405)
