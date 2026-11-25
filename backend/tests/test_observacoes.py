"""Observação nova para o KDS em QUALQUER pedido (não só NostFood).

- Observação de item de cozinha chega só na cozinha (e churrasqueira); de bebida, só no bar.
- Pedido inteiro: todas as telas que têm itens do pedido.
- O "Ciente" de uma tela não apaga o aviso da outra.
- Quem pode: admin, caixa e garçom lançam; cozinha e bar confirmam.
- Eventos sem dados pessoais para cozinha, bar e garçom.

Teste OFFLINE. Rodar: cd backend && python -m pytest tests/test_observacoes.py
"""
import pytest

from _offline_app import call, server, token_for
from test_nostfood_integration import (  # noqa: F401  (env é fixture)
    N, T_ADMIN, T_CASHIER, T_KITCHEN, env, link_all, orders, remote_order, send_event,
)

BAR = {"id": "u-bar", "name": "Barman", "email": "b@x", "role": "bar", "is_active": True}
WAITER = {"id": "u-garcom", "name": "Garçom Zé", "email": "g@x", "role": "waiter", "is_active": True}
T_BAR, T_WAITER = token_for(BAR["id"]), token_for(WAITER["id"])
PHONE, ADDRESS = "16988887777", "Rua das Flores, 123"
PII_KEYS = {"customer_phone", "address", "change_for", "customer_address", "latitude", "longitude"}
KDS_ROOMS = {"role:kitchen", "role:bar", "role:waiter"}


@pytest.fixture
def salon(env, monkeypatch):
    env.db.users.docs += [dict(BAR), dict(WAITER)]
    env.db.orders.docs.append({
        "id": "o-mesa", "table_id": "mesa-5", "table_number": 5, "tab_number": 210, "source": "salon",
        "is_closed": False, "status": "pending", "created_at": "2026-11-25T12:00:00+00:00",
        "customer_name": "Joana Prado Lima", "customer_phone": PHONE, "address": ADDRESS,
        "items": [
            {"id": "i-sansao", "product_name": "Sansão", "type": "food", "quantity": 1, "status": "preparing"},
            {"id": "i-coca", "product_name": "Coca-Cola Lata", "type": "drink", "quantity": 2, "status": "pending"},
            {"id": "i-velho", "product_name": "Suco", "type": "drink", "quantity": 1, "status": "delivered"},
        ],
    })
    sent = []

    async def fake_emit(event, data=None, room=None, **kw):
        sent.append((event, data, {room} if isinstance(room, str) else set(room or [])))
        env.emitted.append((event, data))
    monkeypatch.setattr(server.sio, "emit", fake_emit)
    env.sent_rooms = sent
    return env


def _order(env, oid="o-mesa"):
    return next(o for o in env.db.orders.docs if o["id"] == oid)


def _add(token, text, item_id=None, oid="o-mesa"):
    body = {"text": text}
    if item_id:
        body["item_id"] = item_id
    return call("POST", f"/api/orders/{oid}/observacao", token=token, body=body)


def _ack(token, obs_id, station, oid="o-mesa"):
    return call("POST", f"/api/orders/{oid}/observacao/{obs_id}/ciente", token=token, body={"station": station})


def test_observacao_de_item_de_cozinha_chega_so_na_cozinha(salon):
    status, obs = _add(T_WAITER, "tirar picles do Sansão", item_id="i-sansao")
    assert status == 200
    assert obs["stations"] == ["kitchen", "grill"]
    assert obs["item_id"] == "i-sansao" and obs["item_name"] == "Sansão"
    assert obs["author_name"] == "Garçom Zé" and obs["created_at"] and obs["acks"] == {}
    assert _order(salon)["observations"] == [obs]
    # O bar não tem o que confirmar nesta observação.
    assert _ack(T_BAR, obs["id"], "bar")[0] == 400


def test_observacao_de_bebida_chega_so_no_bar(salon):
    status, obs = _add(T_CASHIER, "Coca sem gelo", item_id="i-coca")
    assert status == 200 and obs["stations"] == ["bar"]
    assert _ack(T_KITCHEN, obs["id"], "kitchen")[0] == 400
    status, acked = _ack(T_BAR, obs["id"], "bar")
    assert status == 200 and acked["acks"]["bar"]["by_name"] == "Barman" and acked["acks"]["bar"]["at"]


def test_ciente_de_uma_tela_nao_apaga_o_aviso_da_outra(salon):
    status, obs = _add(T_ADMIN, "Mesa com alergia a amendoim")  # pedido inteiro
    assert status == 200 and obs["item_id"] is None
    assert obs["stations"] == ["kitchen", "bar", "grill"]
    _ack(T_KITCHEN, obs["id"], "kitchen")
    saved = _order(salon)["observations"][0]
    assert saved["acks"]["kitchen"]["by_name"] == "Cozinheiro"
    assert "bar" not in saved["acks"] and "grill" not in saved["acks"]
    _ack(T_BAR, obs["id"], "bar")
    saved = _order(salon)["observations"][0]
    assert set(saved["acks"]) == {"kitchen", "bar"}
    assert saved["acks"]["kitchen"]["by_name"] == "Cozinheiro"


def test_pedido_so_com_bebida_nao_avisa_a_cozinha(salon):
    _order(salon)["items"] = [i for i in _order(salon)["items"] if i["type"] == "drink"]
    _, obs = _add(T_CASHIER, "Trazer canudo")
    assert obs["stations"] == ["bar"]


@pytest.mark.parametrize("token,expected", [
    ("admin", 200), ("cashier", 200), ("waiter", 200), ("kitchen", 403), ("bar", 403), (None, 403),
])
def test_quem_pode_lancar(salon, token, expected):
    tokens = {"admin": T_ADMIN, "cashier": T_CASHIER, "waiter": T_WAITER, "kitchen": T_KITCHEN, "bar": T_BAR}
    status, _ = _add(tokens.get(token), "x", item_id="i-sansao")
    assert status == expected


def test_quem_pode_confirmar(salon):
    _, obs = _add(T_CASHIER, "x")
    assert _ack(T_CASHIER, obs["id"], "kitchen")[0] == 403
    assert _ack(T_WAITER, obs["id"], "kitchen")[0] == 403
    assert _ack(T_KITCHEN, obs["id"], "sala")[0] == 400
    assert _ack(T_KITCHEN, "nao-existe", "kitchen")[0] == 404


@pytest.mark.parametrize("body,detail", [
    ({"text": "  "}, "Escreva"),
    ({"text": "x" * 501}, "muito longa"),
    ({"text": "x", "item_id": "nao-existe"}, "não encontrado"),
    ({"text": "x", "item_id": "i-velho"}, "já entregue"),
])
def test_validacoes(salon, body, detail):
    status, resp = call("POST", "/api/orders/o-mesa/observacao", token=T_CASHIER, body=body)
    assert status == 400 and detail in resp["detail"]


def test_pedido_fechado_ou_cancelado_recusa(salon):
    _order(salon)["is_closed"] = True
    assert _add(T_CASHIER, "x")[0] == 400
    assert call("POST", "/api/orders/nao-existe/observacao", token=T_CASHIER, body={"text": "x"})[0] == 404


def test_eventos_sem_dados_pessoais_para_cozinha_bar_e_garcom(salon):
    _, obs = _add(T_WAITER, "tirar picles", item_id="i-sansao")
    _ack(T_KITCHEN, obs["id"], "kitchen")
    events = {e for e, _, _ in salon.sent_rooms}
    assert {"order_observation", "kitchen_update"} <= events
    for event, data, to in salon.sent_rooms:
        assert to, f"{event} sem sala"
        if to & KDS_ROOMS:
            text = repr(data)
            assert PHONE not in text and ADDRESS not in text and "Joana Prado Lima" not in text
            if isinstance(data, list):
                assert all(not (PII_KEYS & set(o)) for o in data)
            elif isinstance(data, dict):
                assert not (PII_KEYS & set(data))
    (payload,) = [d for e, d, _ in salon.sent_rooms if e == "order_observation"]
    assert payload == {"order_id": "o-mesa", "observation": obs}


def test_rotas_antigas_da_nostfood_continuam(salon):
    link_all(salon)
    send_event("order.created", remote_order(), event_id="e1")
    oid = orders(salon)[0]["id"]
    status, obs = call("POST", f"{N}/pedidos/{oid}/observacao", token=T_CASHIER, body={"text": "Sem cebola!"})
    assert status == 200 and obs["stations"] == ["kitchen", "bar", "grill"]
    # Garçom não tinha acesso à rota antiga e continua sem.
    assert call("POST", f"{N}/pedidos/{oid}/observacao", token=T_WAITER, body={"text": "x"})[0] == 403
    status, acked = call("POST", f"{N}/pedidos/{oid}/observacao/{obs['id']}/ciente", token=T_KITCHEN,
                         body={"station": "kitchen"})
    assert status == 200 and acked["acks"]["kitchen"]["by_name"] == "Cozinheiro"
    # A rota geral vale para o mesmo pedido.
    assert _ack(T_BAR, obs["id"], "bar", oid=oid)[0] == 200


def test_observacao_antiga_sem_telas_aceita_qualquer_tela(salon):
    _order(salon)["observations"] = [{"id": "velha", "text": "x", "acks": {}}]
    assert _ack(T_BAR, "velha", "bar")[0] == 200
