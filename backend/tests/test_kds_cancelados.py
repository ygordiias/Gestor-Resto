"""Aviso de cancelado no KDS para QUALQUER pedido (não só NostFood).

- Item cancelado numa mesa (pedido continua aberto): aparece no KDS da tela do
  item até ela dar "Ciente".
- Pedido de salão cancelado inteiro: aparece até cozinha e bar darem "Ciente".

Teste OFFLINE. Rodar: cd backend && python -m pytest tests/test_kds_cancelados.py
"""
import pytest

import kds_cancel
from _offline_app import call, server, token_for
from test_nostfood_integration import (  # noqa: F401  (env é fixture)
    ADMIN, N, T_ADMIN, T_CASHIER, T_KITCHEN, env,
)

BAR = {"id": "u-bar", "name": "Barman", "email": "b@x", "role": "bar", "is_active": True}
WAITER = {"id": "u-garcom", "name": "Garçom", "email": "g@x", "role": "waiter", "is_active": True}
T_BAR, T_WAITER = token_for(BAR["id"]), token_for(WAITER["id"])
ADMIN_PASSWORD = "senha-admin-kds-1"
PHONE, ADDRESS = "16988887777", "Rua das Flores, 123"


@pytest.fixture
def salon(env):
    """Mesa 5, comanda 210, com 1 Sansão (cozinha) e 2 Cocas (bar), e dados de cliente."""
    for u in env.db.users.docs:
        if u["id"] == ADMIN["id"]:
            u["password"] = server.get_password_hash(ADMIN_PASSWORD)
    env.db.users.docs += [dict(BAR), dict(WAITER)]
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


def _order(env, oid="o-mesa"):
    return next(o for o in env.db.orders.docs if o["id"] == oid)


def _item(order, iid):
    return next(i for i in order["items"] if i["id"] == iid)


def _cancel_item(item_id, qty, reason="cliente desistiu"):
    return call("PATCH", f"/api/orders/o-mesa/item/{item_id}/cancel", token=T_CASHIER, body={
        "quantity": qty, "reason": reason, "admin_email": ADMIN["email"], "admin_password": ADMIN_PASSWORD})


def _listed(token):
    status, rows = call("GET", f"{N}/kds/cancelados", token=token)
    assert status == 200
    return rows


def _ack(token, station, oid="o-mesa"):
    return call("POST", f"{N}/pedidos/{oid}/cancelamento/ciente", token=token, body={"station": station})


# ==================== item cancelado de mesa ====================
def test_item_cancelado_de_mesa_fica_no_kds_ate_ciente(salon):
    status, _ = _cancel_item("i-sansao", 1, reason="cliente desistiu")
    assert status == 200
    o = _order(salon)
    assert o["is_closed"] is False and o["kds_item_cancel_pending"] is True
    item = _item(o, "i-sansao")
    assert item["status"] == "cancelled" and item["kds_item_cancel"] and item["kds_ack_pending"]
    assert item["status_before_cancel"] == "preparing"

    # Cozinha vê o item cancelado, com motivo e quem cancelou, sem dados pessoais.
    (row,) = _listed(T_KITCHEN)
    assert row["id"] == "o-mesa" and row["table_number"] == 5 and row["tab_number"] == 210
    assert row["customer_name"] == "Joana"
    assert "customer_phone" not in row and "address" not in row
    seen = _item(row, "i-sansao")
    assert seen["kds_ack_pending"] and seen["cancellation_reason"] == "cliente desistiu"
    assert seen["cancelled_by_name"] == "Admin"
    # Caixa e admin recebem o pedido completo.
    assert _listed(T_CASHIER)[0]["customer_phone"] == PHONE

    # O som/refresh do KDS é avisado só com o id, para todos os logados.
    assert ("kds_cancelled", {"order_id": "o-mesa"}) in salon.emitted

    # "Ciente" do bar não tira o item da cozinha.
    assert _ack(T_BAR, "bar")[0] == 200
    assert _item(_order(salon), "i-sansao")["kds_ack_pending"] is True
    assert len(_listed(T_KITCHEN)) == 1

    status, acked = _ack(T_KITCHEN, "kitchen")
    assert status == 200 and "customer_phone" not in acked
    assert _item(acked, "i-sansao")["cancel_acks"]["kitchen"]["by_name"] == "Cozinheiro"
    assert _order(salon)["kds_item_cancel_pending"] is False
    assert _listed(T_KITCHEN) == []
    # A Coca segue no pedido, sem aviso.
    assert _item(_order(salon), "i-coca")["status"] == "pending"


def test_cancelamento_parcial_de_bebida_avisa_o_bar(salon):
    assert _cancel_item("i-coca", 1)[0] == 200
    o = _order(salon)
    assert _item(o, "i-coca")["quantity"] == 1 and "kds_item_cancel" not in _item(o, "i-coca")
    line = next(i for i in o["items"] if i["id"] not in ("i-sansao", "i-coca"))
    assert line["quantity"] == 1 and line["kds_item_cancel"] and line["type"] == "drink"
    # A cozinha não tem item cancelado: o "Ciente" dela não muda nada.
    _ack(T_KITCHEN, "kitchen")
    assert _order(salon)["kds_item_cancel_pending"] is True
    _ack(T_BAR, "bar")
    assert _order(salon)["kds_item_cancel_pending"] is False and _listed(T_BAR) == []


def test_item_ja_entregue_cancelado_nao_avisa(salon):
    _item(_order(salon), "i-coca")["status"] = "delivered"
    assert _cancel_item("i-coca", 2)[0] == 200
    assert not _order(salon).get("kds_item_cancel_pending")
    assert _listed(T_BAR) == []


def test_ciente_sem_cancelamento_pendente_e_404(salon):
    assert _ack(T_KITCHEN, "kitchen")[0] == 404


# ==================== pedido de salão cancelado ====================
def test_pedido_de_salao_cancelado_fica_no_kds_ate_cozinha_e_bar(salon):
    status, _ = call("PATCH", "/api/orders/o-mesa/cancel", token=T_CASHIER, body={
        "reason": "mesa foi embora", "admin_email": ADMIN["email"], "admin_password": ADMIN_PASSWORD})
    assert status == 200
    o = _order(salon)
    assert o["status"] == "cancelled" and o["kds_ack_pending"] is True and o["cancel_acks"] == {}

    (row,) = _listed(T_KITCHEN)
    assert row["status"] == "cancelled" and row["cancellation_reason"] == "mesa foi embora"
    assert row["cancelled_by_name"] == "Admin" and row["customer_name"] == "Joana"
    assert "customer_phone" not in row and "address" not in row
    assert {i["id"] for i in row["items"]} == {"i-sansao", "i-coca"}
    assert ("kds_cancelled", {"order_id": "o-mesa"}) in salon.emitted

    _ack(T_KITCHEN, "kitchen")
    assert _order(salon)["kds_ack_pending"] is True  # falta o bar (tem Coca)
    _ack(T_BAR, "bar")
    assert _order(salon)["kds_ack_pending"] is False
    assert _listed(T_KITCHEN) == [] and _listed(T_BAR) == []


def test_pedido_cancelado_sem_itens_de_cozinha_ou_bar_nao_avisa(salon):
    _order(salon)["items"] = [{"id": "x", "product_name": "Taxa", "type": "other", "quantity": 1,
                               "unit_price": 1.0, "status": "pending"}]
    call("PATCH", "/api/orders/o-mesa/cancel", token=T_CASHIER, body={
        "reason": "x", "admin_email": ADMIN["email"], "admin_password": ADMIN_PASSWORD})
    assert _order(salon)["kds_ack_pending"] is False


def test_cancelamento_rapido_avisa_o_kds(salon):
    for item in _order(salon)["items"]:
        item["status"] = "pending"
    assert call("POST", "/api/orders/o-mesa/cancel-quick", token=T_CASHIER)[0] == 403
    assert call("POST", "/api/orders/o-mesa/cancel-quick", token=T_ADMIN)[0] == 200
    o = _order(salon)
    assert o["kds_ack_pending"] is True and o["cancelled_by_name"] == "Admin"
    assert all(i["status_before_cancel"] == "pending" for i in o["items"])
    assert {i["id"] for i in _listed(T_BAR)[0]["items"]} == {"i-sansao", "i-coca"}


def test_item_cancelado_antes_nao_volta_no_card_do_pedido_inteiro():
    order = {"status": "cancelled", "items": [
        {"id": "a", "type": "food", "status": "pending"},
        {"id": "b", "type": "drink", "status": "cancelled", "status_before_cancel": "pending",
         "kds_item_cancel": True, "kds_ack_pending": False},
        {"id": "c", "type": "drink", "status": "cancelled"},  # cancelado antes desta mudança
    ]}
    assert [i["id"] for i in kds_cancel.whole_order_items(order)] == ["a"]
    assert kds_cancel.order_cancel_fields(order) == {"kds_ack_pending": True, "cancel_acks": {}}
