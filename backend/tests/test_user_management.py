"""Segurança (Etapa 1, item 6): contas desativadas, proteção de superadmin,
campos permitidos em PUT /users/{id} e DELETE que só desativa.

Teste OFFLINE (sem servidor e sem MongoDB). Senhas geradas na hora.
Rodar: cd backend && python -m pytest tests/test_user_management.py
"""
import copy
import secrets

import pytest

from _offline_app import call, server, token_for


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


def _project(doc, projection):
    doc = copy.deepcopy(doc)
    doc.pop("_id", None)
    if projection:
        for k, v in projection.items():
            if v == 0:
                doc.pop(k, None)
    return doc


class FakeUsers:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if _match(d, query):
                return _project(d, projection)
        return None

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    async def update_one(self, query, update):
        for d in self.docs:
            if _match(d, query):
                d.update(copy.deepcopy(update.get("$set", {})))
                for k in update.get("$unset", {}):
                    d.pop(k, None)
                return

    async def delete_one(self, query):  # não deve ser usado
        raise AssertionError("delete_one não deve ser chamado: usuários são desativados")


class FakeDB:
    def __init__(self, users):
        self.users = FakeUsers(users)


PWD = {r: secrets.token_urlsafe(12) for r in ("superadmin", "admin", "admin2", "waiter", "inactive")}


def _user(uid, role, active=True):
    return {"id": uid, "name": uid, "email": f"{uid}@example.invalid", "role": role,
            "is_active": active, "password": server.get_password_hash(PWD[uid])}


@pytest.fixture(scope="module")
def base_users():
    return [_user("superadmin", "superadmin"), _user("admin", "admin"), _user("admin2", "admin"),
            _user("waiter", "waiter"), _user("inactive", "waiter", active=False)]


@pytest.fixture
def db(monkeypatch, base_users):
    fake = FakeDB(copy.deepcopy(base_users))
    monkeypatch.setattr(server, "db", fake)
    return fake


def _doc(db, uid):
    return next(d for d in db.users.docs if d["id"] == uid)


T = {uid: token_for(uid) for uid in ("superadmin", "admin", "admin2", "waiter", "inactive")}


# ---------- is_active ----------
def test_inactive_token_is_refused(db):
    status, body = call("GET", "/api/auth/me", token=T["inactive"])
    assert status == 401 and body["detail"] == "Usuário desativado"


def test_active_token_works(db):
    assert call("GET", "/api/auth/me", token=T["waiter"])[0] == 200


def test_login_inactive_right_password_is_403(db):
    status, body = call("POST", "/api/auth/login", body={"email": "inactive@example.invalid", "password": PWD["inactive"]})
    assert status == 403 and "desativado" in body["detail"]


def test_login_inactive_wrong_password_is_401(db):
    status, _ = call("POST", "/api/auth/login", body={"email": "inactive@example.invalid", "password": "errada-123456"})
    assert status == 401


def test_login_active_ok(db):
    status, body = call("POST", "/api/auth/login", body={"email": "waiter@example.invalid", "password": PWD["waiter"]})
    assert status == 200 and body["access_token"]


def test_login_alias_inactive_right_password_is_403(db):
    # POST /api/login (sem /auth) também recusa conta desativada.
    status, body = call("POST", "/api/login", body={"email": "inactive@example.invalid", "password": PWD["inactive"]})
    assert status == 403 and "desativado" in body["detail"]


def test_login_alias_inactive_wrong_password_is_401(db):
    status, _ = call("POST", "/api/login", body={"email": "inactive@example.invalid", "password": "errada-123456"})
    assert status == 401


# ---------- superadmin protegido ----------
def test_admin_cannot_update_superadmin(db):
    assert call("PUT", "/api/users/superadmin", token=T["admin"], body={"name": "X"})[0] == 403
    assert _doc(db, "superadmin")["name"] == "superadmin"


def test_admin_cannot_deactivate_superadmin(db):
    assert call("DELETE", "/api/users/superadmin", token=T["admin"])[0] == 403
    assert _doc(db, "superadmin")["is_active"] is True


def test_superadmin_can_update_admin(db):
    assert call("PUT", "/api/users/admin", token=T["superadmin"], body={"name": "Novo Nome"})[0] == 200
    assert _doc(db, "admin")["name"] == "Novo Nome"


def test_admin_cannot_promote_to_superadmin(db):
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"role": "superadmin"})[0] == 403


# ---------- própria conta ----------
def test_cannot_deactivate_self_via_delete(db):
    assert call("DELETE", "/api/users/admin", token=T["admin"])[0] == 403


def test_cannot_deactivate_self_via_update(db):
    assert call("PUT", "/api/users/admin", token=T["admin"], body={"is_active": False})[0] == 403


def test_cannot_change_own_role(db):
    assert call("PUT", "/api/users/admin", token=T["admin"], body={"role": "waiter"})[0] == 403
    assert call("PUT", "/api/users/superadmin", token=T["superadmin"], body={"role": "admin"})[0] == 403


def test_resending_same_role_and_active_on_self_is_ok(db):
    # A tela de Usuários sempre reenvia role e is_active.
    body = {"name": "Eu Mesmo", "email": "admin@example.invalid", "role": "admin", "is_active": True}
    assert call("PUT", "/api/users/admin", token=T["admin"], body=body)[0] == 200


def test_can_change_own_name_and_password(db):
    new_pwd = secrets.token_urlsafe(12)
    assert call("PUT", "/api/users/admin", token=T["admin"], body={"name": "Outro", "password": new_pwd})[0] == 200
    assert server.verify_password(new_pwd, _doc(db, "admin")["password"])


# ---------- campos permitidos e validação ----------
@pytest.mark.parametrize("field", ["id", "created_at", "password_hash", "deactivated_at"])
def test_unknown_field_is_refused(db, field):
    status, body = call("PUT", "/api/users/waiter", token=T["admin"], body={field: "x"})
    assert status == 400 and field in body["detail"]


def test_empty_body_is_refused(db):
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={})[0] == 400


def test_invalid_role_is_refused(db):
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"role": "dono"})[0] == 400


@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_is_active_must_be_bool(db, value):
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"is_active": value})[0] == 400


def test_short_password_is_refused_on_update(db):
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"password": "1234567"})[0] == 400


def test_email_of_other_account_is_refused(db):
    status, _ = call("PUT", "/api/users/waiter", token=T["admin"], body={"email": "admin2@example.invalid"})
    assert status == 409


def test_own_email_unchanged_is_ok(db):
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"email": "waiter@example.invalid"})[0] == 200


def test_password_hashed_and_never_returned(db):
    new_pwd = secrets.token_urlsafe(12)
    status, body = call("PUT", "/api/users/waiter", token=T["admin"], body={"password": new_pwd})
    assert status == 200
    assert "password" not in body
    stored = _doc(db, "waiter")["password"]
    assert stored != new_pwd and server.verify_password(new_pwd, stored)


def test_unknown_user_is_404(db):
    assert call("PUT", "/api/users/nao-existe", token=T["admin"], body={"name": "X"})[0] == 404


# ---------- DELETE só desativa ----------
def test_delete_only_deactivates(db):
    status, body = call("DELETE", "/api/users/waiter", token=T["admin"])
    assert status == 200 and body["message"] == "Usuário desativado"
    doc = _doc(db, "waiter")
    assert doc["is_active"] is False
    assert doc["deactivated_by_id"] == "admin" and doc["deactivated_at"]
    assert call("GET", "/api/auth/me", token=T["waiter"])[0] == 401


def test_delete_is_idempotent(db):
    call("DELETE", "/api/users/waiter", token=T["admin"])  # preparação: 1ª desativação
    first = _doc(db, "waiter")["deactivated_at"]
    assert call("DELETE", "/api/users/waiter", token=T["admin"])[0] == 200
    assert _doc(db, "waiter")["deactivated_at"] == first


def test_reactivate_by_admin(db):
    call("DELETE", "/api/users/waiter", token=T["admin"])
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"is_active": True})[0] == 200
    assert call("GET", "/api/auth/me", token=T["waiter"])[0] == 200


def test_reactivate_removes_deactivation_marks(db):
    call("DELETE", "/api/users/waiter", token=T["admin"])
    assert "deactivated_at" in _doc(db, "waiter")
    status, body = call("PUT", "/api/users/waiter", token=T["admin"], body={"is_active": True})
    assert status == 200
    doc = _doc(db, "waiter")
    assert doc["is_active"] is True
    assert "deactivated_at" not in doc and "deactivated_by_id" not in doc
    assert "deactivated_at" not in body


def test_update_active_user_does_not_unset(db):
    _doc(db, "waiter")["deactivated_at"] = "marca-antiga"  # dado legado num usuário ativo
    assert call("PUT", "/api/users/waiter", token=T["admin"], body={"is_active": True})[0] == 200
    assert _doc(db, "waiter")["deactivated_at"] == "marca-antiga"


# ---------- POST /users: senha mínima ----------
def test_create_user_short_password_is_refused(db):
    body = {"name": "Novo", "email": "novo@example.invalid", "role": "waiter", "password": "1234567"}
    assert call("POST", "/api/users", token=T["admin"], body=body)[0] == 400
    assert not any(d["email"] == "novo@example.invalid" for d in db.users.docs)


def test_create_user_ok(db):
    body = {"name": "Novo", "email": "novo@example.invalid", "role": "waiter", "password": secrets.token_urlsafe(12)}
    status, resp = call("POST", "/api/users", token=T["admin"], body=body)
    assert status == 200 and "password" not in resp
