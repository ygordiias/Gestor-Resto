"""Etapa 1, item 2: superadmin inicial só por variáveis de ambiente.

Teste unitário, sem rede e sem MongoDB (banco falso em memória).
Rodar: cd backend && python -m pytest tests/test_bootstrap_superadmin.py
"""
import asyncio
import logging
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bootstrap import ensure_initial_superadmin  # noqa: E402

PASSWORD = uuid.uuid4().hex  # gerada na hora; nunca fixa no código


class _Result:
    def __init__(self, upserted_id):
        self.upserted_id = upserted_id


class FakeUsers:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None

    async def update_one(self, query, update, upsert=False):
        if await self.find_one(query):
            return _Result(None)
        self.docs.append(dict(update["$setOnInsert"]))
        return _Result("new")


class BrokenUsers:
    async def find_one(self, *a, **k):
        raise RuntimeError("db down")


class FakeDB:
    def __init__(self, users):
        self.users = users


def _hash(p):
    return "hashed:" + str(len(p))


def _run(users, env, caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test-bootstrap")
    return asyncio.run(ensure_initial_superadmin(FakeDB(users), logger, env=env, hash_password=_hash))


def _env(email="dono@example.invalid", password=PASSWORD):
    return {"INITIAL_SUPERADMIN_EMAIL": email, "INITIAL_SUPERADMIN_PASSWORD": password}


def test_existing_superadmin_is_left_alone(caplog):
    users = FakeUsers([{"id": "1", "email": "x@example.invalid", "role": "superadmin"}])
    assert _run(users, _env(), caplog) == "exists"
    assert len(users.docs) == 1


def test_missing_env_only_warns(caplog):
    users = FakeUsers()
    assert _run(users, {}, caplog) == "missing_env"
    assert users.docs == []
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_short_password_is_rejected(caplog):
    users = FakeUsers()
    assert _run(users, _env(password="curta"), caplog) == "invalid_env"
    assert users.docs == []


def test_existing_email_is_not_promoted(caplog):
    users = FakeUsers([{"id": "1", "email": "dono@example.invalid", "role": "admin"}])
    assert _run(users, _env(), caplog) == "email_conflict"
    assert users.docs[0]["role"] == "admin"
    assert len(users.docs) == 1
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_creates_superadmin_with_hash(caplog):
    users = FakeUsers()
    assert _run(users, _env(), caplog) == "created"
    (doc,) = users.docs
    assert doc["role"] == "superadmin"
    assert doc["is_active"] is True
    assert doc["password"] == _hash(PASSWORD)
    assert PASSWORD not in str(doc)


def test_password_never_logged(caplog):
    for users, env in [(FakeUsers(), _env()), (FakeUsers(), _env(password=PASSWORD[:5]))]:
        _run(users, env, caplog)
    assert PASSWORD not in caplog.text
    assert PASSWORD[:5] not in caplog.text


def test_db_error_does_not_raise(caplog):
    assert _run(BrokenUsers(), _env(), caplog) == "error"
