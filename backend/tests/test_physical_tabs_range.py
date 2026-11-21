"""Faixa das comandas físicas (200 a 291). Teste OFFLINE: banco falso em memória.

- Vincular 200, 230, 231 e 291 funciona; 292 (e 199) é recusada com 400.
- O cadastro automático (startup) cria só 231 a 291 sem tocar nas 200 a 230
  existentes nem nos vínculos abertos.
- O script criar_comandas_faltantes.py rodado duas vezes não duplica nada.
- POST /tabs/range fica limitado à mesma faixa.

Rodar: cd backend && python -m pytest tests/test_physical_tabs_range.py
"""
import asyncio
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from _offline_app import call, server, token_for  # noqa: E402
import criar_comandas_faltantes as script  # noqa: E402
import physical_tabs  # noqa: E402


# ---------- banco falso mínimo ----------
def _match(doc, query):
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                if op == "$ne" and value == arg:
                    return False
                if op == "$gte" and not (value is not None and value >= arg):
                    return False
                if op == "$lte" and not (value is not None and value <= arg):
                    return False
                if op == "$exists" and (key in doc) != bool(arg):
                    return False
        elif value != cond:
            return False
    return True


class _Res:
    def __init__(self, matched=0, upserted_id=None):
        self.matched_count = self.modified_count = matched
        self.upserted_id = upserted_id


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key) or 0, reverse=direction == -1)
        return self

    async def to_list(self, n=None):
        return self.docs

    def __iter__(self):  # uso síncrono (pymongo) no script
        return iter(self.docs)


class SyncCol:
    """Coleção com a API síncrona do pymongo (usada pelo script)."""

    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, query=None, projection=None):
        return _Cursor([copy.deepcopy(d) for d in self.docs if _match(d, query or {})])

    def find_one(self, query, projection=None):
        for d in self.docs:
            if _match(d, query):
                return copy.deepcopy(d)
        return None

    def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                return _Res(matched=1)
        if upsert:
            new = {k: v for k, v in query.items() if not isinstance(v, dict)}
            new.update(update.get("$setOnInsert", {}))
            new.update(update.get("$set", {}))
            new["_id"] = len(self.docs) + 1
            self.docs.append(new)
            return _Res(upserted_id=new["_id"])
        return _Res()

    def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))
        return _Res(matched=1)


class AsyncCol(SyncCol):
    """Mesma coleção com a API do motor (usada pelo servidor)."""

    async def find_one(self, query, projection=None):
        return SyncCol.find_one(self, query)

    async def update_one(self, query, update, upsert=False):
        return SyncCol.update_one(self, query, update, upsert)

    async def insert_one(self, doc):
        return SyncCol.insert_one(self, doc)


class FakeDB:
    def __init__(self, tabs, tables, users):
        self.physical_tabs = AsyncCol(tabs)
        self.tables = AsyncCol(tables)
        self.orders = AsyncCol()
        self.users = AsyncCol(users)


ADMIN = {"id": "u-admin", "name": "Admin", "email": "a@x", "role": "admin", "is_active": True}
WAITER = {"id": "u-waiter", "name": "Garçom", "email": "g@x", "role": "waiter", "is_active": True}


def _existing_tabs():
    """200 a 230 como hoje em produção; a 205 com vínculo aberto."""
    tabs = [physical_tabs.new_tab_doc(n) for n in range(200, 231)]
    tabs[5].update({"active_order_id": "pedido-aberto-205", "table_id": "mesa-antiga"})
    return tabs


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("PHYSICAL_TAB_MIN", raising=False)
    monkeypatch.delenv("PHYSICAL_TAB_MAX", raising=False)
    tables = [{"id": f"t{i}", "number": i, "status": "available"} for i in range(1, 8)]
    fake = FakeDB(_existing_tabs(), tables, [ADMIN, WAITER])
    monkeypatch.setattr(server, "db", fake)

    async def no_emit(*a, **k):
        return None

    async def no_tables():
        return []

    monkeypatch.setattr(server.sio, "emit", no_emit)
    monkeypatch.setattr(server, "get_tables", no_tables)
    # Startup: o cadastro automático cria só o que falta (231 a 291).
    created = asyncio.run(physical_tabs.ensure_tabs(fake.physical_tabs))
    assert created == 61
    return fake


def _link(table_id, number, user=WAITER):
    return call("POST", f"/api/tables/{table_id}/tabs", token_for(user["id"]), {"tab_number": number})


def _tab(db, number):
    return next((d for d in db.physical_tabs.docs if d["number"] == number), None)


# ---------- faixa ----------
def test_default_range_is_200_to_291(monkeypatch):
    monkeypatch.delenv("PHYSICAL_TAB_MIN", raising=False)
    monkeypatch.delenv("PHYSICAL_TAB_MAX", raising=False)
    assert physical_tabs.tab_range() == (200, 291)


def test_range_from_env_and_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("PHYSICAL_TAB_MIN", "300")
    monkeypatch.setenv("PHYSICAL_TAB_MAX", "350")
    assert physical_tabs.tab_range() == (300, 350)
    monkeypatch.setenv("PHYSICAL_TAB_MAX", "abc")
    assert physical_tabs.tab_range() == (200, 291)  # 300 > 291 -> faixa inválida -> padrão
    monkeypatch.setenv("PHYSICAL_TAB_MIN", "250")
    monkeypatch.setenv("PHYSICAL_TAB_MAX", "240")
    assert physical_tabs.tab_range() == (200, 291)


def test_config_route_returns_range(db):
    status, body = call("GET", "/api/tabs/config", token_for(WAITER["id"]))
    assert status == 200 and body == {"min": 200, "max": 291}


# ---------- vínculo ----------
@pytest.mark.parametrize("number,table", [(231, "t1"), (291, "t2"), (200, "t3"), (230, "t4")])
def test_link_inside_range_works(db, number, table):
    status, body = _link(table, number)
    assert status == 200, body
    assert body["tab_number"] == number and body["table_id"] == table
    tab = _tab(db, number)
    assert tab["active_order_id"] == body["id"] and tab["table_id"] == table
    assert any(o["id"] == body["id"] for o in db.orders.docs)


@pytest.mark.parametrize("number", [292, 199])
def test_link_outside_range_is_400(db, number):
    status, body = _link("t1", number)
    assert status == 400
    assert body["detail"] == f"Comanda {number} fora da faixa permitida (200 a 291)"
    assert db.orders.docs == []
    assert _tab(db, number) is None  # nada foi criado


def test_existing_tabs_and_open_links_untouched(db):
    # O cadastro automático não alterou a 205 (vínculo aberto) nem duplicou nada.
    tab = _tab(db, 205)
    assert tab["active_order_id"] == "pedido-aberto-205" and tab["table_id"] == "mesa-antiga"
    numbers = [d["number"] for d in db.physical_tabs.docs]
    assert sorted(numbers) == list(range(200, 292))
    # E a 205 continua reservada: outra mesa não consegue vinculá-la.
    status, body = _link("t5", 205)
    assert status == 409


def test_tab_in_range_but_missing_is_404(db):
    db.physical_tabs.docs = [d for d in db.physical_tabs.docs if d["number"] != 250]
    status, body = _link("t1", 250)
    assert status == 404 and body["detail"] == "Comanda não cadastrada"


# ---------- POST /tabs/range ----------
def test_range_route_limited_to_same_range(db):
    status, body = call("POST", "/api/tabs/range", token_for(ADMIN["id"]), {"start": 280, "end": 292})
    assert status == 400 and "200 e 291" in body["detail"]
    status, body = call("POST", "/api/tabs/range", token_for(ADMIN["id"]), {"start": 100, "end": 210})
    assert status == 400
    status, body = call("POST", "/api/tabs/range", token_for(ADMIN["id"]), {"start": 200, "end": 291})
    assert status == 200 and body == {"created": 0, "total_requested": 92}


# ---------- script ----------
def test_script_dry_run_then_twice_never_duplicates(monkeypatch):
    monkeypatch.delenv("PHYSICAL_TAB_MIN", raising=False)
    monkeypatch.delenv("PHYSICAL_TAB_MAX", raising=False)
    col = SyncCol(_existing_tabs())
    before = copy.deepcopy(col.docs)
    lines = []

    assert script.executar(col, dry_run=True, out=lines.append) == 0
    assert col.docs == before  # dry-run não escreve
    assert "[dry-run] Seriam criadas 61 comanda(s): 231 a 291" in lines

    lines.clear()
    assert script.executar(col, dry_run=False, out=lines.append) == 61
    assert "Criadas 61 comanda(s): 231 a 291" in lines

    lines.clear()
    assert script.executar(col, dry_run=False, out=lines.append) == 0
    assert "Nenhuma comanda faltando. Nada a fazer." in lines

    numbers = [d["number"] for d in col.docs]
    assert len(numbers) == len(set(numbers)) == 92
    assert sorted(numbers) == list(range(200, 292))
    # As 200 a 230 continuam exatamente como estavam (inclusive o vínculo da 205).
    assert col.docs[:31] == before


def test_script_fills_gaps_only():
    col = SyncCol([physical_tabs.new_tab_doc(n) for n in range(200, 292) if n not in (240, 241, 260)])
    lines = []
    script.executar(col, dry_run=True, out=lines.append)
    assert "[dry-run] Seriam criadas 3 comanda(s): 240 a 241, 260" in lines


def test_script_without_env_does_not_connect(monkeypatch, capsys):
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    assert script.main(["--dry-run"]) == 2
    assert "MONGO_URL" in capsys.readouterr().err
