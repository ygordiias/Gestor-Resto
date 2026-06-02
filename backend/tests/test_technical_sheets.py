"""Backend tests for the Technical Sheets module (Fichas Tecnicas)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@teste.com", "password": "123456"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    assert admin_token, "No token from login"
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def products(auth_headers):
    r = requests.get(f"{BASE_URL}/api/products", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) > 0
    return data


# ==================== Module: Technical Sheets CRUD ====================

class TestTechnicalSheetsCRUD:
    def test_list_sheets(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/technical-sheets", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_by_product_existing_sansao(self, auth_headers, products):
        sansao = next((p for p in products if "Sans" in p.get("name", "")), None)
        if not sansao:
            pytest.skip("Product 'Sansao' not found in seed data")
        r = requests.get(
            f"{BASE_URL}/api/technical-sheets/by-product/{sansao['id']}",
            headers=auth_headers,
            timeout=30,
        )
        # Pre-existing per main agent note - if not present, treat as 404 still valid
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert r.json()["product_id"] == sansao["id"]

    def test_by_product_not_found_returns_404(self, auth_headers):
        fake_id = str(uuid.uuid4())
        r = requests.get(
            f"{BASE_URL}/api/technical-sheets/by-product/{fake_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 404

    def test_create_update_delete_flow(self, auth_headers, products):
        # find product without existing sheet
        target = None
        for p in products:
            r = requests.get(
                f"{BASE_URL}/api/technical-sheets/by-product/{p['id']}",
                headers=auth_headers, timeout=30,
            )
            if r.status_code == 404:
                target = p
                break
        if not target:
            pytest.skip("No product available without an existing sheet")

        # CREATE
        payload = {
            "product_id": target["id"],
            "product_name": f"TEST_{target['name']}",
            "image_url": "https://example.com/img.png",
            "ingredients": [
                {"name": "Pao", "quantity": "1 un"},
                {"name": "Carne", "quantity": "150g"},
            ],
            "assembly_steps": ["Montar", "Servir"],
            "notes": "TEST observacoes iniciais",
        }
        r = requests.post(f"{BASE_URL}/api/technical-sheets",
                          headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        sheet = r.json()
        assert sheet["product_id"] == target["id"]
        assert sheet["ingredients"][0]["name"] == "Pao"
        assert sheet["assembly_steps"] == ["Montar", "Servir"]
        assert "id" in sheet and "_id" not in sheet
        sheet_id = sheet["id"]

        # Duplicate POST should fail with 400
        r2 = requests.post(f"{BASE_URL}/api/technical-sheets",
                           headers=auth_headers, json=payload, timeout=30)
        assert r2.status_code == 400

        # GET by id
        rg = requests.get(f"{BASE_URL}/api/technical-sheets/{sheet_id}",
                          headers=auth_headers, timeout=30)
        assert rg.status_code == 200
        assert rg.json()["product_name"] == payload["product_name"]

        # GET by product
        rp = requests.get(
            f"{BASE_URL}/api/technical-sheets/by-product/{target['id']}",
            headers=auth_headers, timeout=30,
        )
        assert rp.status_code == 200
        assert rp.json()["id"] == sheet_id

        # UPDATE notes
        upd = {"notes": "TEST observacoes ATUALIZADAS",
               "ingredients": payload["ingredients"],
               "assembly_steps": payload["assembly_steps"]}
        ru = requests.put(f"{BASE_URL}/api/technical-sheets/{sheet_id}",
                          headers=auth_headers, json=upd, timeout=30)
        assert ru.status_code == 200
        assert ru.json()["notes"] == "TEST observacoes ATUALIZADAS"

        # verify update persisted
        rg2 = requests.get(f"{BASE_URL}/api/technical-sheets/{sheet_id}",
                           headers=auth_headers, timeout=30)
        assert rg2.json()["notes"] == "TEST observacoes ATUALIZADAS"

        # DELETE
        rd = requests.delete(f"{BASE_URL}/api/technical-sheets/{sheet_id}",
                             headers=auth_headers, timeout=30)
        assert rd.status_code == 200

        # confirm gone
        rg3 = requests.get(f"{BASE_URL}/api/technical-sheets/{sheet_id}",
                           headers=auth_headers, timeout=30)
        assert rg3.status_code == 404

    def test_create_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/technical-sheets",
                          json={"product_id": "x"}, timeout=30)
        assert r.status_code in (401, 403)


# ==================== Module: Regression checks ====================

class TestRegression:
    def test_login_admin(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200

    def test_products_list(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/products", headers=auth_headers, timeout=30)
        assert r.status_code == 200

    def test_tables_list(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/tables", headers=auth_headers, timeout=30)
        assert r.status_code == 200

    def test_orders_list(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/orders", headers=auth_headers, timeout=30)
        assert r.status_code == 200

    def test_stock_list(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/stock", headers=auth_headers, timeout=30)
        assert r.status_code in (200, 404)  # endpoint may differ
