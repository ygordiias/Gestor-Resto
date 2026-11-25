"""PATCH /api/orders/{id}/item/{item}/courtesy: desmarcar devolve o preço original.

Teste OFFLINE (banco falso em memória, sem servidor e sem rede).
Rodar: cd backend && python -m pytest tests/test_courtesy_restore_price.py
"""
import pytest

from _fake_mongo import FakeDB
from _offline_app import call, server, token_for

CAIXA = {"id": "u-caixa", "name": "Caixa", "email": "c@x", "role": "cashier", "is_active": True}


def order_with(item):
    return {"id": "o-1", "table_id": "t-1", "table_number": 1, "tab_number": 210,
            "items": [item, {"id": "i-2", "product_id": "p-suco", "product_name": "Suco", "quantity": 1,
                             "unit_price": 8.0, "type": "drink", "status": "pending"}],
            "status": "pending", "service_fee_percentage": 10, "is_closed": False}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.users.docs.append(dict(CAIXA))
    fake.products.docs.append({"id": "p-burger", "name": "Burger", "price": 35.0})
    monkeypatch.setattr(server, "db", fake)
    return fake


def courtesy(is_courtesy, reason="Aniversário"):
    return call("PATCH", "/api/orders/o-1/item/i-1/courtesy", token=token_for(CAIXA["id"]),
                body={"is_courtesy": is_courtesy, "reason": reason})


def test_marcar_e_desmarcar_volta_ao_preco_cobrado(db):
    # Preço lançado (32) diferente do cadastro atual (35): volta o lançado.
    db.orders.docs.append(order_with({"id": "i-1", "product_id": "p-burger", "product_name": "Burger",
                                      "quantity": 2, "unit_price": 32.0, "type": "food", "status": "pending"}))
    status, body = courtesy(True)
    assert status == 200 and body["items"][0]["unit_price"] == 0
    assert body["subtotal"] == 8.0

    # Marcar de novo não perde o preço guardado.
    assert courtesy(True)[0] == 200

    status, body = courtesy(False, reason="")
    assert status == 200
    it = body["items"][0]
    assert it["unit_price"] == 32.0 and it["is_courtesy"] is False and it["courtesy_reason"] is None
    assert "courtesy_original_price" not in it
    assert body["subtotal"] == 72.0
    assert body["service_fee"] == pytest.approx(7.2)
    assert body["total"] == pytest.approx(79.2)


def test_cortesia_antiga_sem_preco_guardado_usa_cadastro(db):
    db.orders.docs.append(order_with({"id": "i-1", "product_id": "p-burger", "product_name": "Burger",
                                      "quantity": 1, "unit_price": 0, "type": "food", "status": "pending",
                                      "is_courtesy": True, "courtesy_reason": "antes da correção"}))
    status, body = courtesy(False, reason="")
    assert status == 200
    assert body["items"][0]["unit_price"] == 35.0
    assert body["subtotal"] == 43.0


def test_desmarcar_item_que_nao_era_cortesia_nao_mexe_no_preco(db):
    db.orders.docs.append(order_with({"id": "i-1", "product_id": "p-burger", "product_name": "Burger",
                                      "quantity": 1, "unit_price": 30.0, "type": "food", "status": "pending"}))
    status, body = courtesy(False, reason="")
    assert status == 200 and body["items"][0]["unit_price"] == 30.0
