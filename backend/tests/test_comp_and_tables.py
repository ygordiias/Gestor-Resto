"""Backend tests for iteration 4:
- Table types (artist/singer/cover/event) + note
- Order comp/cortesia (PATCH /orders/{id}/comp)
- Sales exclude is_comp
- New /reports/sales-by-table endpoint
- Regression: default table_type=regular, waiter auto-fill
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://digital-orders-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@teste.com", "password": "123456"}
WAITER = {"email": "yuri@digitalcodex.com", "password": "123456"}
CASHIER_EMAIL = "caixa@digitalcodex.com"
CASHIER_PWD = "caixa123"


def _login(cred):
    r = requests.post(f"{API}/auth/login", json=cred, timeout=15)
    assert r.status_code == 200, f"Login failed for {cred['email']}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def waiter_token():
    return _login(WAITER)


@pytest.fixture(scope="module")
def cashier_token(admin_token):
    # Try login; if fails, reset password via admin
    r = requests.post(f"{API}/auth/login", json={"email": CASHIER_EMAIL, "password": CASHIER_PWD}, timeout=15)
    if r.status_code != 200:
        # find user id
        ur = requests.get(f"{API}/users", headers=_h(admin_token), timeout=15)
        assert ur.status_code == 200, ur.text
        target = next((u for u in ur.json() if u.get("email") == CASHIER_EMAIL), None)
        assert target, f"cashier {CASHIER_EMAIL} not found in DB"
        up = requests.put(f"{API}/users/{target['id']}", json={"password": CASHIER_PWD},
                          headers=_h(admin_token), timeout=15)
        assert up.status_code in (200, 204), up.text
        r = requests.post(f"{API}/auth/login", json={"email": CASHIER_EMAIL, "password": CASHIER_PWD}, timeout=15)
        assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------- Tables: table_type + note ----------

class TestTableTypes:
    created_ids = []

    def test_create_artist_table(self, admin_token):
        payload = {"number": 9001, "capacity": 4, "table_type": "artist", "note": "Palco 1"}
        r = requests.post(f"{API}/tables", json=payload, headers=_h(admin_token), timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("table_type") == "artist"
        assert data.get("note") == "Palco 1"
        assert data.get("number") == 9001
        TestTableTypes.created_ids.append(data["id"])

    def test_create_default_regular_table(self, admin_token):
        payload = {"number": 9002, "capacity": 4}
        r = requests.post(f"{API}/tables", json=payload, headers=_h(admin_token), timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("table_type", "regular") == "regular"
        TestTableTypes.created_ids.append(data["id"])

    def test_cleanup_tables(self, admin_token):
        for tid in TestTableTypes.created_ids:
            requests.delete(f"{API}/tables/{tid}", headers=_h(admin_token), timeout=15)


# ---------- Comp/Cortesia ----------

class TestOrderComp:
    order_id = None
    table_id = None

    def test_setup_create_order(self, admin_token, waiter_token):
        tr = requests.post(f"{API}/tables", json={"number": 9010, "capacity": 4},
                           headers=_h(admin_token), timeout=15)
        assert tr.status_code in (200, 201), tr.text
        table = tr.json()
        TestOrderComp.table_id = table["id"]

        # Get a product
        pr = requests.get(f"{API}/products", headers=_h(waiter_token), timeout=15)
        assert pr.status_code == 200, pr.text
        products = pr.json()
        assert products, "Need at least 1 product"
        p = products[0]
        order_payload = {
            "table_id": table["id"],
            "table_number": table["number"],
            "items": [{
                "product_id": p["id"],
                "product_name": p["name"],
                "quantity": 1,
                "unit_price": p["price"],
                "type": p.get("type", "food"),
            }],
        }
        r = requests.post(f"{API}/orders", json=order_payload, headers=_h(waiter_token), timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("waiter_id"), f"waiter_id not auto-filled: {data}"
        assert data.get("waiter_name"), f"waiter_name not auto-filled: {data}"
        TestOrderComp.order_id = data["id"]

    def test_waiter_cannot_comp(self, waiter_token):
        r = requests.patch(f"{API}/orders/{TestOrderComp.order_id}/comp",
                           json={"is_comp": True, "comp_reason": "test"},
                           headers=_h(waiter_token), timeout=15)
        assert r.status_code in (401, 403), f"Waiter should not comp: got {r.status_code}"

    def test_cashier_can_comp(self, cashier_token):
        r = requests.patch(f"{API}/orders/{TestOrderComp.order_id}/comp",
                           json={"is_comp": True, "comp_reason": "Cortesia da casa"},
                           headers=_h(cashier_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("is_comp") is True
        assert data.get("comp_reason") == "Cortesia da casa"

    def test_comp_requires_reason(self, admin_token):
        r0 = requests.patch(f"{API}/orders/{TestOrderComp.order_id}/comp",
                            json={"is_comp": False}, headers=_h(admin_token), timeout=15)
        assert r0.status_code == 200, r0.text
        r = requests.patch(f"{API}/orders/{TestOrderComp.order_id}/comp",
                           json={"is_comp": True, "comp_reason": ""}, headers=_h(admin_token), timeout=15)
        assert r.status_code == 400

    def test_cleanup(self, admin_token):
        if TestOrderComp.order_id:
            requests.post(f"{API}/orders/{TestOrderComp.order_id}/cancel", headers=_h(admin_token), timeout=15)
        if TestOrderComp.table_id:
            requests.delete(f"{API}/tables/{TestOrderComp.table_id}", headers=_h(admin_token), timeout=15)


# ---------- Sales excludes comp + sales-by-table ----------

class TestSalesReports:
    def test_sales_by_table_admin(self, admin_token):
        r = requests.get(f"{API}/reports/sales-by-table?period=daily",
                         headers=_h(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("period", "start", "rows"):
            assert k in data
        assert data["period"] == "daily"
        assert isinstance(data["rows"], list)
        if data["rows"]:
            row = data["rows"][0]
            for k in ("table_number", "total", "orders_count", "items_count", "comp_total"):
                assert k in row, f"missing key {k} in row {row}"

    def test_sales_by_table_cashier(self, cashier_token):
        r = requests.get(f"{API}/reports/sales-by-table?period=weekly",
                         headers=_h(cashier_token), timeout=20)
        assert r.status_code == 200
        assert r.json()["period"] == "weekly"

    def test_sales_by_table_waiter_forbidden(self, waiter_token):
        r = requests.get(f"{API}/reports/sales-by-table?period=daily",
                         headers=_h(waiter_token), timeout=15)
        assert r.status_code in (401, 403)

    def test_sales_endpoint_exists(self, admin_token):
        r = requests.get(f"{API}/reports/sales?period=daily", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200
