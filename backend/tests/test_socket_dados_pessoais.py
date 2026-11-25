"""Nenhum evento de Socket.IO para cozinha, bar ou garçom leva telefone ou
endereço do cliente; alertas e estoque vão só para admin.

Teste OFFLINE. Rodar: cd backend && python -m pytest tests/test_socket_dados_pessoais.py
"""
from pathlib import Path

import pytest

import nostfood_integration as nf
from _offline_app import call, server, token_for
from test_nostfood_integration import (  # noqa: F401  (env é fixture)
    ADMIN, N, T_CASHIER, T_KITCHEN, env, link_all, orders, real_order, remote_order, send_event,
)

BAR = {"id": "u-bar", "name": "Barman", "email": "b@x", "role": "bar", "is_active": True}
T_BAR = token_for(BAR["id"])
ADMIN_PASSWORD = "senha-admin-kds-1"
PHONE, ADDRESS = "16988887777", "Rua das Flores, 123"

PII_KEYS = {"customer_phone", "address", "change_for", "customer_address", "latitude", "longitude"}
KDS_ROOMS = {"role:kitchen", "role:bar", "role:waiter"}
FULL_ROOMS = {"role:superadmin", "role:admin", "role:cashier"}
ADMIN_ROOMS = {"role:superadmin", "role:admin"}


@pytest.fixture
def salon(env):
    """Mesa 5, comanda 210, com 1 Sansão (cozinha) e 2 Cocas (bar), e dados de cliente."""
    for u in env.db.users.docs:
        if u["id"] == ADMIN["id"]:
            u["password"] = server.get_password_hash(ADMIN_PASSWORD)
    env.db.users.docs.append(dict(BAR))
    env.db.tables.docs.append({"id": "mesa-5", "number": 5, "status": "occupied", "active_order_id": "o-mesa"})
    env.db.orders.docs.append({
        "id": "o-mesa", "table_id": "mesa-5", "table_number": 5, "tab_number": 210, "source": "salon",
        "is_closed": False, "status": "pending", "service_fee_percentage": 10,
        "subtotal": 44.0, "service_fee": 4.4, "total": 48.4, "created_at": "2026-11-25T12:00:00+00:00",
        "customer_name": "Joana Prado Lima", "customer_phone": PHONE, "address": ADDRESS,
        "items": [
            {"id": "i-sansao", "product_id": "p-sansao", "product_name": "Sansão", "type": "food",
             "quantity": 1, "unit_price": 32.0, "status": "preparing", "stock_deducted": False},
            {"id": "i-coca", "product_id": "p-coca", "product_name": "Coca-Cola Lata", "type": "drink",
             "quantity": 2, "unit_price": 6.0, "status": "pending", "stock_deducted": False},
        ],
    })
    return env


def _walk(data):
    """Todas as chaves e valores em texto, em qualquer nível."""
    if isinstance(data, dict):
        for k, v in data.items():
            yield ("key", k)
            yield from _walk(v)
    elif isinstance(data, list):
        for v in data:
            yield from _walk(v)
    elif isinstance(data, str):
        yield ("value", data)


@pytest.fixture
def rooms(salon, monkeypatch):
    sent = []

    async def fake_emit(event, data=None, room=None, **kw):
        rooms_ = {room} if isinstance(room, str) else set(room or [])
        sent.append((event, data, rooms_))
        salon.emitted.append((event, data))
    monkeypatch.setattr(server.sio, "emit", fake_emit)
    return sent


def test_nenhum_evento_para_cozinha_ou_bar_leva_telefone_ou_endereco(salon, rooms):
    link_all(salon)
    # NostFood: pedido real da 99 (com telefone, endereço e coordenadas) e pedido antigo.
    send_event("order.created", real_order(), event_id="r1", resource_id="900001")
    send_event("order.created", remote_order(), event_id="r2")
    nf_order = next(o for o in orders(salon) if o["external_id"] == "498")
    assert nf_order["customer_phone"] and nf_order["customer_address"] and nf_order["latitude"]
    sansao = next(i for i in nf_order["items"] if i["product_name"] == "Sansão")
    call("PUT", f"/api/orders/{nf_order['id']}/item/{sansao['id']}/status", token=T_KITCHEN,
         body={"status": "preparing"})
    call("POST", f"{N}/pedidos/{nf_order['id']}/observacao", token=T_CASHIER, body={"text": "Sem cebola"})
    send_event("order.created", remote_order(oid=499, items=[{"id": 99, "name": "Prato novo", "quantity": 1,
                                                                 "price": 10.0}]), event_id="r3", resource_id="499")
    send_event("order.cancelled", {"order_number": "PED-498"}, event_id="r4")
    call("POST", f"{N}/pedidos/{nf_order['id']}/cancelamento/ciente", token=T_KITCHEN, body={"station": "kitchen"})
    # Salão: item cancelado e depois o pedido inteiro.
    call("PATCH", "/api/orders/o-mesa/item/i-coca/cancel", token=T_CASHIER, body={
        "quantity": 1, "reason": "x", "admin_email": ADMIN["email"], "admin_password": ADMIN_PASSWORD})
    call("PATCH", "/api/orders/o-mesa/cancel", token=T_CASHIER, body={
        "reason": "x", "admin_email": ADMIN["email"], "admin_password": ADMIN_PASSWORD})

    assert rooms, "esperava eventos"
    events = {e for e, _, _ in rooms}
    for expected in ("kitchen_update", "bar_update", "new_online_order", "order_observation",
                     "order_cancelled", "kds_cancelled", "nostfood_alert", "order_updated"):
        assert expected in events, expected

    leaked_values = {PHONE, ADDRESS, "16999990000", "16900000000", "Rua A", "Rua Fictícia",
                     "Joana Prado Lima", "Cliente Fixture"}
    reached_kds = 0
    for event, data, to in rooms:
        assert to, f"{event} sem sala"
        if to & KDS_ROOMS:
            reached_kds += 1
            assert not (to & FULL_ROOMS), f"{event}: a mesma cópia foi para caixa e cozinha"
            for kind, v in _walk(data):
                assert not (kind == "key" and v in PII_KEYS), f"{event} levou {v}"
                assert not (kind == "value" and v in leaked_values), f"{event} levou {v!r}"
        if event in ("nostfood_alert", "stock_updated"):
            assert to == ADMIN_ROOMS, f"{event} foi para {to}"
    assert reached_kds > 0
    # Admin e caixa recebem o pedido completo.
    full = [d for e, d, to in rooms if e == "kitchen_update" and to == FULL_ROOMS]
    assert any(o.get("customer_phone") == "16999990000" for lst in full for o in lst)


def test_ciente_do_kds_nao_devolve_dados_pessoais(salon):
    link_all(salon)
    send_event("order.created", remote_order(), event_id="e1")
    send_event("order.cancelled", {"order_number": "PED-498"}, event_id="e2")
    oid = orders(salon)[0]["id"]
    status, o = call("POST", f"{N}/pedidos/{oid}/cancelamento/ciente", token=T_KITCHEN, body={"station": "kitchen"})
    assert status == 200 and o["customer_name"] == "Maria"
    assert not (PII_KEYS & set(o))


def test_nostfood_so_emite_pelas_funcoes_por_sala():
    src = Path(nf.__file__).read_text(encoding="utf-8")
    assert "sio.emit" not in src
    assert src.count("S.emit_") >= 12


def test_strip_customer_data_tira_endereco_da_nostfood():
    clean = server.strip_customer_data({"customer_name": "Ana Lima", "customer_address": {"street": "Rua"},
                                        "latitude": -20.5, "longitude": -47.4, "customer_phone": "1"})
    assert clean == {"customer_name": "Ana"}
