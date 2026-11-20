"""Integração NostFood: webhook, polling, cancelamento, estoque, caixa e KDS.

Teste OFFLINE (sem servidor, sem MongoDB e sem rede): banco falso em memória
e a API da NostFood substituída por funções locais.
Rodar: cd backend && python -m pytest tests/test_nostfood_integration.py
"""
import asyncio
import base64
import hashlib
import hmac
import json

import pytest

from _fake_mongo import FakeDB
from _offline_app import call, server, token_for

import nostfood_integration as nf

SECRET = "segredo-de-teste-nostfood"
ADMIN = {"id": "u-admin", "name": "Admin", "email": "a@x", "role": "admin", "is_active": True}
CASHIER = {"id": "u-caixa", "name": "Caixa", "email": "c@x", "role": "cashier", "is_active": True}
KITCHEN = {"id": "u-coz", "name": "Cozinheiro", "email": "k@x", "role": "kitchen", "is_active": True}
T_ADMIN, T_CASHIER, T_KITCHEN = token_for(ADMIN["id"]), token_for(CASHIER["id"]), token_for(KITCHEN["id"])


# ==================== infraestrutura ====================
class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session(_Tx):
    def start_transaction(self):
        return _Tx()


class _Client:
    async def start_session(self):
        return _Session()


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    for u in (ADMIN, CASHIER, KITCHEN):
        db.users.docs.append(dict(u))
    db.products.docs += [
        {"id": "p-sansao", "name": "Sansão", "type": "food", "price": 32.0, "cost": 0, "category_id": "c1"},
        {"id": "p-coca", "name": "Coca-Cola Lata", "type": "drink", "price": 6.0, "cost": 2.5, "category_id": "c2"},
    ]
    # Ficha técnica do Sansão: 1 pão (R$ 1,50) + 0,15 kg de carne (R$ 40/kg) = R$ 7,50
    db.stock.docs += [
        {"id": "s-pao", "name": "Pão", "quantity": 10, "unit": "unit", "unit_cost": 1.5, "min_quantity": 0},
        {"id": "s-carne", "name": "Carne", "quantity": 5, "unit": "kg", "unit_cost": 40.0, "min_quantity": 0},
        {"id": "s-coca", "product_id": "p-coca", "name": "Coca lata", "quantity": 24, "unit": "unit",
         "unit_cost": 2.5, "min_quantity": 0},
    ]
    db.recipes.docs.append({"product_id": "p-sansao", "ingredients": [
        {"stock_item_id": "s-pao", "quantity": 1}, {"stock_item_id": "s-carne", "quantity": 0.15}]})
    db.cash_registers.docs.append({"id": "reg-1", "is_open": True, "total_sales": 0.0,
                                   "opened_at": "2000-01-01T00:00:00+00:00"})

    emitted, sent, remote, scheduled = [], [], [], []

    async def fake_emit(event, data=None, **kw):
        emitted.append((event, data))

    async def fake_page(params):
        return {"pedidos": list(remote), "has_more": False}

    async def fake_send(external_id, order_number, status):
        if env_state.get("send_fails"):
            raise RuntimeError("NostFood fora do ar")
        sent.append((external_id, status))
        return {"success": True}

    env_state = {}
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "client", _Client())
    monkeypatch.setattr(server.sio, "emit", fake_emit)
    monkeypatch.setattr(nf, "fetch_orders_page", fake_page)
    monkeypatch.setattr(nf, "send_status", fake_send)
    monkeypatch.setattr(nf, "_schedule", lambda coro: scheduled.append(coro))
    monkeypatch.setitem(nf._state, "indexes_ok", False)
    monkeypatch.setitem(nf._state, "enabled_at", None)
    monkeypatch.setenv("NOSTFOOD_ENABLED", "true")
    monkeypatch.setenv("NOSTFOOD_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("NOSTFOOD_API_KEY", "chave-teste")

    class E:
        pass

    e = E()
    e.db, e.emitted, e.sent, e.remote, e.state = db, emitted, sent, remote, env_state

    def run_scheduled():
        while scheduled:
            asyncio.run(scheduled.pop(0))

    e.run_scheduled = run_scheduled
    yield e
    for coro in scheduled:  # envios não executados no teste
        coro.close()


def sign_hex(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def sign_b64(body: bytes) -> str:
    return "sha256=" + base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


def post_raw(path, body: bytes, headers: dict, method="POST", query=""):
    hdrs = [(b"content-type", b"application/json")] + [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": query.encode(),
             "root_path": "", "headers": hdrs, "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
    state = {"sent": False}
    result = {"body": b""}

    async def receive():
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    asyncio.run(server.app(scope, receive, send))
    return result["status"], json.loads(result["body"] or b"null")


WEBHOOK = "/api/integrations/nostfood/webhook"
N = "/api/integrations/nostfood"


def remote_order(oid=498, payment="pix_online", status="confirmado", **kw):
    o = {
        "id": oid, "order_number": f"PED-{oid}", "customer_name": "Maria", "customer_phone": "16999990000",
        "customer_address": "Rua A", "customer_number": "10", "customer_neighborhood": "Centro",
        "customer_city": "Franca", "customer_state": "SP", "latitude": -20.5, "longitude": -47.4,
        "items": [
            {"id": 11, "name": "Sansão", "quantity": 1, "price": 32.0, "subtotal": 35.0,
             "observation": "sem picles", "customizations": [{"name": "Bacon", "price": 3.0}]},
            {"id": 12, "name": "Coca-Cola lata", "quantity": 2, "price": 6.0, "subtotal": 12.0},
        ],
        "subtotal": 47.0, "delivery": 5.0, "total": 52.0, "status": status, "payment_method": payment,
    }
    o.update(kw)
    return o


def send_event(event_type, data, event_id="evt_1", resource_id="498", signer=sign_hex):
    payload = {"event_id": event_id, "event_type": event_type, "occurred_at": "2026-11-20T19:55:31Z",
               "delivery_attempt": 1, "lojista_id": 32, "resource": {"type": "order", "id": resource_id},
               "data": data}
    body = json.dumps(payload).encode()
    return post_raw(WEBHOOK, body, {"X-NostFood-Signature": signer(body), "X-NostFood-Event": event_type})


def link_all(env):
    env.db.nostfood_product_map.docs += [
        {"nostfood_key": "name:sansao", "product_id": "p-sansao"},
        {"nostfood_key": "name:coca-cola lata", "product_id": "p-coca"},
    ]


def orders(env):
    return [o for o in env.db.orders.docs if o.get("external_source") == "nostfood"]


def stock(env, sid):
    return next(s for s in env.db.stock.docs if s["id"] == sid)["quantity"]


# ==================== assinatura ====================
def test_signature_hex_and_base64_accepted(env):
    link_all(env)
    assert send_event("order.created", remote_order(), event_id="evt_hex")[0] == 200
    assert send_event("order.created", remote_order(499, id=499), event_id="evt_b64",
                      resource_id="499", signer=sign_b64)[0] == 200
    assert len(orders(env)) == 2


def test_signature_invalid_returns_401(env):
    status, _ = send_event("order.created", remote_order(), signer=lambda b: "sha256=" + "0" * 64)
    assert status == 401
    status, _ = post_raw(WEBHOOK, b'{"event_id":"x"}', {})
    assert status == 401
    assert env.db.nostfood_events.docs == [] and orders(env) == []


def test_signature_over_raw_body(env):
    """Assinatura de outro corpo (ex.: JSON re-serializado) não vale."""
    body = json.dumps({"event_id": "evt_raw", "event_type": "order.created", "data": remote_order()}).encode()
    other = body.replace(b'"Maria"', b'"Joana"')
    status, _ = post_raw(WEBHOOK, other, {"X-NostFood-Signature": sign_hex(body)})
    assert status == 401


def test_empty_secret_refuses_everything(env, monkeypatch):
    monkeypatch.setenv("NOSTFOOD_WEBHOOK_SECRET", "")
    body = json.dumps({"event_id": "evt_x", "event_type": "order.created", "data": remote_order()}).encode()
    empty_sig = "sha256=" + hmac.new(b"", body, hashlib.sha256).hexdigest()
    for headers in ({}, {"X-NostFood-Signature": empty_sig}):
        assert post_raw(WEBHOOK, body, headers)[0] in (401, 503)
    assert not nf.verify_signature(body, empty_sig, "")
    assert env.db.nostfood_events.docs == [] and orders(env) == []


def test_events_have_ttl_of_30_days(env):
    link_all(env)
    send_event("order.created", remote_order())
    ttl = [opts for fields, opts in env.db.nostfood_events.indexes if fields == ["received_at_dt"]]
    assert ttl and ttl[0]["expireAfterSeconds"] == 30 * 24 * 3600
    assert env.db.nostfood_events.docs[0]["received_at_dt"].tzinfo is not None


def test_safe_deduct_marks_only_on_success(env, monkeypatch):
    order = {"id": "o", "external_source": "nostfood"}
    ok_item = {"product_id": "p-coca", "quantity": 1}
    assert asyncio.run(nf.safe_deduct(order, ok_item)) is True and ok_item["stock_deducted"] is True

    async def boom(*a, **k):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(server, "deduct_stock", boom)
    bad = {"product_id": "p-coca", "quantity": 1}
    assert asyncio.run(nf.safe_deduct(order, bad)) is False
    assert "stock_deducted" not in bad and bad["stock_pending"] is True
    unlinked = {"product_id": "nostfood-unlinked:x", "quantity": 1, "unlinked": True}
    assert asyncio.run(nf.safe_deduct(order, unlinked)) is False and "stock_deducted" not in unlinked
    test_item = {"product_id": "p-coca", "quantity": 1}
    assert asyncio.run(nf.safe_deduct({**order, "is_test": True}, test_item)) is False
    assert "stock_deducted" not in test_item and "stock_pending" not in test_item


def test_webhook_off_by_default(env, monkeypatch):
    monkeypatch.delenv("NOSTFOOD_ENABLED")
    assert send_event("order.created", remote_order())[0] == 503
    assert orders(env) == []


# ==================== evento e pedido duplicados ====================
def test_duplicate_event_is_ignored(env):
    link_all(env)
    assert send_event("order.created", remote_order(), event_id="evt_dup") == (200, {"ok": True})
    status, body = send_event("order.created", remote_order(), event_id="evt_dup")
    assert status == 200 and body["duplicate"] is True
    assert len(env.db.nostfood_events.docs) == 1 and len(orders(env)) == 1
    assert env.db.nostfood_events.docs[0]["status"] == "processed"


def test_same_order_from_webhook_and_polling_is_not_duplicated(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="evt_a")
    send_event("order.updated", {"order_number": "PED-498", "status": "aprovado"}, event_id="evt_b")
    env.remote.append(remote_order(status="aprovado"))
    summary = asyncio.run(nf.poll_once())
    assert summary["created"] == 0 and len(orders(env)) == 1
    assert orders(env)[0]["nostfood_status"] == "aprovado"


def test_polling_first_then_webhook(env):
    link_all(env)
    env.remote.append(remote_order())
    assert asyncio.run(nf.poll_once())["created"] == 1
    send_event("order.created", remote_order(), event_id="evt_late")
    assert len(orders(env)) == 1
    assert env.db.nostfood_events.docs[0]["result"] == "exists"


def test_unique_index_blocks_concurrent_insert(env):
    """Mesmo se duas gravações escaparem da checagem, o índice único barra a segunda."""
    link_all(env)
    asyncio.run(nf.ensure_indexes())
    env.db.orders.docs.append({"id": "x", "external_source": "nostfood", "external_id": "498"})
    with pytest.raises(Exception):
        asyncio.run(env.db.orders.insert_one({"id": "y", "external_source": "nostfood", "external_id": "498"}))
    # pedidos antigos sem external_source não colidem entre si (índice parcial)
    asyncio.run(env.db.orders.insert_one({"id": "old1"}))
    asyncio.run(env.db.orders.insert_one({"id": "old2"}))


def test_webhook_without_items_fetches_full_order(env):
    link_all(env)
    env.remote.append(remote_order())
    send_event("order.created", {"order_number": "PED-498", "status": "confirmado", "total": 52.0})
    assert len(orders(env)) == 1 and len(orders(env)[0]["items"]) == 2


# ==================== conteúdo do pedido ====================
def test_order_fields(env):
    link_all(env)
    send_event("order.created", remote_order())
    o = orders(env)[0]
    assert o["channel"] == "delivery" and o["service_fee"] == 0 and o["service_fee_percentage"] == 0
    assert o["external_id"] == "498" and o["external_order_number"] == "PED-498"
    assert (o["subtotal"], o["delivery_fee"], o["total"]) == (47.0, 5.0, 52.0)
    assert o["customer_name"] == "Maria" and o["latitude"] == -20.5 and "Rua A" in o["address"]
    sansao, coca = o["items"]
    assert sansao["product_id"] == "p-sansao" and sansao["type"] == "food" and sansao["unit_price"] == 35.0
    assert "sem picles" in sansao["notes"] and "Bacon" in sansao["notes"]
    assert coca["product_id"] == "p-coca" and coca["type"] == "drink" and coca["quantity"] == 2
    assert any(ev == "kitchen_update" for ev, _ in env.emitted)
    assert any(ev == "bar_update" for ev, _ in env.emitted)


def test_portuguese_field_names(env):
    link_all(env)
    raw = {"pedido_id": 77, "numero": "PED-77", "cliente": {"nome": "João", "telefone": "1"},
           "itens": [{"nome": "Sansão", "quantidade": "2", "preco": "30,00", "observacao": "bem passado",
                      "adicionais": [{"nome": "Cheddar", "quantidade": 1, "preco": 2}]}],
           "taxa_entrega": 4, "forma_pagamento": "dinheiro"}
    assert asyncio.run(nf.upsert_from_snapshot(raw, "teste")) == "created"
    o = orders(env)[0]
    assert o["customer_name"] == "João" and o["external_id"] == "77"
    it = o["items"][0]
    assert it["quantity"] == 2 and it["unit_price"] == 32.0 and "bem passado" in it["notes"]
    assert o["subtotal"] == 64.0 and o["total"] == 68.0 and o["payment_status"] == "to_collect"


# ==================== pago online x cobrar na entrega ====================
@pytest.mark.parametrize("method,expected", [
    ("pix_online", "pending_platform"), ("cartao_credito_online", "pending_platform"),
    ("mercadopago_online", "pending_platform"), ("pago_online", "pending_platform"),
    ("dinheiro", "to_collect"), ("pix", "to_collect"), ("cartao_debito_loja", "to_collect"),
    ("cartao_credito_celular", "to_collect"),
])
def test_payment_status(method, expected):
    assert nf.payment_status_for(method) == expected


def test_paid_online_goes_to_settlement_not_cash(env):
    link_all(env)
    send_event("order.created", remote_order(payment="pix_online"))
    o = orders(env)[0]
    assert o["payment_status"] == "pending_platform"
    status, body = call("POST", f"/api/orders/{o['id']}/close", token=T_CASHIER,
                        body={"payments": [{"method": "cash", "amount": 52.0}]})
    assert status == 409
    status, body = call("POST", f"/api/orders/{o['id']}/complete-online", token=T_CASHIER)
    assert status == 200 and body["settlement_status"] == "pending_platform"
    assert env.db.cash_registers.docs[0]["total_sales"] == 0 and env.db.payments.docs == []


def test_collect_on_delivery_enters_cash(env):
    link_all(env)
    send_event("order.created", remote_order(payment="dinheiro"))
    o = orders(env)[0]
    assert o["payment_status"] == "to_collect"
    status, _ = call("POST", f"/api/orders/{o['id']}/complete-online", token=T_CASHIER)
    assert status == 409  # nunca vira repasse
    # bloqueia o fechamento do caixa enquanto não for recebido
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 1
    status, _ = call("POST", f"/api/orders/{o['id']}/close", token=T_CASHIER,
                     body={"payments": [{"method": "cash", "amount": 60.0}]})
    assert status == 200
    assert env.db.cash_registers.docs[0]["total_sales"] == pytest.approx(52.0)
    assert env.db.payments.docs[0]["amount"] == 60.0
    assert not nf.settles_on_platform(orders(env)[0])
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 0


# ==================== cancelamento ====================
def test_cancel_before_kitchen_starts(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    before = (stock(env, "s-pao"), stock(env, "s-coca"))
    send_event("order.cancelled", {"order_number": "PED-498", "status": "cancelado",
                                   "motivo": "Cliente desistiu"}, event_id="e2")
    o = orders(env)[0]
    assert o["status"] == "cancelled" and o["is_closed"] is True
    assert o["cancelled_by_name"] == "nostfood" and o["cancellation_reason"] == "Cliente desistiu"
    assert o["cancelled_at"] and o["kds_ack_pending"] is True
    assert all(i["status"] == "cancelled" for i in o["items"])
    assert (stock(env, "s-pao"), stock(env, "s-coca")) == before
    assert env.db.stock_losses.docs == []
    assert any(ev == "kds_cancelled" for ev, _ in env.emitted)


def test_cancel_before_start_restores_previous_deduction(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    o = env.db.orders.docs[0]
    o["items"][1]["stock_deducted"] = True  # coca já baixada (ex.: entregue no balcão)
    env.db.stock.docs[2]["quantity"] -= 2
    send_event("order.updated", {"order_number": "PED-498", "status": "rejeitado"}, event_id="e2")
    assert stock(env, "s-coca") == 24
    assert orders(env)[0]["status"] == "cancelled"


def test_cancel_after_kitchen_started_is_loss(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    o = orders(env)[0]
    sansao = o["items"][0]
    status, _ = call("PUT", f"/api/orders/{o['id']}/item/{sansao['id']}/status", token=T_KITCHEN,
                     body={"status": "preparing"})
    assert status == 200
    send_event("order.cancelled", {"order_number": "PED-498", "motivo": "Loja fechou"}, event_id="e2")
    o = orders(env)[0]
    assert o["status"] == "cancelled"
    # Sansão em preparo: baixa pela ficha técnica e perda; Coca pendente: nada
    assert stock(env, "s-pao") == 9 and stock(env, "s-carne") == pytest.approx(4.85)
    assert stock(env, "s-coca") == 24
    assert len(env.db.stock_losses.docs) == 1
    loss = env.db.stock_losses.docs[0]
    assert loss["reason"] == "Loja fechou" and loss["order_id"] == o["id"]
    assert loss["total_cost"] == 7.5 and loss["items"][0]["cost_source"] == "ficha_tecnica"
    assert len(loss["items"]) == 1 and loss["items"][0]["status_before_cancel"] == "preparing"
    auth = {"Authorization": f"Bearer {T_ADMIN}"}
    day = loss["date"]
    status, body = post_raw(f"{N}/perdas", b"", auth, method="GET", query=f"data_inicio={day}&data_fim={day}")
    assert status == 200 and body["count"] == 1 and body["total_cost"] == 7.5
    status, body = post_raw(f"{N}/perdas", b"", auth, method="GET", query="data_inicio=2000-01-01&data_fim=2000-01-02")
    assert status == 200 and body["count"] == 0
    assert post_raw(f"{N}/perdas", b"", auth, method="GET", query="data_inicio=20/11/2026")[0] == 400
    assert post_raw(f"{N}/perdas", b"", {"Authorization": f"Bearer {T_CASHIER}"}, method="GET")[0] == 403


def test_cancel_with_stock_shortage_never_blocks(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    env.db.stock.docs[0]["quantity"] = 0  # sem pão
    o = orders(env)[0]
    call("PUT", f"/api/orders/{o['id']}/item/{o['items'][0]['id']}/status", token=T_KITCHEN,
         body={"status": "ready"})
    send_event("order.cancelled", {"order_number": "PED-498"}, event_id="e2")
    o = orders(env)[0]
    assert o["status"] == "cancelled"
    assert o["items"][0]["stock_pending"] is True and o["items"][0]["stock_deducted"] is False
    assert env.db.stock_losses.docs[0]["items"][0]["stock_pending"] is True


def test_cancel_arrives_before_create(env):
    link_all(env)
    send_event("order.cancelled", {"order_number": "PED-498"}, event_id="e1")
    send_event("order.created", remote_order(), event_id="e2")
    assert orders(env) == []
    assert env.db.nostfood_events.docs[1]["result"] == "ignored_cancelled"


def test_polling_processes_cancellation(env):
    link_all(env)
    env.remote.append(remote_order())
    asyncio.run(nf.poll_once())
    env.remote[0] = remote_order(status="cancelado")
    assert asyncio.run(nf.poll_once())["cancelled"] == 1
    assert orders(env)[0]["status"] == "cancelled"


# ==================== data de ativação ====================
def _activate(env, iso="2026-11-20T15:00:00+00:00"):  # 12:00 em São Paulo
    env.db.nostfood_settings.docs.append({"key": "config", "nostfood_enabled_at": iso})


def test_activation_date_is_recorded_once(env):
    first = asyncio.run(nf.get_enabled_at())
    nf._state["enabled_at"] = None
    assert asyncio.run(nf.get_enabled_at()) == first
    assert len(env.db.nostfood_settings.docs) == 1


def test_orders_before_activation_are_ignored(env):
    link_all(env)
    _activate(env)
    env.remote += [
        remote_order(1, id=1, created_at="2026-11-20 11:59:00"),             # antes (horário SP)
        remote_order(2, id=2, created_at="2026-11-20 11:00:00", status="cancelado"),
        remote_order(3, id=3, created_at="2026-11-20 12:01:00"),             # depois
    ]
    summary = asyncio.run(nf.poll_once())
    assert summary["created"] == 1 and summary["skipped"] == 1
    assert [o["external_id"] for o in orders(env)] == ["3"]
    assert env.db.nostfood_tombstones.docs == []


def test_finished_order_after_activation_goes_to_history(env):
    link_all(env)
    _activate(env)
    env.remote.append(remote_order(5, id=5, created_at="2026-11-20 13:00:00", status="entregue"))
    assert asyncio.run(nf.poll_once())["created"] == 1
    o = orders(env)[0]
    assert all(i["status"] == "delivered" for i in o["items"])          # nada novo no KDS
    assert o["is_closed"] is True and o["settlement_status"] == "pending_platform"  # entra nas vendas
    assert stock(env, "s-pao") == 9 and stock(env, "s-coca") == 22       # baixa de estoque feita
    assert not any(ev == "new_online_order" for ev, _ in env.emitted)


def test_ready_collect_on_delivery_stays_open_for_cash(env):
    link_all(env)
    _activate(env)
    env.remote.append(remote_order(6, id=6, created_at="2026-11-20 13:00:00", status="pronto", payment="dinheiro"))
    asyncio.run(nf.poll_once())
    o = orders(env)[0]
    assert o["is_closed"] is False and all(i["status"] == "delivered" for i in o["items"])
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 1


def test_in_preparation_order_is_not_new(env):
    link_all(env)
    env.remote.append(remote_order(status="em_preparo"))
    asyncio.run(nf.poll_once())
    o = orders(env)[0]
    assert all(i["status"] == "preparing" for i in o["items"]) and "em_preparo" in o["nostfood_sent_statuses"]


def test_cancel_ack_by_station(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    send_event("order.cancelled", {"order_number": "PED-498"}, event_id="e2")
    status, listed = call("GET", f"{N}/kds/cancelados", token=T_KITCHEN)
    assert status == 200 and len(listed) == 1
    oid = listed[0]["id"]
    status, o = call("POST", f"{N}/pedidos/{oid}/cancelamento/ciente", token=T_KITCHEN, body={"station": "kitchen"})
    assert status == 200 and o["cancel_acks"]["kitchen"]["by_name"] == "Cozinheiro" and o["kds_ack_pending"]
    call("POST", f"{N}/pedidos/{oid}/cancelamento/ciente", token=T_KITCHEN, body={"station": "bar"})
    assert call("GET", f"{N}/kds/cancelados", token=T_KITCHEN)[1] == []
    assert call("POST", f"{N}/pedidos/{oid}/cancelamento/ciente", token=T_CASHIER,
                body={"station": "kitchen"})[0] == 403


# ==================== status de volta e laço ====================
def test_status_back_and_self_echo_ignored(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    o = orders(env)[0]
    for item in o["items"]:
        call("PUT", f"/api/orders/{o['id']}/item/{item['id']}/status", token=T_KITCHEN, body={"status": "preparing"})
    env.run_scheduled()
    assert env.sent == [("498", "em_preparo")]  # uma vez só
    for item in o["items"]:
        call("PUT", f"/api/orders/{o['id']}/item/{item['id']}/status", token=T_KITCHEN, body={"status": "ready"})
    env.run_scheduled()
    assert env.sent == [("498", "em_preparo"), ("498", "pronto")]
    send_event("order.updated", {"order_number": "PED-498", "status": "em_preparo",
                                 "previous_status": "confirmado"}, event_id="e_echo")
    ev = next(e for e in env.db.nostfood_events.docs if e["event_id"] == "e_echo")
    assert ev["result"] == "ignored_self"


def test_nostfood_error_does_not_block_kds(env):
    link_all(env)
    env.state["send_fails"] = True
    send_event("order.created", remote_order(), event_id="e1")
    o = orders(env)[0]
    status, _ = call("PUT", f"/api/orders/{o['id']}/item/{o['items'][0]['id']}/status",
                     token=T_KITCHEN, body={"status": "preparing"})
    assert status == 200
    env.run_scheduled()
    o = orders(env)[0]
    assert o["items"][0]["status"] == "preparing" and o["nostfood_sync_errors"][0]["status"] == "em_preparo"


def test_stock_failure_on_delivery_never_blocks_kds(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    env.db.stock.docs[1]["quantity"] = 0  # sem carne
    o = orders(env)[0]
    status, _ = call("PUT", f"/api/orders/{o['id']}/item/{o['items'][0]['id']}/status",
                     token=T_KITCHEN, body={"status": "delivered"})
    assert status == 200
    item = orders(env)[0]["items"][0]
    assert item["status"] == "delivered" and item["stock_pending"] is True and not item["stock_deducted"]


# ==================== item sem ligação ====================
def test_unlinked_item(env):
    env.db.nostfood_product_map.docs.append({"nostfood_key": "name:sansao", "product_id": "p-sansao"})
    send_event("order.created", remote_order(), event_id="e1")
    o = orders(env)[0]
    coca = o["items"][1]
    assert coca["unlinked"] is True and coca["type"] == "food" and len(o["items"]) == 2
    assert any(ev == "nostfood_alert" and d["type"] == "unlinked_item" for ev, d in env.emitted)
    status, listed = call("GET", f"{N}/produtos-sem-ligacao", token=T_ADMIN)
    assert status == 200 and listed[0]["nostfood_name"] == "Coca-Cola lata" and listed[0]["nostfood_id"] == "12"
    # baixa de estoque de item sem ligação vira pendência (nunca abate outro item)
    call("PUT", f"/api/orders/{o['id']}/item/{coca['id']}/status", token=T_KITCHEN, body={"status": "delivered"})
    assert orders(env)[0]["items"][1]["stock_pending"] is True and stock(env, "s-coca") == 24

    assert call("POST", f"{N}/ligar-produto", token=T_CASHIER,
                body={"nostfood_id": "12", "product_id": "p-coca"})[0] == 403
    status, body = call("POST", f"{N}/ligar-produto", token=T_ADMIN,
                        body={"nostfood_id": "12", "nostfood_name": "Coca-Cola lata", "product_id": "p-coca"})
    assert status == 200 and body["open_orders_updated"] == 1
    coca = orders(env)[0]["items"][1]
    assert coca["product_id"] == "p-coca" and coca["type"] == "drink" and coca["unlinked"] is False
    assert call("GET", f"{N}/produtos-sem-ligacao", token=T_ADMIN)[1] == []
    # próximo pedido já entra ligado (por id)
    send_event("order.created", remote_order(500, id=500), event_id="e2", resource_id="500")
    assert orders(env)[1]["items"][1]["product_id"] == "p-coca"


# ==================== observação em pedido em preparo ====================
def test_observation_and_ack(env):
    link_all(env)
    send_event("order.created", remote_order(), event_id="e1")
    oid = orders(env)[0]["id"]
    assert call("POST", f"{N}/pedidos/{oid}/observacao", token=T_KITCHEN, body={"text": "x"})[0] == 403
    status, obs = call("POST", f"{N}/pedidos/{oid}/observacao", token=T_CASHIER, body={"text": "Sem cebola!"})
    assert status == 200 and obs["author_name"] == "Caixa" and obs["created_at"]
    status, acked = call("POST", f"{N}/pedidos/{oid}/observacao/{obs['id']}/ciente", token=T_KITCHEN,
                         body={"station": "kitchen"})
    assert status == 200 and acked["acks"]["kitchen"]["by_name"] == "Cozinheiro" and acked["acks"]["kitchen"]["at"]
    assert call("POST", f"{N}/pedidos/{oid}/observacao/{obs['id']}/ciente", token=T_KITCHEN,
                body={"station": "sala"})[0] == 400


# ==================== simulação ====================
def test_simulate_only_in_gestor(env):
    status, body = call("POST", f"{N}/simular", token=T_ADMIN)
    assert status == 200 and body["result"] == "created"
    o = body["order"]
    assert o["is_test"] is True and o["payment_status"] == "pending_platform"
    assert o["items"][0]["notes"] == "sem picles" and o["items"][1]["quantity"] == 2
    call("PUT", f"/api/orders/{o['id']}/item/{o['items'][0]['id']}/status", token=T_KITCHEN,
         body={"status": "preparing"})
    env.run_scheduled()
    assert env.sent == []  # nunca chama a NostFood
    assert call("POST", f"{N}/simular", token=T_CASHIER)[0] == 403


def test_test_orders_stay_out_of_cash_stock_and_can_be_deleted(env):
    link_all(env)
    _, body = call("POST", f"{N}/simular", token=T_ADMIN, body={"payment_method": "dinheiro"})
    o = body["order"]
    assert o["payment_status"] == "to_collect" and nf.excluded_from_cash(o)
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 0
    assert asyncio.run(nf.pending_to_collect()) == []
    # não registra dinheiro no caixa; finaliza sem pagamento
    assert call("POST", f"/api/orders/{o['id']}/close", token=T_CASHIER,
                body={"payments": [{"method": "cash", "amount": 49.0}]})[0] == 409
    for item in o["items"]:
        call("PUT", f"/api/orders/{o['id']}/item/{item['id']}/status", token=T_KITCHEN, body={"status": "delivered"})
    assert call("POST", f"/api/orders/{o['id']}/complete-online", token=T_CASHIER)[0] == 200
    assert env.db.payments.docs == [] and env.db.cash_registers.docs[0]["total_sales"] == 0
    assert stock(env, "s-coca") == 24 and stock(env, "s-pao") == 10       # fora do CMV
    # cancelamento de teste não gera perda
    _, body = call("POST", f"{N}/simular", token=T_ADMIN)
    t2 = body["order"]
    call("PUT", f"/api/orders/{t2['id']}/item/{t2['items'][0]['id']}/status", token=T_KITCHEN,
         body={"status": "preparing"})
    asyncio.run(nf.cancel_external(t2["external_id"], None, "teste", "teste"))
    assert env.db.stock_losses.docs == []
    # apagar: só admin
    assert call("DELETE", f"{N}/testes", token=T_CASHIER)[0] == 403
    status, res = call("DELETE", f"{N}/testes", token=T_ADMIN)
    assert status == 200 and res["deleted"] == 2 and orders(env) == []


# ==================== caixa: cancelado e "Não recebido" ====================
def test_cancelled_to_collect_does_not_block_cash(env):
    link_all(env)
    send_event("order.created", remote_order(payment="dinheiro"), event_id="e1")
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 1
    assert len(asyncio.run(nf.pending_to_collect())) == 1
    send_event("order.cancelled", {"order_number": "PED-498"}, event_id="e2")
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 0
    assert asyncio.run(nf.pending_to_collect()) == []


def test_not_received(env):
    link_all(env)
    send_event("order.created", remote_order(payment="dinheiro"), event_id="e1")
    o = orders(env)[0]
    url = f"{N}/pedidos/{o['id']}/nao-recebido"
    assert call("POST", url, token=T_CASHIER, body={"reason": "cliente sumiu"})[0] == 403
    assert call("POST", url, token=T_ADMIN, body={"reason": "  "})[0] == 400
    status, updated = call("POST", url, token=T_ADMIN, body={"reason": "Cliente não estava em casa"})
    assert status == 200
    assert updated["is_closed"] is True and updated["payment_status"] == "not_received"
    assert updated["not_received"]["by_name"] == "Admin" and updated["not_received"]["at"]
    assert updated["not_received"]["reason"] == "Cliente não estava em casa"
    assert asyncio.run(env.db.orders.count_documents(nf.OPEN_CASH_ORDERS_QUERY)) == 0  # libera o caixa
    assert nf.excluded_from_cash(updated)                                             # não é venda
    assert env.db.payments.docs == [] and env.db.cash_registers.docs[0]["total_sales"] == 0
    loss = env.db.stock_losses.docs[0]
    assert loss["kind"] == "not_received" and loss["total_cost"] == pytest.approx(7.5 + 2 * 2.5)
    listed = asyncio.run(nf.not_received_between("2000-01-01", "2999-01-01"))
    assert listed[0]["reason"] == "Cliente não estava em casa"
    assert call("POST", url, token=T_ADMIN, body={"reason": "de novo"})[0] == 409
    # pedido pago online não pode ser "Não recebido"
    send_event("order.created", remote_order(600, id=600), event_id="e2", resource_id="600")
    online = orders(env)[1]
    assert call("POST", f"{N}/pedidos/{online['id']}/nao-recebido", token=T_ADMIN,
                body={"reason": "x"})[0] == 409
