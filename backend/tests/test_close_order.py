"""Etapa 2, item 2.1: POST /orders/{id}/close com validação e transação.

Teste OFFLINE (sem servidor e sem MongoDB). O banco falso simula transação:
as escritas só valem no commit, são descartadas em erro, e duas transações
que mexem no mesmo documento geram conflito (como o MongoDB faz).
Rodar: cd backend && python -m pytest tests/test_close_order.py
"""
import asyncio
import copy

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure, PyMongoError

from _offline_app import call, server, token_for

V = server._validate_close_payments


# =====================================================================
# 1) Validação pura (centavos, regras do fechamento do caixa)
# =====================================================================
def _ok(total, payments, comp=False):
    return V(server._close_cents(total), payments, comp)


def _err(total, payments, comp=False):
    with pytest.raises(HTTPException) as exc:
        _ok(total, payments, comp)
    assert exc.value.status_code == 422
    return exc.value.detail


def test_exact_payment_ok():
    assert _ok(58.19, [{"method": "pix", "amount": 58.19}]) == [{"method": "pix", "amount_cents": 5819}]


def test_cash_change_ok():
    assert _ok(30.0, [{"method": "cash", "amount": 50.0}])[0]["amount_cents"] == 5000


def test_split_payment_ok():
    assert len(_ok(100.0, [{"method": "pix", "amount": 60.0}, {"method": "debit", "amount": 40.0}])) == 2


def test_insufficient_payment():
    assert "faltam R$ 0,01" in _err(58.19, [{"method": "pix", "amount": 58.18}])


def test_missing_payment():
    assert "Informe o pagamento" in _err(10.0, [])


def test_missing_payments_key():
    assert "Informe o pagamento" in _err(10.0, None)


def test_change_without_cash_refused():
    assert "Troco" in _err(30.0, [{"method": "pix", "amount": 50.0}])


def test_change_bigger_than_cash_refused():
    # pix 30 + dinheiro 5 para total 20: troco 15 > dinheiro 5
    assert "Troco" in _err(20.0, [{"method": "pix", "amount": 30.0}, {"method": "cash", "amount": 5.0}])


@pytest.mark.parametrize("method", ["boleto", "platform", "", None, "CASH"])
def test_invalid_method(method):
    assert "Forma de pagamento inválida" in _err(10.0, [{"method": method, "amount": 10.0}])


@pytest.mark.parametrize("amount", ["10", None, True, float("nan"), float("inf"), [10]])
def test_invalid_amount(amount):
    assert "inválido" in _err(10.0, [{"method": "cash", "amount": amount}])


def test_negative_amount():
    assert "negativo" in _err(10.0, [{"method": "cash", "amount": -1.0}])


def test_zero_lines_are_ignored():
    # A tela cria linhas de R$ 0,00 no botão "+".
    assert _ok(10.0, [{"method": "cash", "amount": 10.0}, {"method": "pix", "amount": 0}]) == [
        {"method": "cash", "amount_cents": 1000}]


def test_payment_not_a_list():
    assert "inválidos" in _err(10.0, {"method": "cash", "amount": 10})


# Cortesia e total zero continuam fechando como hoje
def test_comp_closes_without_payment():
    assert _ok(80.0, [], comp=True) == []


def test_comp_closes_with_partial_payment():
    assert len(_ok(80.0, [{"method": "cash", "amount": 10.0}], comp=True)) == 1


def test_comp_still_rejects_invalid_method():
    _err(80.0, [{"method": "boleto", "amount": 10.0}], comp=True)


def test_total_zero_closes_without_payment():
    assert _ok(0, []) == []


def test_total_zero_with_default_zero_line():
    # Tela seleciona a comanda com {cash, total} = {cash, 0}.
    assert _ok(0, [{"method": "cash", "amount": 0}]) == []


def test_total_zero_with_cash_ok():
    assert len(_ok(0, [{"method": "cash", "amount": 5.0}])) == 1


def test_total_zero_with_pix_refused():
    # Travaria o fechamento do caixa (troco sem dinheiro).
    _err(0, [{"method": "pix", "amount": 5.0}])


# =====================================================================
# 2) Rota completa com banco falso transacional
# =====================================================================
def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Result:
    def __init__(self, matched, modified):
        self.matched_count, self.modified_count = matched, modified


class FakeStore:
    def __init__(self, data):
        self.data = data            # {"orders": [...], ...} confirmado
        self.unsupported = False    # simula servidor sem replica set
        self.fail_on = None         # nome do método que falha dentro da transação


class FakeSession:
    def __init__(self, store):
        self.store = store
        self.working = None
        self.snapshot = None
        self.touched = set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def start_transaction(self):
        return _Txn(self)


class _Txn:
    def __init__(self, session):
        self.s = session

    async def __aenter__(self):
        self.s.snapshot = copy.deepcopy(self.s.store.data)
        self.s.working = copy.deepcopy(self.s.store.data)
        self.s.touched = set()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        s = self.s
        if exc_type is None:
            # Conflito: algum documento tocado mudou desde o início da transação.
            for coll, did in s.touched:
                now = next((d for d in s.store.data[coll] if d.get("id") == did), None)
                then = next((d for d in s.snapshot[coll] if d.get("id") == did), None)
                if now != then:
                    s.working = None
                    raise OperationFailure("WriteConflict", code=112)
            s.store.data = s.working
        s.working = None  # abort: descarta tudo
        return False


class FakeClient:
    def __init__(self, store):
        self.store = store

    async def start_session(self):
        return FakeSession(self.store)


class FakeCollection:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def _docs(self, session):
        if session is not None:
            if self.store.unsupported:
                raise OperationFailure(
                    "Transaction numbers are only allowed on a replica set member or mongos", code=20)
            return session.working[self.name]
        return self.store.data[self.name]

    def _maybe_fail(self, method, session):
        if session is not None and self.store.fail_on == f"{self.name}.{method}":
            raise PyMongoError("falha simulada")

    async def find_one(self, query, projection=None, session=None):
        await asyncio.sleep(0)  # permite intercalar pedidos concorrentes
        for d in self._docs(session):
            if _match(d, query):
                return copy.deepcopy(d)
        return None

    async def update_one(self, query, update, session=None):
        self._maybe_fail("update_one", session)
        docs = self._docs(session)
        for d in docs:
            if _match(d, query):
                d.update(copy.deepcopy(update.get("$set", {})))
                for k, inc in update.get("$inc", {}).items():
                    d[k] = round(d.get(k, 0) + inc, 2)
                if session is not None:
                    session.touched.add((self.name, d.get("id")))
                return _Result(1, 1)
        return _Result(0, 0)

    async def insert_many(self, docs, session=None):
        self._maybe_fail("insert_many", session)
        self._docs(session).extend(copy.deepcopy(docs))


class FakeDB:
    def __init__(self, store):
        for name in ("orders", "payments", "cash_registers"):
            setattr(self, name, FakeCollection(store, name))


CASHIER = {"id": "u-cashier", "name": "Caixa", "email": "c@example.invalid", "role": "cashier", "is_active": True}
WAITER = {"id": "u-waiter", "name": "Garçom", "email": "w@example.invalid", "role": "waiter", "is_active": True}


class _Users:
    async def find_one(self, query, projection=None):
        for u in (CASHIER, WAITER):
            if u["id"] == query.get("id"):
                return dict(u)
        return None


def _order(oid="o1", total=58.19, **kw):
    base = {"id": oid, "total": total, "is_closed": False, "status": "pending", "source": "table",
            "table_id": "t1", "items": [{"id": "i1", "product_id": "p1", "quantity": 1, "status": "pending"}]}
    base.update(kw)
    return base


@pytest.fixture
def env(monkeypatch):
    store = FakeStore({
        "orders": [_order()],
        "payments": [],
        "cash_registers": [{"id": "reg-1", "is_open": True, "total_sales": 100.0}],
    })
    fake_db = FakeDB(store)
    fake_db.users = _Users()
    deducted = []

    async def fake_deduct(product_id, quantity, order_code=""):
        deducted.append((order_code, product_id, quantity))

    async def noop(*a, **k):
        return None

    async def fake_tables():
        return []

    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server, "client", FakeClient(store))
    monkeypatch.setattr(server, "deduct_stock", fake_deduct)
    monkeypatch.setattr(server, "release_physical_tab", noop)
    monkeypatch.setattr(server, "refresh_table_after_order", noop)
    monkeypatch.setattr(server, "get_tables", fake_tables)
    monkeypatch.setattr(server.sio, "emit", noop)
    store.deducted = deducted
    return store


TOKEN = token_for(CASHIER["id"])


def _close(payments, oid="o1"):
    return call("POST", f"/api/orders/{oid}/close", token=TOKEN, body={"payments": payments})


def _o(store, oid="o1"):
    return next(o for o in store.data["orders"] if o["id"] == oid)


def _total_sales(store):
    return store.data["cash_registers"][0]["total_sales"]


def test_close_ok_writes_everything_once(env):
    status, _ = _close([{"method": "cash", "amount": 60.0}])
    assert status == 200
    assert _o(env)["is_closed"] is True and _o(env)["closed_by_id"] == "u-cashier"
    assert len(env.data["payments"]) == 1
    pay = env.data["payments"][0]
    assert pay["amount"] == 60.0 and pay["register_id"] == "reg-1" and pay["created_by_id"] == "u-cashier"
    assert _total_sales(env) == pytest.approx(158.19)
    assert env.deducted == [("o1", "p1", 1)]


def test_uses_database_total_not_browser_total(env):
    # Navegador ainda mostra 50,00; no banco o total já é 58,19.
    status, body = _close([{"method": "pix", "amount": 50.0}])
    assert status == 422 and "faltam R$ 8,19" in body["detail"]
    assert _o(env)["is_closed"] is False
    assert env.data["payments"] == [] and _total_sales(env) == 100.0 and env.deducted == []


def test_double_click_sequential(env):
    assert _close([{"method": "pix", "amount": 58.19}])[0] == 200
    status, body = _close([{"method": "pix", "amount": 58.19}])
    assert status == 409 and "já está fechado" in body["detail"]
    assert len(env.data["payments"]) == 1
    assert _total_sales(env) == pytest.approx(158.19)
    assert len(env.deducted) == 1


def test_double_click_concurrent(env):
    async def both():
        args = ("o1", {"payments": [{"method": "pix", "amount": 58.19}]})
        return await asyncio.gather(server.close_order(*args, current_user=CASHIER),
                                    server.close_order(*args, current_user=CASHIER),
                                    return_exceptions=True)

    results = asyncio.run(both())
    ok = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, HTTPException)]
    assert len(ok) == 1 and len(errors) == 1
    assert errors[0].status_code in (409, 503)  # 503 = conflito de escrita: nada gravado
    assert len(env.data["payments"]) == 1
    assert _total_sales(env) == pytest.approx(158.19)
    assert len(env.deducted) == 1


def test_stale_read_is_blocked_by_conditional_close(env, monkeypatch):
    # O 1º pedido fecha a comanda. O 2º leu a comanda ANTES disso (leitura
    # desatualizada) e só abre a transação depois: a condição is_closed == false
    # dentro da transação é o que impede pagar e somar de novo.
    assert _close([{"method": "pix", "amount": 58.19}])[0] == 200
    stale = _order()
    real_find_one = server.db.orders.find_one

    async def stale_find_one(query, projection=None, session=None):
        if session is None:
            return copy.deepcopy(stale)
        return await real_find_one(query, projection, session=session)

    monkeypatch.setattr(server.db.orders, "find_one", stale_find_one)
    status, body = _close([{"method": "pix", "amount": 58.19}])
    assert status == 409 and "já está fechado" in body["detail"]
    assert len(env.data["payments"]) == 1
    assert _total_sales(env) == pytest.approx(158.19)
    assert len(env.deducted) == 1


def test_transaction_unsupported_writes_nothing(env):
    env.unsupported = True
    before = copy.deepcopy(env.data)
    status, body = _close([{"method": "pix", "amount": 58.19}])
    assert status == 503 and "não aceita transações" in body["detail"] and "Nada foi gravado" in body["detail"]
    assert env.data == before and env.deducted == []


@pytest.mark.parametrize("fail_on", ["payments.insert_many", "cash_registers.update_one"])
def test_failure_inside_transaction_rolls_back(env, fail_on):
    env.fail_on = fail_on
    before = copy.deepcopy(env.data)
    status, body = _close([{"method": "pix", "amount": 58.19}])
    assert status == 503 and "Nada foi gravado" in body["detail"]
    assert env.data == before and env.deducted == []


def test_invalid_method_writes_nothing(env):
    before = copy.deepcopy(env.data)
    assert _close([{"method": "cash", "amount": 10.0}, {"method": "boleto", "amount": 50.0}])[0] == 422
    assert env.data == before


def test_comp_closes_and_does_not_add_to_sales(env):
    env.data["orders"] = [_order(is_comp=True)]
    assert _close([{"method": "cash", "amount": 58.19}])[0] == 200
    assert _o(env)["is_closed"] is True
    assert _total_sales(env) == 100.0
    assert env.deducted == [("o1", "p1", 1)]  # cortesia também consome estoque


def test_comp_closes_without_payment(env):
    env.data["orders"] = [_order(is_comp=True)]
    assert _close([])[0] == 200
    assert env.data["payments"] == []


def test_total_zero_closes(env):
    env.data["orders"] = [_order(total=0)]
    assert _close([{"method": "cash", "amount": 0}])[0] == 200
    assert _o(env)["is_closed"] is True and env.data["payments"] == []
    assert _total_sales(env) == 100.0


def test_no_open_register_still_closes(env):
    env.data["cash_registers"][0]["is_open"] = False
    assert _close([{"method": "pix", "amount": 58.19}])[0] == 200
    assert env.data["payments"][0]["register_id"] is None
    assert _total_sales(env) == 100.0


def test_online_order_refused(env):
    env.data["orders"] = [_order(source="online")]
    assert _close([{"method": "pix", "amount": 58.19}])[0] == 409


def test_waiter_cannot_close(env):
    status, _ = call("POST", "/api/orders/o1/close", token=token_for(WAITER["id"]),
                     body={"payments": [{"method": "pix", "amount": 58.19}]})
    assert status == 403
    assert _o(env)["is_closed"] is False
