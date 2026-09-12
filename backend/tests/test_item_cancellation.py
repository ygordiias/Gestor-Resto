"""Testes de STEP 2 — Cancelamento individual de item com decisão de estoque.

Cobre:
  A. Item ainda nao entregue (stock_deducted=False) -> cancela; nao ha dedução.
  B. Item ja entregue, escolher NAO -> mantem baixa.
  C. Item ja entregue, escolher SIM -> restaura exato.
  D. Produto com receita -> restaura ingredientes corretos.
  E. Parcial (3 -> cancelar 1) -> 2 ativos, 1 cancelado no historico.
  F. Recalculo de subtotal / service_fee / total ignora itens cancelados.
  G. Sem credenciais de admin -> 400/403.
  H. Pedido fechado -> nao aceita cancelamento (400).
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("TEST_BACKEND_URL", "http://localhost:8001")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@teste.com"
ADMIN_PASSWORD = "123456"
CASHIER_EMAIL = "caixa@digitalcodex.com"
CASHIER_PASSWORD = "caixa123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get(token, path):
    r = requests.get(f"{API}{path}", headers=_auth_headers(token), timeout=5)
    r.raise_for_status()
    return r.json()


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def cashier():
    return _login(CASHIER_EMAIL, CASHIER_PASSWORD)


def _create_stock_direct(admin_token, name, qty, unit_cost=1.0):
    cats = _get(admin_token, "/categories")
    if not cats:
        rc = requests.post(f"{API}/categories", headers=_auth_headers(admin_token),
                           json={"name": f"CatTest{uuid.uuid4().hex[:6]}", "type": "food"}, timeout=5)
        rc.raise_for_status()
        cat = rc.json()
    else:
        cat = cats[0]
    rp = requests.post(f"{API}/products", headers=_auth_headers(admin_token), json={
        "name": name,
        "price": 10.0,
        "category_id": cat["id"],
        "type": "food",
        "available": True,
    }, timeout=5)
    rp.raise_for_status()
    prod = rp.json()
    rs = requests.post(f"{API}/stock", headers=_auth_headers(admin_token), json={
        "product_id": prod["id"],
        "quantity": qty,
        "min_quantity": 0,
        "unit_cost": unit_cost,
        "unit": "unit",
        "stock_type": "finished",
    }, timeout=5)
    rs.raise_for_status()
    return prod, rs.json()


def _create_table(admin_token):
    tables = _get(admin_token, "/tables")
    available = [t for t in tables if t.get("status") == "available"]
    if available:
        return available[0]
    rt = requests.post(f"{API}/tables", headers=_auth_headers(admin_token),
                       json={"number": 9999, "capacity": 4}, timeout=5)
    rt.raise_for_status()
    return rt.json()


def _create_order(token, table, product, qty):
    r = requests.post(f"{API}/orders", headers=_auth_headers(token), json={
        "table_id": table["id"],
        "table_number": table["number"],
        "items": [{
            "product_id": product["id"],
            "product_name": product["name"],
            "quantity": qty,
            "unit_price": product["price"],
            "type": product.get("type", "food"),
        }],
    }, timeout=5)
    r.raise_for_status()
    return r.json()


def _stock_qty(admin_token, stock_id):
    for s in _get(admin_token, "/stock"):
        if s["id"] == stock_id:
            return float(s["quantity"])
    raise AssertionError(f"stock {stock_id} nao encontrado")


def _mark_item_delivered(order_id, item_id):
    r = requests.put(f"{API}/orders/{order_id}/item/{item_id}/status",
                     json={"status": "delivered"}, timeout=5)
    r.raise_for_status()


def _cancel_item(cashier_token, order_id, item_id, qty,
                 reason="teste", restore=False,
                 admin_email=ADMIN_EMAIL, admin_password=ADMIN_PASSWORD):
    return requests.patch(
        f"{API}/orders/{order_id}/item/{item_id}/cancel",
        headers=_auth_headers(cashier_token),
        json={
            "quantity": qty,
            "reason": reason,
            "admin_email": admin_email,
            "admin_password": admin_password,
            "restore_stock": restore,
        },
        timeout=5,
    )


# ==================== CASE A ====================
def test_a_cancel_before_delivery_does_not_deduct_stock(admin, cashier):
    prod, stock = _create_stock_direct(admin, f"ProdA-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 2)
    item_id = order["items"][0]["id"]
    qty_before = _stock_qty(admin, stock["id"])
    r = _cancel_item(cashier, order["id"], item_id, 2, reason="test A")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cancelled_qty"] == 2
    assert body["stock_restored"] is False
    assert _stock_qty(admin, stock["id"]) == qty_before


# ==================== CASE B ====================
def test_b_cancel_after_delivery_choose_no_keeps_deduction(admin, cashier):
    prod, stock = _create_stock_direct(admin, f"ProdB-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 2)
    item_id = order["items"][0]["id"]
    _mark_item_delivered(order["id"], item_id)
    assert _stock_qty(admin, stock["id"]) == 8
    r = _cancel_item(cashier, order["id"], item_id, 2, reason="test B", restore=False)
    assert r.status_code == 200, r.text
    assert r.json()["stock_restored"] is False
    assert _stock_qty(admin, stock["id"]) == 8


# ==================== CASE C ====================
def test_c_cancel_after_delivery_choose_yes_restores_stock_exactly_once(admin, cashier):
    prod, stock = _create_stock_direct(admin, f"ProdC-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 3)
    item_id = order["items"][0]["id"]
    _mark_item_delivered(order["id"], item_id)
    assert _stock_qty(admin, stock["id"]) == 7
    r = _cancel_item(cashier, order["id"], item_id, 3, reason="test C", restore=True)
    assert r.status_code == 200, r.text
    assert r.json()["stock_restored"] is True
    assert _stock_qty(admin, stock["id"]) == 10
    r2 = _cancel_item(cashier, order["id"], item_id, 1, reason="dup", restore=True)
    assert r2.status_code == 400


# ==================== CASE D ====================
def test_d_recipe_product_restore_ingredients_correctly(admin, cashier):
    r1 = requests.post(f"{API}/stock", headers=_auth_headers(admin), json={
        "name": f"IngX-{uuid.uuid4().hex[:5]}", "quantity": 100, "min_quantity": 0,
        "unit_cost": 1.0, "unit": "gram", "stock_type": "raw_material",
    }, timeout=5)
    r1.raise_for_status()
    ing1 = r1.json()
    r2 = requests.post(f"{API}/stock", headers=_auth_headers(admin), json={
        "name": f"IngY-{uuid.uuid4().hex[:5]}", "quantity": 50, "min_quantity": 0,
        "unit_cost": 2.0, "unit": "gram", "stock_type": "raw_material",
    }, timeout=5)
    r2.raise_for_status()
    ing2 = r2.json()
    cats = _get(admin, "/categories")
    cat = cats[0]
    rp = requests.post(f"{API}/products", headers=_auth_headers(admin), json={
        "name": f"BurgerD-{uuid.uuid4().hex[:5]}", "price": 25.0, "category_id": cat["id"],
        "type": "food", "available": True,
    }, timeout=5)
    rp.raise_for_status()
    prod = rp.json()
    rr = requests.post(f"{API}/recipes", headers=_auth_headers(admin), json={
        "product_id": prod["id"],
        "ingredients": [
            {"stock_item_id": ing1["id"], "quantity": 2},
            {"stock_item_id": ing2["id"], "quantity": 1},
        ],
    }, timeout=5)
    rr.raise_for_status()
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 2)
    item_id = order["items"][0]["id"]
    _mark_item_delivered(order["id"], item_id)
    assert _stock_qty(admin, ing1["id"]) == 96
    assert _stock_qty(admin, ing2["id"]) == 48
    r = _cancel_item(cashier, order["id"], item_id, 2, reason="test D recipe", restore=True)
    assert r.status_code == 200, r.text
    assert _stock_qty(admin, ing1["id"]) == 100
    assert _stock_qty(admin, ing2["id"]) == 50


# ==================== CASE E ====================
def test_e_partial_cancellation_split_line_preserves_history(admin, cashier):
    prod, _stock = _create_stock_direct(admin, f"ProdE-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 3)
    item_id = order["items"][0]["id"]
    r = _cancel_item(cashier, order["id"], item_id, 1, reason="test E parcial")
    assert r.status_code == 200, r.text
    updated = r.json()["order"]
    active = [it for it in updated["items"] if it.get("status") != "cancelled" and it.get("product_id") == prod["id"]]
    cancelled = [it for it in updated["items"] if it.get("status") == "cancelled" and it.get("product_id") == prod["id"]]
    assert len(active) == 1 and active[0]["quantity"] == 2
    assert len(cancelled) == 1 and cancelled[0]["quantity"] == 1
    assert cancelled[0]["cancellation_reason"] == "test E parcial"
    assert cancelled[0]["cancelled_by_name"]
    assert cancelled[0]["cancelled_by_cashier_name"]


# ==================== CASE F ====================
def test_f_totals_recalculated_ignoring_cancelled_items(admin, cashier):
    prod, _stock = _create_stock_direct(admin, f"ProdF-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 3)
    item_id = order["items"][0]["id"]
    assert order["subtotal"] == 30.0
    r = _cancel_item(cashier, order["id"], item_id, 1, reason="test F")
    assert r.status_code == 200, r.text
    updated = r.json()["order"]
    assert updated["subtotal"] == 20.0
    assert round(updated["service_fee"], 2) == 2.0
    assert round(updated["total"], 2) == 22.0


# ==================== CASE G ====================
def test_g_authorization_required(admin, cashier):
    prod, _stock = _create_stock_direct(admin, f"ProdG-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 1)
    item_id = order["items"][0]["id"]
    r = requests.patch(
        f"{API}/orders/{order['id']}/item/{item_id}/cancel",
        headers=_auth_headers(cashier),
        json={"quantity": 1, "reason": "sem admin"},
        timeout=5,
    )
    assert r.status_code == 400
    r2 = _cancel_item(cashier, order["id"], item_id, 1, reason="ok", admin_password="senha-errada")
    assert r2.status_code == 403
    r3 = _cancel_item(cashier, order["id"], item_id, 1, reason="ok",
                      admin_email=CASHIER_EMAIL, admin_password=CASHIER_PASSWORD)
    assert r3.status_code == 403


# ==================== CASE H ====================
def test_h_closed_order_is_read_only(admin, cashier):
    prod, _stock = _create_stock_direct(admin, f"ProdH-{uuid.uuid4().hex[:6]}", 10)
    table = _create_table(admin)
    order = _create_order(cashier, table, prod, 1)
    item_id = order["items"][0]["id"]
    _mark_item_delivered(order["id"], item_id)
    rc = requests.post(f"{API}/orders/{order['id']}/close",
                       headers=_auth_headers(cashier),
                       json={"payments": [{"method": "cash", "amount": 11.0}]}, timeout=5)
    rc.raise_for_status()
    r = _cancel_item(cashier, order["id"], item_id, 1, reason="tentativa apos fechar")
    assert r.status_code == 400
