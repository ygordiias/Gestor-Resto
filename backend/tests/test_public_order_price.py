"""POST /api/public/pedido: preço e nome vêm do cadastro, nunca do navegador.

Teste OFFLINE (banco falso em memória, sem servidor e sem rede).
Rodar: cd backend && python -m pytest tests/test_public_order_price.py
"""
import pytest

from _fake_mongo import FakeDB
from _offline_app import call, server

PRODUTO = {"id": "p-sansao", "name": "Sansão", "price": 32.0, "type": "food", "is_available": True}
BEBIDA = {"id": "p-coca", "name": "Coca-Cola lata", "price": 6.0, "type": "drink", "is_available": True}


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.products.docs.extend([dict(PRODUTO), dict(BEBIDA)])

    async def codigo():
        return "EM-0001"

    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "generate_order_code", codigo)
    return fake


def pedido(*items):
    return {"customer_name": "Cliente Teste", "customer_phone": "16900000000",
            "delivery_type": "retirada", "payment_method": "pix", "items": list(items)}


def test_preco_do_navegador_e_ignorado(db):
    status, body = call("POST", "/api/public/pedido", body=pedido(
        {"product_id": "p-sansao", "name": "Sansão", "price": 0.01, "quantity": 2},
        {"product_id": "p-coca", "name": "Brinde grátis", "price": 0, "quantity": 1},
    ))
    assert status == 200
    assert body["subtotal"] == 70.0 and body["total"] == 70.0

    order = db.orders.docs[0]
    assert [(i["product_name"], i["unit_price"], i["type"]) for i in order["items"]] == [
        ("Sansão", 32.0, "food"), ("Coca-Cola lata", 6.0, "drink")]
    assert order["subtotal"] == 70.0 and order["total"] == 70.0


def test_produto_inexistente_recusado(db):
    status, body = call("POST", "/api/public/pedido", body=pedido(
        {"product_id": "nao-existe", "name": "X", "price": 1, "quantity": 1}))
    assert status == 400
    assert db.orders.docs == []


def test_produto_indisponivel_recusado(db):
    db.products.docs[0]["is_available"] = False
    status, _ = call("POST", "/api/public/pedido", body=pedido(
        {"product_id": "p-sansao", "name": "Sansão", "price": 32.0, "quantity": 1}))
    assert status == 400
    assert db.orders.docs == []


@pytest.mark.parametrize("qty", [0, -3])
def test_quantidade_invalida_recusada(db, qty):
    status, _ = call("POST", "/api/public/pedido", body=pedido(
        {"product_id": "p-sansao", "name": "Sansão", "price": 32.0, "quantity": qty}))
    assert status == 400
    assert db.orders.docs == []
