"""POST /api/orders: item cancelado não volta a somar quando entra item novo.

Teste OFFLINE (banco falso em memória, sem servidor e sem rede).
Rodar: cd backend && python -m pytest tests/test_order_total_cancelled.py
"""
import pytest

from _fake_mongo import FakeDB
from _offline_app import call, server, token_for

GARCOM = {"id": "u-garcom", "name": "Garçom", "email": "g@x", "role": "waiter", "is_active": True}


def item(item_id, price, qty, status="pending"):
    return {"id": item_id, "product_id": f"p-{item_id}", "product_name": item_id, "quantity": qty,
            "unit_price": price, "type": "food", "status": status, "is_courtesy": False,
            "stock_deducted": False, "created_at": "2026-11-24T12:00:00+00:00"}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.users.docs.append(dict(GARCOM))
    fake.tables.docs.append({"id": "t-1", "number": 1, "capacity": 4, "status": "occupied"})
    # Comanda 205: 2 x 30 ativos e uma linha de 1 x 50 cancelada (cancelamento já recalculou: 60 + 10%).
    fake.orders.docs.append({
        "id": "o-1", "table_id": "t-1", "table_number": 1, "tab_number": 205,
        "items": [item("burger", 30.0, 2), item("vinho", 50.0, 1, status="cancelled")],
        "status": "pending", "subtotal": 60.0, "service_fee": 6.0, "total": 66.0,
        "service_fee_percentage": 10, "is_closed": False, "waiter_id": GARCOM["id"],
    })
    monkeypatch.setattr(server, "db", fake)
    return fake


def test_item_novo_nao_ressuscita_cancelado(db):
    status, body = call("POST", "/api/orders", token=token_for(GARCOM["id"]), body={
        "table_id": "t-1", "table_number": 1, "tab_number": 205,
        "items": [{"product_id": "p-suco", "product_name": "Suco", "quantity": 1,
                   "unit_price": 8.0, "type": "drink"}],
    })
    assert status == 200
    # 60 + 8 = 68; o vinho cancelado (50) continua fora
    assert body["subtotal"] == 68.0
    assert body["service_fee"] == pytest.approx(6.8)
    assert body["total"] == pytest.approx(74.8)
    # a linha cancelada continua no histórico
    assert [i["status"] for i in body["items"]] == ["pending", "cancelled", "pending"]
