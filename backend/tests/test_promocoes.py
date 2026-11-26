"""Promoção gerencial (promotions.py + rotas /promotions e lançamento de itens).

Teste OFFLINE (banco falso em memória, sem servidor e sem rede). O relógio do
restaurante é fixado com monkeypatch em promotions.now_local.
Rodar: cd backend && python -m pytest tests/test_promocoes.py
"""
from datetime import datetime

import pytest

import order_billing as billing
import promotions
from _fake_mongo import FakeDB, match
from _offline_app import call, server, token_for

ADMIN = {"id": "u-admin", "name": "Admin Bia", "email": "admin@x", "role": "admin", "is_active": True}
CAIXA = {"id": "u-caixa", "name": "Caixa Ana", "email": "caixa@x", "role": "cashier", "is_active": True}
GARCOM = {"id": "u-garcom", "name": "Garçom Leo", "email": "g@x", "role": "waiter", "is_active": True}

# Terça, 24/11/2026, 20h (horário do restaurante)
TERCA_20H = datetime(2026, 11, 24, 20, 0, tzinfo=promotions.LOCAL_TZ)

DRINKS_50 = {
    "name": "Drinks 50%", "discount_type": "percent", "discount_value": 50,
    "category_ids": ["c-drinks"], "product_ids": [],
    "start_date": "2026-11-01", "end_date": "2026-11-30",
    "weekdays": [2, 3, 4], "start_time": "19:00", "end_time": "21:00",
    "channels": ["salao", "balcao", "cardapio"],
}


@pytest.fixture
def clock(monkeypatch):
    state = {"now": TERCA_20H}
    monkeypatch.setattr(promotions, "now_local", lambda: state["now"])
    return state


@pytest.fixture
def db(monkeypatch, clock):
    fake = FakeDB()
    fake.users.docs += [dict(ADMIN), dict(CAIXA), dict(GARCOM)]
    fake.products.docs += [
        {"id": "p-caipi", "name": "Caipirinha", "price": 20.0, "category_id": "c-drinks", "type": "drink",
         "is_available": True},
        {"id": "p-burger", "name": "X-Burger", "price": 30.0, "category_id": "c-lanches", "type": "food",
         "is_available": True},
    ]
    fake.tables.docs.append({"id": "t-1", "number": 5, "status": "available"})

    async def noop(*a, **k):
        return None

    async def no_tables():
        return []

    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "validate_stock", noop)
    monkeypatch.setattr(server, "get_tables", no_tables)
    monkeypatch.setattr(server.sio, "emit", noop)
    return fake


def as_(user, method, path, body=None):
    return call(method, path, token=token_for(user["id"]), body=body)


def create_promo(body=None):
    status, promo = as_(ADMIN, "POST", "/api/promotions", body or DRINKS_50)
    assert status == 201, promo
    return promo


def launch(*items):
    body = {"table_id": "t-1", "table_number": 5, "items": [
        {"product_id": pid, "product_name": name, "quantity": q, "unit_price": price,
         "type": "drink" if pid == "p-caipi" else "food"} for pid, name, q, price in items]}
    status, order = as_(GARCOM, "POST", "/api/orders", body)
    assert status == 200, order
    return order


CAIPI = ("p-caipi", "Caipirinha", 1, 20.0)
BURGER = ("p-burger", "X-Burger", 1, 30.0)


def by_product(order, pid):
    return [i for i in order["items"] if i["product_id"] == pid]


# =====================================================================
# Lançamento
# =====================================================================
def test_drink_lancado_na_promocao_sai_com_50_e_lanche_nao(db):
    promo = create_promo()
    order = launch(CAIPI, BURGER)
    drink = by_product(order, "p-caipi")[0]
    assert drink["unit_price"] == 10.0 and drink["promo_original_price"] == 20.0 and drink["promo_price"] == 10.0
    assert drink["promo_name"] == "Drinks 50%" and drink["promo_id"] == promo["id"]
    burger = by_product(order, "p-burger")[0]
    assert burger["unit_price"] == 30.0 and "promo_id" not in burger
    # 10% sobre o cobrado, já com a promoção
    assert order["subtotal"] == 40.0 and order["service_fee"] == 4.0 and order["total"] == 44.0
    assert order["item_promo_total"] == 10.0 and order["item_discount_total"] == 0


@pytest.mark.parametrize("now", [
    datetime(2026, 11, 24, 21, 30, tzinfo=promotions.LOCAL_TZ),  # depois das 21h
    datetime(2026, 11, 24, 18, 59, tzinfo=promotions.LOCAL_TZ),  # antes das 19h
    datetime(2026, 11, 23, 20, 0, tzinfo=promotions.LOCAL_TZ),   # segunda
    datetime(2026, 12, 1, 20, 0, tzinfo=promotions.LOCAL_TZ),    # depois do fim (terça)
])
def test_fora_do_horario_dia_ou_periodo_nao_aplica(db, clock, now):
    create_promo()
    clock["now"] = now
    drink = by_product(launch(CAIPI), "p-caipi")[0]
    assert drink["unit_price"] == 20.0 and "promo_id" not in drink


def test_promocao_desligada_nao_aplica_nos_novos_e_mantem_nos_antigos(db):
    promo = create_promo()
    launch(CAIPI)
    status, off = as_(ADMIN, "PATCH", f"/api/promotions/{promo['id']}/active", {"is_active": False})
    assert status == 200 and off["status"] == "desligada"
    order = launch(CAIPI)  # mesma mesa: acrescenta na comanda aberta
    drinks = by_product(order, "p-caipi")
    assert [d["unit_price"] for d in drinks] == [10.0, 20.0]
    assert drinks[0]["promo_name"] == "Drinks 50%" and "promo_id" not in drinks[1]
    assert order["item_promo_total"] == 10.0 and order["total"] == 33.0
    # Nada é apagado: o histórico guarda criação e desligamento.
    saved = db.promotions.docs[0]
    assert [h["action"] for h in saved["history"]] == ["created", "deactivated"]


def test_promocao_que_acabou_depois_mantem_o_desconto_no_item(db, clock):
    create_promo()
    launch(CAIPI)
    clock["now"] = datetime(2026, 11, 24, 22, 0, tzinfo=promotions.LOCAL_TZ)
    order = launch(CAIPI)
    assert [d["unit_price"] for d in by_product(order, "p-caipi")] == [10.0, 20.0]


def test_pedido_da_nostfood_nunca_recebe_promocao(db):
    create_promo({**DRINKS_50, "channels": list(promotions.CHANNELS)})
    nostfood_order = {"source": "online", "external_source": "nostfood", "platform": "nostfood",
                      "origin": "nostfood", "delivery_type": "delivery"}
    assert promotions.order_channel(nostfood_order) is None
    for platform in ("ifood", "99food"):
        assert promotions.order_channel({"source": "online", "platform": platform}) is None
    # iFood/99 lançados à mão no caixa: preço da plataforma, sem promoção.
    status, order = as_(CAIXA, "POST", "/api/orders/online", {
        "platform": "ifood", "external_order_number": "123", "delivery_type": "delivery",
        "items": [{"product_id": "p-caipi", "product_name": "Caipirinha", "quantity": 1,
                   "unit_price": 20.0, "type": "drink"}]})
    assert status == 200 and order["items"][0]["unit_price"] == 20.0 and "promo_id" not in order["items"][0]


def test_balcao_e_cardapio_proprio_recebem_conforme_os_canais(db, monkeypatch):
    async def code():
        return "EM-0001"

    monkeypatch.setattr(server, "generate_order_code", code)
    create_promo({**DRINKS_50, "channels": ["balcao", "cardapio"]})
    status, order = as_(CAIXA, "POST", "/api/orders/online", {
        "platform": "other", "external_order_number": "B1", "delivery_type": "pickup",
        "items": [{"product_id": "p-caipi", "product_name": "Caipirinha", "quantity": 2,
                   "unit_price": 20.0, "type": "drink"}]})
    assert status == 200 and order["items"][0]["unit_price"] == 10.0 and order["total"] == 20.0
    status, body = call("POST", "/api/public/pedido", body={
        "customer_name": "Cliente", "customer_phone": "16999999999", "delivery_type": "retirada",
        "payment_method": "pix", "items": [{"product_id": "p-caipi", "name": "x", "price": 1, "quantity": 1}]})
    assert status == 200 and body["subtotal"] == 10.0
    # Salão não marcado: sem promoção.
    assert by_product(launch(CAIPI), "p-caipi")[0]["unit_price"] == 20.0


def test_vale_a_promocao_de_maior_desconto(db):
    create_promo()
    create_promo({**DRINKS_50, "name": "Caipirinha R$ 12 off", "discount_type": "value", "discount_value": 12,
                  "category_ids": [], "product_ids": ["p-caipi"]})
    drink = by_product(launch(CAIPI), "p-caipi")[0]
    assert drink["unit_price"] == 8.0 and drink["promo_name"] == "Caipirinha R$ 12 off"


def test_faixa_que_passa_da_meia_noite():
    promo = {**DRINKS_50, "id": "p", "is_active": True, "weekdays": [2], "start_time": "22:00", "end_time": "02:00"}
    assert promotions.applies_at(promo, datetime(2026, 11, 24, 23, 0, tzinfo=promotions.LOCAL_TZ))
    assert promotions.applies_at(promo, datetime(2026, 11, 25, 1, 0, tzinfo=promotions.LOCAL_TZ))  # ainda terça
    assert not promotions.applies_at(promo, datetime(2026, 11, 25, 23, 0, tzinfo=promotions.LOCAL_TZ))
    assert not promotions.applies_at(promo, datetime(2026, 11, 24, 3, 0, tzinfo=promotions.LOCAL_TZ))


# =====================================================================
# Desconto manual x promoção (não acumula)
# =====================================================================
def _drink_line(db):
    return next(i for i in db.orders.docs[0]["items"] if i["product_id"] == "p-caipi")


def test_desconto_menor_que_a_promocao_mostra_aviso_e_vale_a_promocao(db):
    create_promo()
    launch(CAIPI)
    order_id = db.orders.docs[0]["id"]
    status, body = as_(CAIXA, "PATCH", f"/api/orders/{order_id}/item/{_drink_line(db)['id']}/discount",
                       {"type": "percent", "value": 10, "reason": "cliente fiel"})
    assert status == 409 and "não acumula" in body["detail"] and "Vale a promoção" in body["detail"]
    assert _drink_line(db)["unit_price"] == 10.0


def test_desconto_maior_substitui_a_promocao_e_tirar_volta_a_promocao(db):
    create_promo()
    launch(CAIPI)
    order_id = db.orders.docs[0]["id"]
    item_id = _drink_line(db)["id"]
    status, body = as_(ADMIN, "PATCH", f"/api/orders/{order_id}/item/{item_id}/discount",
                       {"type": "percent", "value": 60, "reason": "reclamação"})
    assert status == 200, body
    assert "não acumula" in body["warning"]
    assert _drink_line(db)["unit_price"] == 8.0
    assert body["item_promo_total"] == 0 and body["item_discount_total"] == 12.0
    status, body = as_(CAIXA, "DELETE", f"/api/orders/{order_id}/item/{item_id}/discount")
    assert status == 200
    assert _drink_line(db)["unit_price"] == 10.0 and body["item_promo_total"] == 10.0
    assert body["item_discount_total"] == 0


def test_cortesia_em_item_da_promocao(db):
    create_promo()
    launch(CAIPI)
    order_id = db.orders.docs[0]["id"]
    item_id = _drink_line(db)["id"]
    status, body = as_(CAIXA, "PATCH", f"/api/orders/{order_id}/item/{item_id}/courtesy",
                       {"is_courtesy": True, "reason": "aniversário"})
    assert status == 200
    assert body["item_courtesy_total"] == 10.0 and body["item_promo_total"] == 10.0 and body["total"] == 0
    status, body = as_(CAIXA, "PATCH", f"/api/orders/{order_id}/item/{item_id}/courtesy", {"is_courtesy": False})
    assert _drink_line(db)["unit_price"] == 10.0 and body["total"] == 11.0  # volta ao preço da promoção


# =====================================================================
# Cadastro: só admin, validação, status
# =====================================================================
@pytest.mark.parametrize("user", [CAIXA, GARCOM])
def test_so_admin_cria_edita_ou_desliga(db, user):
    promo = create_promo()
    assert as_(user, "POST", "/api/promotions", DRINKS_50)[0] == 403
    assert as_(user, "PUT", f"/api/promotions/{promo['id']}", DRINKS_50)[0] == 403
    assert as_(user, "PATCH", f"/api/promotions/{promo['id']}/active", {"is_active": False})[0] == 403
    assert as_(user, "GET", "/api/promotions")[0] == 403
    status, active = as_(user, "GET", "/api/promotions/active?channel=salao")
    assert status == 200


@pytest.mark.parametrize("change,message", [
    ({"name": ""}, "nome"),
    ({"discount_value": 100}, "100%"),
    ({"discount_value": 0}, "maior que zero"),
    ({"category_ids": [], "product_ids": []}, "categoria ou um produto"),
    ({"end_date": "2026-10-01"}, "antes da data de início"),
    ({"start_time": "19:00", "end_time": None}, "horário"),
    ({"channels": ["ifood"]}, "canais"),
    ({"channels": []}, "canais"),
    ({"weekdays": [0]}, "Dias da semana"),
])
def test_validacao(db, change, message):
    status, body = as_(ADMIN, "POST", "/api/promotions", {**DRINKS_50, **change})
    assert status == 400 and message in body["detail"]


def test_editar_guarda_historico_e_nao_muda_item_lancado(db):
    promo = create_promo()
    launch(CAIPI)
    status, edited = as_(ADMIN, "PUT", f"/api/promotions/{promo['id']}", {**DRINKS_50, "discount_value": 30})
    assert status == 200 and edited["discount_value"] == 30
    history = db.promotions.docs[0]["history"]
    assert history[-1]["action"] == "edited" and history[-1]["fields"] == ["discount_value"]
    assert history[-1]["before"] == {"discount_value": 50.0}
    order = launch(CAIPI)
    assert [d["unit_price"] for d in by_product(order, "p-caipi")] == [10.0, 14.0]


def test_status_ativa_agendada_encerrada_desligada(db):
    create_promo()
    create_promo({**DRINKS_50, "name": "Natal", "start_date": "2026-12-20", "end_date": "2026-12-25"})
    create_promo({**DRINKS_50, "name": "Outubro", "start_date": "2026-10-01", "end_date": "2026-10-31"})
    off = create_promo({**DRINKS_50, "name": "Desligada"})
    as_(ADMIN, "PATCH", f"/api/promotions/{off['id']}/active", {"is_active": False})
    status, rows = as_(ADMIN, "GET", "/api/promotions")
    assert status == 200
    assert {r["name"]: r["status"] for r in rows} == {
        "Drinks 50%": "ativa", "Natal": "agendada", "Outubro": "encerrada", "Desligada": "desligada"}
    assert next(r for r in rows if r["name"] == "Drinks 50%")["applies_now"] is True


# =====================================================================
# Relatórios
# =====================================================================
def test_relatorio_por_promocao_e_por_periodo(db):
    create_promo()
    order = launch(CAIPI, CAIPI, BURGER)  # 2 caipirinhas na promoção
    stored = db.orders.docs[0]
    stored["items"][2]["discount_original_price"] = 30.0  # desconto manual de R$ 3 no lanche
    stored["items"][2]["unit_price"] = 27.0
    stored.update({"is_closed": True, "status": "delivered", "closed_at": "2026-11-24T23:00:00+00:00"})
    stored.update(billing.totals(stored))
    # Outro dia, fora do período pedido
    db.orders.docs.append({**stored, "id": "o-velho", "closed_at": "2026-11-20T23:00:00+00:00"})

    status, report = as_(ADMIN, "GET", "/api/reports/promotions?start=2026-11-24&end=2026-11-24")
    assert status == 200, report
    assert report["by_promotion"] == [{"promo_id": order["items"][0]["promo_id"], "name": "Drinks 50%",
                                       "units": 2, "amount": 20.0, "orders": 1}]
    assert report["totals"] == {"promo": 20.0, "discount": 3.0, "courtesy": 0}
    assert report["by_day"] == [{"date": "2026-11-24", "promo": 20.0, "discount": 3.0, "courtesy": 0}]

    status, report = as_(ADMIN, "GET", "/api/reports/promotions?start=2026-11-01&end=2026-11-30")
    assert report["totals"]["promo"] == 40.0 and len(report["by_day"]) == 2


def test_relatorio_de_vendas_soma_promocao_separada(monkeypatch, db):
    pipelines = []

    class Agg:
        def __init__(self, p):
            pipelines.append(p)

        async def to_list(self, n):
            return []

    monkeypatch.setattr(db.orders, "aggregate", lambda p: Agg(p), raising=False)
    status, body = as_(ADMIN, "GET", "/api/reports/sales")
    assert status == 200
    group = pipelines[0][1]["$group"]
    for key in ("item_discount_total", "item_courtesy_total", "item_promo_total"):
        assert key in group and body["summary"][key] == 0
    assert match({"is_closed": True, "closed_at": "2999-01-01", "status": "delivered"}, pipelines[0][0]["$match"])
