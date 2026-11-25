"""Segurança da integração NostFood: o que sai do Gestor e o que entra.

Prova que:
- toda saída passa pela allowlist (rotas e campos fixos) e o resto é recusado;
- com NOSTFOOD_SEND_STATUS=false nenhum POST sai;
- o POST de status leva exatamente pedido_id e status;
- só o webhook aceita chamada sem login, e ele nunca devolve dado do Gestor.

Teste OFFLINE: rodar com cd backend && python -m pytest tests/test_nostfood_security.py
"""
import asyncio
import json
from datetime import date

import pytest

from _offline_app import call
import nostfood_integration as nf
from test_nostfood_integration import (  # noqa: F401  (env é fixture)
    N, T_ADMIN, WEBHOOK, env, post_raw, remote_order, sign_hex,
)


# ==================== saída: allowlist ====================
@pytest.fixture
def wire(monkeypatch):
    """Captura o que iria para a rede (nada sai de verdade)."""
    sent = []

    async def fake_http(method, url, params, body, headers):
        sent.append({"method": method, "url": url, "params": params, "body": body, "headers": headers})
        return {"success": True, "data": {"pedidos": [], "has_more": False}}

    monkeypatch.setattr(nf, "_http_send", fake_http)
    monkeypatch.setenv("NOSTFOOD_API_KEY", "chave-teste")
    monkeypatch.delenv("NOSTFOOD_BASE_URL", raising=False)
    return sent


def test_only_two_routes_are_allowed():
    assert set(nf.OUTBOUND_ALLOWLIST) == {("GET", "pedidos.php"), ("POST", "atualizar-pedido.php")}


def test_get_orders_sends_only_key_and_date_filters(wire):
    asyncio.run(nf.fetch_orders_for_days([date(2026, 11, 24)]))
    assert len(wire) == 1
    call_ = wire[0]
    assert call_["method"] == "GET" and call_["url"] == "https://nostfood.com/api/public/pedidos.php"
    assert call_["params"] == {"data_inicio": "2026-11-24", "data_fim": "2026-11-24", "limit": 1000, "offset": 0}
    assert call_["body"] is None and call_["headers"] == {"X-API-Key": "chave-teste"}


@pytest.mark.parametrize("method,route", [
    ("POST", "criar-produto.php"), ("POST", "criar-usuario.php"), ("POST", "criar-pedido.php"),
    ("GET", "produtos.php"), ("DELETE", "pedidos.php"), ("POST", "pedidos.php"), ("GET", "atualizar-pedido.php"),
    ("GET", "../pedidos.php"),
])
def test_route_outside_allowlist_is_refused_and_logged(wire, method, route, caplog):
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.nostfood_request(method, route, body={"status": "pronto", "pedido_id": 1}))
    assert wire == []
    assert "SAÍDA BLOQUEADA" in caplog.text


@pytest.mark.parametrize("params", [
    {"data_inicio": "2026-11-24", "cliente": "Maria"},
    {"data_inicio": "2026-11-24", "estoque": 10},
    {"data_inicio": "24/11/2026"},
    {"limit": "1000; DROP"},
    {"offset": -1},
])
def test_get_with_extra_or_bad_params_is_refused(wire, params):
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.nostfood_request("GET", "pedidos.php", params=params))
    assert wire == []


def test_get_never_sends_body(wire):
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.nostfood_request("GET", "pedidos.php", params={"limit": 1}, body={"status": "pronto"}))
    assert wire == []


@pytest.mark.parametrize("body", [
    {"pedido_id": 498, "status": "pronto", "total": 52.0},
    {"pedido_id": 498, "status": "pronto", "customer_name": "Maria"},
    {"pedido_id": 498, "status": "pronto", "items": [{"name": "Sansão"}]},
    {"pedido_id": 498, "status": "cancelado"},           # status que o Gestor nunca envia
    {"pedido_id": 498, "order_number": "PED-498", "status": "pronto"},  # dois identificadores
    {"status": "pronto"},                                 # sem identificador
    {"pedido_id": "498", "status": "pronto"},             # id precisa ser inteiro
    {"pedido_id": None, "status": "pronto"},
])
def test_post_with_extra_or_bad_fields_is_refused(wire, monkeypatch, body):
    monkeypatch.setenv("NOSTFOOD_SEND_STATUS", "true")
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.nostfood_request("POST", "atualizar-pedido.php", body=body))
    assert wire == []


def test_status_post_contains_exactly_pedido_id_and_status(wire, monkeypatch):
    monkeypatch.setenv("NOSTFOOD_SEND_STATUS", "true")
    asyncio.run(nf.send_status("498", "PED-498", "pronto"))
    assert len(wire) == 1
    assert wire[0]["method"] == "POST" and wire[0]["url"].endswith("/atualizar-pedido.php")
    assert wire[0]["body"] == {"pedido_id": 498, "status": "pronto"}
    assert wire[0]["params"] is None and wire[0]["headers"] == {"X-API-Key": "chave-teste"}


def test_status_post_without_numeric_id_uses_only_order_number(wire, monkeypatch):
    monkeypatch.setenv("NOSTFOOD_SEND_STATUS", "true")
    asyncio.run(nf.send_status(None, "99-5764", "em_preparo"))
    assert wire[0]["body"] == {"order_number": "99-5764", "status": "em_preparo"}


def test_status_post_without_any_id_is_refused(wire, monkeypatch):
    monkeypatch.setenv("NOSTFOOD_SEND_STATUS", "true")
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.send_status(None, None, "pronto"))
    assert wire == []


@pytest.mark.parametrize("value", ["false", "", "0", "nao"])
def test_send_status_off_no_post_leaves_even_calling_directly(wire, monkeypatch, value):
    monkeypatch.setenv("NOSTFOOD_SEND_STATUS", value)
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.send_status("498", "PED-498", "pronto"))
    assert wire == []


_REAL_SEND_STATUS = nf.send_status  # guardado antes da fixture env trocar por um falso


def test_send_status_off_kds_flow_sends_nothing(env, monkeypatch, wire):
    """Fluxo completo com SEND_STATUS=false: o KDS muda o status e nenhum POST sai."""
    from test_nostfood_integration import T_KITCHEN, link_all
    monkeypatch.setenv("NOSTFOOD_SEND_STATUS", "false")
    monkeypatch.setattr(nf, "send_status", _REAL_SEND_STATUS)
    link_all(env)
    asyncio.run(nf.upsert_from_snapshot(remote_order(), "teste"))
    order = next(o for o in env.db.orders.docs if o.get("external_source") == "nostfood")
    for item in order["items"]:
        for st in ("preparing", "ready"):
            call("PUT", f"/api/orders/{order['id']}/item/{item['id']}/status", token=T_KITCHEN, body={"status": st})
    env.run_scheduled()
    assert wire == []


def test_base_url_must_be_https(wire, monkeypatch):
    monkeypatch.setenv("NOSTFOOD_BASE_URL", "http://outro-servidor.exemplo/api")
    with pytest.raises(nf.OutboundBlocked):
        asyncio.run(nf.nostfood_request("GET", "pedidos.php", params={"limit": 1}))
    assert wire == []


def test_no_other_http_client_in_integration():
    """Só _http_send usa httpx: nenhuma saída contorna a allowlist."""
    import inspect
    src = inspect.getsource(nf)
    assert src.count("httpx.") == 1 and "requests." not in src and "urllib" not in src
    assert "httpx." in inspect.getsource(nf._http_send)


# ==================== entrada: rotas e perfis ====================
PROTECTED = [
    ("GET", "/status"), ("POST", "/simular"), ("DELETE", "/testes"),
    ("POST", "/pedidos/x/nao-recebido"), ("GET", "/produtos-sem-ligacao"), ("GET", "/ligacoes"),
    ("POST", "/ligar-produto"), ("POST", "/pedidos/x/observacao"), ("POST", "/pedidos/x/observacao/y/ciente"),
    ("GET", "/kds/cancelados"), ("POST", "/pedidos/x/cancelamento/ciente"), ("GET", "/perdas"),
]


def test_every_route_is_listed_here():
    """Rota nova na integração quebra este teste até entrar na lista (e na documentação)."""
    import server
    from fastapi.routing import APIRoute
    paths = {(m, r.path.replace("/api/integrations/nostfood", ""))
             for r in server.app.other_asgi_app.routes if isinstance(r, APIRoute)
             and r.path.startswith("/api/integrations/nostfood") for m in r.methods}
    listed = {(m, p.replace("/x/", "/{order_id}/").replace("/y/", "/{obs_id}/")) for m, p in PROTECTED}
    assert paths == listed | {("POST", "/webhook")}


@pytest.mark.parametrize("method,path", PROTECTED)
def test_without_login_is_refused_and_returns_no_data(env, method, path):
    status, body = call(method, N + path)
    assert status in (401, 403)  # sem token: 403 "Not authenticated" (padrão do FastAPI 0.110)
    assert set(body) == {"detail"}


@pytest.mark.parametrize("method,path", PROTECTED)
def test_invalid_token_is_401(env, method, path):
    status, body = call(method, N + path, token="token-invalido")
    assert status == 401 and set(body) == {"detail"}


@pytest.mark.parametrize("method,path", [(m, p) for m, p in PROTECTED if p not in
                                         ("/kds/cancelados", "/pedidos/x/observacao/y/ciente",
                                          "/pedidos/x/cancelamento/ciente", "/pedidos/x/observacao")])
def test_admin_only_routes_refuse_cashier_and_kitchen(env, method, path):
    from test_nostfood_integration import T_CASHIER, T_KITCHEN
    for token in (T_CASHIER, T_KITCHEN):
        assert call(method, N + path, token=token)[0] == 403


# ==================== entrada: webhook ====================
def _event(event_id="evt_sec", **data):
    return json.dumps({"event_id": event_id, "event_type": "order.created",
                       "resource": {"type": "order", "id": "498"}, "data": data or remote_order()}).encode()


def test_webhook_invalid_signature_is_401(env):
    body = _event()
    status, resp = post_raw(WEBHOOK, body, {"X-NostFood-Signature": "sha256=" + "0" * 64})
    assert status == 401 and set(resp) == {"detail"}
    status, resp = post_raw(WEBHOOK, body, {})
    assert status == 401 and set(resp) == {"detail"}
    assert env.db.orders.docs == [] or all(o.get("external_source") != "nostfood" for o in env.db.orders.docs)


def test_webhook_valid_signature_answers_only_ok(env):
    body = _event()
    status, resp = post_raw(WEBHOOK, body, {"X-NostFood-Signature": sign_hex(body)})
    assert status == 200 and resp == {"ok": True}
    # repetido: mesma resposta, sem campo extra
    status, resp = post_raw(WEBHOOK, body, {"X-NostFood-Signature": sign_hex(body)})
    assert status == 200 and resp == {"ok": True}


def test_webhook_body_limit(env):
    big = json.dumps({"event_id": "evt_big", "data": {"x": "a" * (nf.WEBHOOK_MAX_BODY_BYTES + 1)}}).encode()
    status, resp = post_raw(WEBHOOK, big, {"X-NostFood-Signature": sign_hex(big), "Content-Length": str(len(big))})
    assert status == 413 and set(resp) == {"detail"}
    # sem Content-Length também é barrado na leitura
    status, _ = post_raw(WEBHOOK, big, {"X-NostFood-Signature": sign_hex(big)})
    assert status == 413


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH"])
def test_webhook_only_accepts_post(env, method):
    status, _ = post_raw(WEBHOOK, b"", {}, method=method)
    assert status == 405


# ==================== kds/cancelados sem dados pessoais ====================
PERSONAL_FIELDS = {"customer_phone", "address", "customer_address", "latitude", "longitude",
                   "payment_method", "payment_status", "total", "subtotal", "delivery_fee",
                   "external_financials", "external_id", "external_platform_order_id", "observations",
                   "change_for", "troco", "customer_email"}


def _cancelled_order(env):
    from test_nostfood_integration import link_all, send_event
    link_all(env)
    send_event("order.created", remote_order(customer_name="Maria Aparecida da Silva", troco=50,
                                             change_for=50), event_id="c1")
    send_event("order.cancelled", {"order_number": "PED-498", "status": "cancelado",
                                   "motivo": "Cliente desistiu"}, event_id="c2")


def _token(role):
    from _offline_app import token_for
    uid = f"u-{role}"
    return uid, token_for(uid)


@pytest.mark.parametrize("role", ["kitchen", "bar", "waiter"])
def test_kds_cancelled_for_kitchen_bar_waiter_has_no_personal_data(env, role):
    uid, tok = _token(role)
    env.db.users.docs.append({"id": uid, "name": role, "email": f"{role}@x", "role": role, "is_active": True})
    _cancelled_order(env)
    status, rows = call("GET", f"{N}/kds/cancelados", token=tok)
    assert status == 200 and len(rows) == 1
    o = rows[0]
    assert set(o) <= set(nf.KDS_CANCELLED_ORDER_FIELDS) | {"customer_name", "items"}
    assert not (set(o) & PERSONAL_FIELDS)
    assert o["customer_name"] == "Maria"  # só o primeiro nome
    assert o["cancellation_reason"] == "Cliente desistiu" and o["cancelled_at"]
    assert o["external_order_number"] == "PED-498"
    assert [(i["product_name"], i["quantity"], i["type"]) for i in o["items"]] == [
        ("Sansão", 1, "food"), ("Coca-Cola Lata", 2, "drink")]
    for item in o["items"]:
        assert set(item) <= set(nf.KDS_CANCELLED_ITEM_FIELDS)
        assert "unit_price" not in item and "notes" not in item and "addons" not in item


@pytest.mark.parametrize("role", ["admin", "cashier"])
def test_kds_cancelled_for_admin_and_cashier_is_complete(env, role):
    from test_nostfood_integration import T_ADMIN, T_CASHIER
    _cancelled_order(env)
    status, rows = call("GET", f"{N}/kds/cancelados", token=T_ADMIN if role == "admin" else T_CASHIER)
    assert status == 200 and len(rows) == 1
    o = rows[0]
    assert o["customer_name"] == "Maria Aparecida da Silva" and o["customer_phone"] == "16999990000"
    assert "address" in o and "total" in o and "unit_price" in o["items"][0]


def test_first_name():
    assert nf.first_name("  Maria   Aparecida ") == "Maria"
    assert nf.first_name("") is None and nf.first_name(None) is None
