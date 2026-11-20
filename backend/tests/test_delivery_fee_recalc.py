"""Cancelar item e marcar cortesia mantêm a taxa de entrega no total.

Total = subtotal + serviço + taxa de entrega - descontos.
Teste OFFLINE. Rodar: cd backend && python -m pytest tests/test_delivery_fee_recalc.py
"""
import pytest

from _fake_mongo import FakeDB
from _offline_app import call, server, token_for

ADMIN = {"id": "u-admin", "name": "Admin", "email": "admin@x", "role": "admin", "is_active": True}
CASHIER = {"id": "u-caixa", "name": "Caixa", "email": "c@x", "role": "cashier", "is_active": True}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.users.docs += [dict(ADMIN, password=server.get_password_hash("senha-admin-1")), dict(CASHIER)]
    fake.orders.docs.append({
        "id": "o1", "is_closed": False, "status": "pending", "service_fee_percentage": 0,
        "subtotal": 47.0, "service_fee": 0, "delivery_fee": 5.0, "total": 52.0,
        "items": [
            {"id": "i1", "product_id": "p1", "product_name": "Sansão", "quantity": 1, "unit_price": 35.0,
             "status": "pending", "stock_deducted": False},
            {"id": "i2", "product_id": "p2", "product_name": "Coca", "quantity": 2, "unit_price": 6.0,
             "status": "pending", "stock_deducted": False},
        ],
    })

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server.sio, "emit", noop)
    return fake


def _order(db):
    return db.orders.docs[0]


def test_cancel_item_keeps_delivery_fee(db):
    status, _ = call("PATCH", "/api/orders/o1/item/i2/cancel", token=token_for(CASHIER["id"]), body={
        "quantity": 1, "reason": "sem coca", "admin_email": "admin@x", "admin_password": "senha-admin-1"})
    assert status == 200
    assert _order(db)["subtotal"] == 41.0 and _order(db)["total"] == 46.0  # 41 + 5 de entrega


def test_courtesy_keeps_delivery_fee(db):
    status, _ = call("PATCH", "/api/orders/o1/item/i1/courtesy", token=token_for(CASHIER["id"]),
                     body={"reason": "aniversário"})
    assert status == 200
    assert _order(db)["subtotal"] == 12.0 and _order(db)["total"] == 17.0


def test_salon_order_without_delivery_fee_unchanged(db):
    _order(db).update({"delivery_fee": None, "service_fee_percentage": 10, "subtotal": 47.0})
    call("PATCH", "/api/orders/o1/item/i1/courtesy", token=token_for(CASHIER["id"]), body={"reason": "x"})
    assert _order(db)["total"] == pytest.approx(12.0 + 1.2)


def test_discount_is_subtracted_and_never_negative():
    assert server._order_total({"delivery_fee": 5, "discount": 2}, 10, 1) == 14.0
    assert server._order_total({"delivery_fee": 0, "discount": 50}, 10, 0) == 0.0
