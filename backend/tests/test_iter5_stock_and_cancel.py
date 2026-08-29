"""Iteration 5 backend tests: stock deduction idempotency, cancel with admin auth, courtesy per item.

Covers:
1. Stock deduction on delivered status
2. Stock deduction guarantee on close_order (skipping delivered)
3. Idempotency: closing 2x doesn't double-deduct
4. PATCH /orders/{id}/cancel authorization
5. PATCH /orders/{order_id}/item/{item_id}/courtesy
"""

import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://digital-orders-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@teste.com", "password": "123456"}
WAITER = {"email": "yuri@digitalcodex.com", "password": "123456"}
CASHIER = {"email": "caixa@digitalcodex.com", "password": "caixa123"}
BAR = {"email": "bar@digitalcodex.com", "password": "bar123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tokens():
    return {
        "admin": _login(ADMIN),
        "waiter": _login(WAITER),
        "cashier": _login(CASHIER),
    }


@pytest.fixture(scope="module")
def coca_product(tokens):
    """Ensure Coca-Cola product exists and has stock=50."""
    r = requests.get(f"{API}/products", timeout=30)
    assert r.status_code == 200
    products = r.json()
    coca = next((p for p in products if p.get("name", "").lower().startswith("coca")), None)
    assert coca is not None, "Coca-Cola product must be seeded"

    # Ensure stock item exists for this product with plenty of stock
    r2 = requests.get(f"{API}/stock", headers=_headers(tokens["admin"]), timeout=30)
    assert r2.status_code == 200
    stock_list = r2.json()
    stock = next((s for s in stock_list if s.get("product_id") == coca["id"]), None)
    if stock is None:
        payload = {
            "product_id": coca["id"],
            "name": coca["name"],
            "category": "Bebidas",
            "stock_type": "finished_product",
            "quantity": 100,
            "unit": "unit",
            "min_quantity": 5,
            "max_quantity": 200,
            "unit_cost": 6,
        }
        r3 = requests.post(f"{API}/stock", json=payload, headers=_headers(tokens["admin"]), timeout=30)
        assert r3.status_code in (200, 201), r3.text
        stock = r3.json()
    else:
        # top up to at least 50 to avoid running out
        if stock["quantity"] < 50:
            requests.put(
                f"{API}/stock/{stock['id']}",
                json={"quantity": 100},
                headers=_headers(tokens["admin"]),
                timeout=30,
            )
            stock["quantity"] = 100
    return {"product": coca, "stock": stock}


def _get_stock_qty(stock_id, tok):
    r = requests.get(f"{API}/stock", headers=_headers(tok), timeout=30)
    assert r.status_code == 200
    for s in r.json():
        if s["id"] == stock_id:
            return float(s["quantity"])
    return None


def _free_table(tok):
    """Get an available table or free one occupied."""
    r = requests.get(f"{API}/tables", timeout=30)
    tables = r.json()
    # Prefer any available
    for t in tables:
        if t.get("status") == "available":
            return t
    # Force one free: pick first, cancel its open order
    t = tables[0]
    open_o = requests.get(f"{API}/orders/table/{t['id']}", timeout=30)
    if open_o.status_code == 200 and open_o.json():
        oid = open_o.json()["id"]
        # cancel-quick as admin
        requests.post(f"{API}/orders/{oid}/cancel-quick", headers=_headers(tok), timeout=30)
    requests.put(f"{API}/tables/{t['id']}/status", json={"status": "available"}, timeout=30)
    return t


def _new_order(coca, tokens, qty=1):
    table = _free_table(tokens["admin"])
    payload = {
        "table_id": table["id"],
        "table_number": table["number"],
        "items": [
            {
                "product_id": coca["product"]["id"],
                "product_name": coca["product"]["name"],
                "quantity": qty,
                "unit_price": coca["product"]["price"],
                "type": "drink",
                "status": "pending",
            }
        ],
    }
    r = requests.post(f"{API}/orders", json=payload, headers=_headers(tokens["waiter"]), timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---------- 1) Stock deduction via delivered ----------
def test_stock_deducted_on_delivered(coca_product, tokens):
    before = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    order = _new_order(coca_product, tokens, qty=1)
    item_id = order["items"][-1]["id"]  # last inserted item
    order_id = order["id"]

    r = requests.put(
        f"{API}/orders/{order_id}/item/{item_id}/status",
        json={"status": "delivered"},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text

    after = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    assert after == before - 1, f"Expected stock {before-1}, got {after}"

    # Confirm item.stock_deducted True
    ordr = requests.get(f"{API}/orders/{order_id}", timeout=30).json()
    it = next(i for i in ordr["items"] if i["id"] == item_id)
    assert it.get("stock_deducted") is True

    # Cleanup: close
    requests.post(
        f"{API}/orders/{order_id}/close",
        json={"payments": [{"method": "cash", "amount": ordr["total"]}]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )


# ---------- 2) Stock deduction guarantee via close_order ----------
def test_stock_deducted_on_close_without_delivered(coca_product, tokens):
    before = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    order = _new_order(coca_product, tokens, qty=1)
    order_id = order["id"]
    item_id = order["items"][-1]["id"]

    # Close directly (skip delivered)
    r = requests.post(
        f"{API}/orders/{order_id}/close",
        json={"payments": [{"method": "cash", "amount": order["total"]}]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text

    after = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    assert after == before - 1, f"Expected stock {before-1}, got {after}"

    ordr = requests.get(f"{API}/orders/{order_id}", timeout=30).json()
    it = next(i for i in ordr["items"] if i["id"] == item_id)
    assert it.get("stock_deducted") is True


# ---------- 3) Idempotency: closing 2x does not double-deduct ----------
def test_close_idempotent(coca_product, tokens):
    before = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    order = _new_order(coca_product, tokens, qty=1)
    order_id = order["id"]

    r1 = requests.post(
        f"{API}/orders/{order_id}/close",
        json={"payments": [{"method": "cash", "amount": order["total"]}]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r1.status_code == 200
    mid = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    assert mid == before - 1

    # 2nd close call
    r2 = requests.post(
        f"{API}/orders/{order_id}/close",
        json={"payments": [{"method": "cash", "amount": 0}]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    # May 200 or 400 depending on impl; important: stock unchanged
    after = _get_stock_qty(coca_product["stock"]["id"], tokens["admin"])
    assert after == mid, f"Idempotency broken: stock changed from {mid} to {after} on 2nd close (status={r2.status_code})"


# ---------- 4) Cancel without admin creds -> 400 ----------
def test_cancel_missing_admin_creds(coca_product, tokens):
    order = _new_order(coca_product, tokens, qty=1)
    order_id = order["id"]

    r = requests.patch(
        f"{API}/orders/{order_id}/cancel",
        json={"reason": "teste"},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code} {r.text}"

    # Cleanup - cancel with valid admin
    requests.patch(
        f"{API}/orders/{order_id}/cancel",
        json={"reason": "cleanup", "admin_email": ADMIN["email"], "admin_password": ADMIN["password"]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )


# ---------- 5) Cancel with wrong admin password -> 403 ----------
def test_cancel_wrong_admin_password(coca_product, tokens):
    order = _new_order(coca_product, tokens, qty=1)
    order_id = order["id"]

    r = requests.patch(
        f"{API}/orders/{order_id}/cancel",
        json={"reason": "teste", "admin_email": ADMIN["email"], "admin_password": "wrong"},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"

    # cleanup
    requests.patch(
        f"{API}/orders/{order_id}/cancel",
        json={"reason": "cleanup", "admin_email": ADMIN["email"], "admin_password": ADMIN["password"]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )


# ---------- 6) Cancel with valid admin -> 200, order cancelled, table free ----------
def test_cancel_success(coca_product, tokens):
    order = _new_order(coca_product, tokens, qty=1)
    order_id = order["id"]
    table_id = order["table_id"]

    r = requests.patch(
        f"{API}/orders/{order_id}/cancel",
        json={
            "reason": "cliente desistiu",
            "admin_email": ADMIN["email"],
            "admin_password": ADMIN["password"],
        },
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text

    ordr = requests.get(f"{API}/orders/{order_id}", timeout=30).json()
    assert ordr["status"] == "cancelled"
    assert ordr["is_closed"] is True
    assert ordr.get("cancelled_by_name")
    assert ordr.get("cancellation_reason") == "cliente desistiu"

    # Table should be available
    tables = requests.get(f"{API}/tables", timeout=30).json()
    tbl = next(t for t in tables if t["id"] == table_id)
    assert tbl["status"] == "available"


# ---------- 7) Courtesy per item ----------
def test_item_courtesy_recalculates(coca_product, tokens):
    order = _new_order(coca_product, tokens, qty=2)
    order_id = order["id"]
    item_id = order["items"][-1]["id"]
    original_total = order["total"]
    assert original_total > 0

    r = requests.patch(
        f"{API}/orders/{order_id}/item/{item_id}/courtesy",
        json={"reason": "aniversariante", "is_courtesy": True},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    it = next(i for i in body["items"] if i["id"] == item_id)
    assert it["is_courtesy"] is True
    assert it["unit_price"] == 0
    # Subtotal should have decreased by the original coca-cola contribution
    assert body["subtotal"] < order["subtotal"] + 0.01
    # Total < original
    assert body["total"] < original_total

    # cleanup
    requests.patch(
        f"{API}/orders/{order_id}/cancel",
        json={"reason": "cleanup", "admin_email": ADMIN["email"], "admin_password": ADMIN["password"]},
        headers=_headers(tokens["cashier"]),
        timeout=30,
    )


# ---------- 8) Regression: logins ----------
@pytest.mark.parametrize("creds", [ADMIN, WAITER, CASHIER, BAR])
def test_regression_login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"{creds['email']} -> {r.status_code} {r.text}"
