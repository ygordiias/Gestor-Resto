"""Apoio para testes OFFLINE: importa o app sem tocar em nenhum banco real e
chama o ASGI direto, sem rede e sem httpx.

- MONGO_URL aponta para um endereço inexistente só durante o import
  (o driver só conecta quando usado; o startup não é executado).
- SECRET_KEY de teste gerada na hora.
- Cada teste troca server.db por um banco falso (use monkeypatch).
"""
import asyncio
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_saved_env = {k: os.environ.get(k) for k in ("MONGO_URL", "DB_NAME", "SECRET_KEY")}
os.environ["MONGO_URL"] = "mongodb://127.0.0.1:1"
os.environ["DB_NAME"] = "teste_offline"
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
if len(os.environ["SECRET_KEY"]) < 32:
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
import server  # noqa: E402

for _k, _v in _saved_env.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v


def call(method, path, token=None, body=None):
    """Executa uma requisição no app ASGI. Devolve (status, json_ou_None)."""
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
    result = {"body": b""}

    async def receive():
        if not sent["done"]:
            sent["done"] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    asyncio.run(server.app(scope, receive, send))
    try:
        data = json.loads(result["body"] or b"null")
    except ValueError:
        data = None
    return result["status"], data


def token_for(user_id):
    return server.create_access_token({"sub": user_id})
