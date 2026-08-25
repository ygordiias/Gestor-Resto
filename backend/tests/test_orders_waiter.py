"""Tests for waiter auto-assignment, item notes, and service fee on POST /api/orders."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://digital-orders-3.preview.emergentagent.com').rstrip('/')

WAITER_EMAIL = "yuri@digitalcodex.com"
WAITER_PASS = "123456"
ADMIN_EMAIL = "admin@teste.com"
ADMIN_PASS = "123456"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def waiter_token():
    return _login(WAITER_EMAIL, WAITER_PASS)["access_token"]


@pytest.fixture(scope="module")
def waiter_user():
    return _login(WAITER_EMAIL, WAITER_PASS)["user"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)["access_token"]


@pytest.fixture(scope="module")
def test_table(admin_token):
    """Create a fresh test table for orders (avoids conflicts with occupied tables)."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Find an unused table number
    tables = requests.get(f"{BASE_URL}/api/tables", timeout=15).json()
    existing_numbers = {t["number"] for t in tables}
    number = 999
    while number in existing_numbers:
        number -= 1
    r = requests.post(f"{BASE_URL}/api/tables",
                     json={"number": number, "capacity": 4, "status": "available"},
                     headers=headers, timeout=15)
    assert r.status_code == 200, f"Create table failed: {r.text}"
    tbl = r.json()
    yield tbl
    # Cleanup: cancel any open order on this table then delete
    try:
        o = requests.get(f"{BASE_URL}/api/orders/table/{tbl['id']}", timeout=15).json()
        if o and o.get("id"):
            requests.post(f"{BASE_URL}/api/orders/{o['id']}/cancel", timeout=15)
    except Exception:
        pass
    requests.delete(f"{BASE_URL}/api/tables/{tbl['id']}", headers=headers, timeout=15)


def test_auth_me_waiter_role(waiter_token):
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {waiter_token}"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "waiter", f"Expected role=waiter, got {data.get('role')}"
    assert data["email"] == WAITER_EMAIL


def test_create_order_auto_waiter_and_notes_and_service_fee(waiter_token, waiter_user, test_table):
    """POST /orders as waiter without waiter_id/name -> resp has waiter_id/name from token,
    items[].notes preserved, service_fee=10% of subtotal."""
    headers = {"Authorization": f"Bearer {waiter_token}"}
    payload = {
        "table_id": test_table["id"],
        "table_number": test_table["number"],
        "items": [
            {
                "product_id": "test-prod-1",
                "product_name": "Item Teste 52.90",
                "quantity": 1,
                "unit_price": 52.90,
                "type": "food",
                "notes": "Sem cebola",
            }
        ],
        # intentionally NOT sending waiter_id / waiter_name
    }
    r = requests.post(f"{BASE_URL}/api/orders", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200, f"POST /orders failed: {r.status_code} {r.text}"
    order = r.json()

    # Waiter auto-assigned from token
    assert order.get("waiter_id") == waiter_user["id"], f"waiter_id mismatch: {order.get('waiter_id')} vs {waiter_user['id']}"
    assert order.get("waiter_name"), "waiter_name missing"
    assert order["waiter_name"].strip().lower().startswith("yuri"), f"waiter_name should be Yuri-ish, got {order['waiter_name']!r}"

    # Item notes preserved
    assert len(order["items"]) >= 1
    # find item we just added
    added = [i for i in order["items"] if i["product_id"] == "test-prod-1"]
    assert added, "Item not found in order response"
    assert added[0].get("notes") == "Sem cebola", f"notes not preserved: {added[0].get('notes')!r}"

    # Service fee = 10% of subtotal (subtotal computed on ALL items in order)
    subtotal = order["subtotal"]
    assert order["service_fee"] == pytest.approx(subtotal * 0.10, abs=0.01)
    assert order["total"] == pytest.approx(subtotal + order["service_fee"], abs=0.01)

    # If this was the first order (single item @ 52.90) => fee=5.29 total=58.19
    if abs(subtotal - 52.90) < 0.001:
        assert order["service_fee"] == pytest.approx(5.29, abs=0.01)
        assert order["total"] == pytest.approx(58.19, abs=0.01)

    # GET /orders/{id} returns waiter_name and items[].notes
    order_id = order["id"]
    r2 = requests.get(f"{BASE_URL}/api/orders/{order_id}", timeout=15)
    assert r2.status_code == 200
    fetched = r2.json()
    assert fetched.get("waiter_name")
    assert any(i.get("notes") == "Sem cebola" for i in fetched["items"])


def test_regression_admin_login():
    """Regression: admin login continues working."""
    data = _login(ADMIN_EMAIL, ADMIN_PASS)
    assert data["user"]["role"] in ("admin", "superadmin")
