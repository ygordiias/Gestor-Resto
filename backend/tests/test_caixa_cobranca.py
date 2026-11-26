"""Caixa: pagamento parcial, desconto por item, cortesia por quantidade e totais.

Teste OFFLINE (banco falso em memória, sem servidor e sem rede). A transação é
simulada sem rollback (o rollback do fechamento já é coberto em test_close_order.py).
Rodar: cd backend && python -m pytest tests/test_caixa_cobranca.py
"""
import copy

import pytest

import order_billing as billing
from _fake_mongo import FakeDB
from _offline_app import call, server, token_for

CAIXA = {"id": "u-caixa", "name": "Caixa Ana", "email": "caixa@x", "role": "cashier", "is_active": True}
ADMIN_PASSWORD = "senha-do-admin-123"
ADMIN = {"id": "u-admin", "name": "Admin Bia", "email": "admin@x", "role": "admin", "is_active": True}
GARCOM = {"id": "u-garcom", "name": "Garçom", "email": "g@x", "role": "waiter", "is_active": True}


def item(iid, product_id, name, qty, price, kind="food"):
    return {"id": iid, "product_id": product_id, "product_name": name, "quantity": qty,
            "unit_price": price, "type": kind, "status": "pending", "is_courtesy": False}


def salon_order(oid="o-1", tab=210, items=None):
    order = {"id": oid, "table_id": "t-1", "table_number": 5, "tab_number": tab, "status": "pending",
             "service_fee_percentage": 10, "is_closed": False, "is_comp": False,
             "created_at": "2026-11-26T20:00:00+00:00",
             "items": items if items is not None else [
                 item("i-burger", "p-burger", "X-Burger", 3, 30.0),
                 item("i-chopp", "p-chopp", "Chopp", 2, 12.0, "drink")]}
    order.update(billing.totals(order))
    return order


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def start_transaction(self):
        return self


class _Client:
    async def start_session(self):
        return _Session()


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.users.docs += [dict(CAIXA), dict(GARCOM),
                        {**ADMIN, "password": server.get_password_hash(ADMIN_PASSWORD)}]
    fake.products.docs += [{"id": "p-burger", "name": "X-Burger", "price": 30.0, "category_id": "c-lanches"},
                           {"id": "p-chopp", "name": "Chopp", "price": 12.0, "category_id": "c-drinks"}]
    fake.cash_registers.docs.append({"id": "reg-1", "is_open": True, "total_sales": 0.0, "initial_amount": 100.0,
                                     "deposits": 0, "withdrawals": 0, "opened_at": "2026-11-26T00:00:00+00:00"})
    fake.orders.docs.append(salon_order())
    deducted = []

    async def fake_deduct(product_id, quantity, order_code=""):
        deducted.append((product_id, quantity))

    async def noop(*a, **k):
        return None

    async def no_tables():
        return []

    monkeypatch.setattr(server, "db", fake)
    monkeypatch.setattr(server, "client", _Client())
    monkeypatch.setattr(server, "deduct_stock", fake_deduct)
    monkeypatch.setattr(server, "release_physical_tab", noop)
    monkeypatch.setattr(server, "refresh_table_after_order", noop)
    monkeypatch.setattr(server, "get_tables", no_tables)
    monkeypatch.setattr(server.sio, "emit", noop)
    fake.deducted = deducted
    return fake


def caixa(method, path, body=None):
    return call(method, path, token=token_for(CAIXA["id"]), body=body)


def admin(method, path, body=None):
    return call(method, path, token=token_for(ADMIN["id"]), body=body)


def order(db, oid="o-1"):
    return next(o for o in db.orders.docs if o["id"] == oid)


def line(db, iid, oid="o-1"):
    return next(i for i in order(db, oid)["items"] if i["id"] == iid)


def total_sales(db):
    return round(db.cash_registers.docs[0]["total_sales"], 2)


ADMIN_CREDS = {"admin_email": "admin@x", "admin_password": ADMIN_PASSWORD}


# =====================================================================
# Totais (funções puras)
# =====================================================================
def test_totais_10_por_cento_so_no_salao_sobre_o_cobrado():
    o = salon_order()
    assert billing.totals(o)["subtotal"] == 114.0
    assert billing.totals(o)["service_fee"] == 11.4
    assert billing.totals(o)["total"] == 125.4


@pytest.mark.parametrize("extra", [{"delivery_type": "delivery"}, {"source": "online", "origin": "web"},
                                   {"external_source": "nostfood", "source": "online"}])
def test_delivery_online_e_nostfood_sem_10(extra):
    o = {**salon_order(), **extra}
    t = billing.totals(o)
    assert t["service_fee"] == 0 and t["service_fee_percentage"] == 0 and t["total"] == 114.0


def test_cancelado_nao_soma():
    o = salon_order()
    o["items"].append({**item("i-x", "p-burger", "X-Burger", 2, 30.0), "status": "cancelled"})
    assert billing.totals(o)["subtotal"] == 114.0


def test_arredondamento_dos_10_por_cento():
    o = salon_order(items=[item("i-1", "p", "Água", 1, 4.55)])
    t = billing.totals(o)
    assert t["service_fee"] == 0.46 and t["total"] == 5.01  # 0,455 arredonda para cima


# =====================================================================
# A) Pagamento parcial
# =====================================================================
def test_pagar_parte_pagar_o_resto_e_fechar(db):
    status, body = caixa("POST", "/api/orders/o-1/partial-payments",
                         {"amount": 50.0, "payments": [{"method": "pix", "amount": 50.0}]})
    assert status == 200, body
    assert body["remaining"] == 75.4
    o = order(db)
    assert o["is_closed"] is False and o["paid_amount"] == 50.0
    entry = o["partial_payments"][0]
    assert entry["amount"] == 50.0 and entry["created_by_name"] == "Caixa Ana" and entry["created_at"]
    assert entry["payments"] == [{"method": "pix", "amount": 50.0}]
    pay = db.payments.docs[0]
    assert pay["kind"] == "partial" and pay["method"] == "pix" and pay["amount"] == 50.0
    assert pay["register_id"] == "reg-1" and pay["created_by_id"] == "u-caixa" and pay["created_at"]
    assert total_sales(db) == 50.0  # entra no caixa na hora

    # Fechar cobra só o que falta: R$ 75,40 (dinheiro 80, troco 4,60).
    status, body = caixa("POST", "/api/orders/o-1/close", {"payments": [{"method": "pix", "amount": 50.0}]})
    assert status == 422 and "faltam R$ 25,40" in body["detail"]
    status, _ = caixa("POST", "/api/orders/o-1/close", {"payments": [{"method": "cash", "amount": 80.0}]})
    assert status == 200
    assert order(db)["is_closed"] is True
    assert total_sales(db) == 125.4
    assert sorted((p["kind"], p["amount"]) for p in db.payments.docs) == [("final", 80.0), ("partial", 50.0)]
    assert sorted(db.deducted) == [("p-burger", 3), ("p-chopp", 2)]

    # A prévia do caixa concilia parcial + final sem aviso.
    status, report = caixa("GET", "/api/cash-register/preview")
    assert status == 200, report
    assert report["warnings"] == [] and report["closed_orders"] == 1
    assert report["total_sales"] == 125.4
    assert report["payment_methods"]["pix"] == 50.0 and report["payment_methods"]["cash"] == 75.4
    assert report["total_change"] == 4.6


def test_parcial_em_varias_formas_com_troco_no_dinheiro(db):
    status, body = caixa("POST", "/api/orders/o-1/partial-payments", {
        "amount": 40.0, "payments": [{"method": "debit", "amount": 20.0}, {"method": "cash", "amount": 50.0}]})
    assert status == 200, body
    assert body["change"] == 30.0
    assert sorted((p["method"], p["amount"]) for p in db.payments.docs) == [("cash", 20.0), ("debit", 20.0)]
    assert order(db)["paid_amount"] == 40.0 and total_sales(db) == 40.0


def test_parcial_acima_do_que_falta_e_recusado(db):
    status, body = caixa("POST", "/api/orders/o-1/partial-payments",
                         {"amount": 125.41, "payments": [{"method": "pix", "amount": 125.41}]})
    assert status == 409 and "falta pagar" in body["detail"]
    assert db.payments.docs == [] and "paid_amount" not in order(db)


def test_parcial_exige_caixa_aberto_e_pagamento_suficiente(db):
    status, body = caixa("POST", "/api/orders/o-1/partial-payments",
                         {"amount": 30.0, "payments": [{"method": "pix", "amount": 20.0}]})
    assert status == 422 and "faltam R$ 10,00" in body["detail"]
    db.cash_registers.docs[0]["is_open"] = False
    status, body = caixa("POST", "/api/orders/o-1/partial-payments",
                         {"amount": 30.0, "payments": [{"method": "pix", "amount": 30.0}]})
    assert status == 409 and "Abra o caixa" in body["detail"]
    assert db.payments.docs == []


def test_parcial_por_itens_nao_paga_a_mesma_unidade_duas_vezes(db):
    status, body = caixa("POST", "/api/orders/o-1/partial-payments", {
        "items": [{"item_id": "i-burger", "quantity": 1}], "payments": [{"method": "pix", "amount": 33.0}]})
    assert status == 200, body
    assert body["partial_payment"]["amount"] == 33.0  # 30 + 10%
    assert line(db, "i-burger")["paid_quantity"] == 1

    status, body = caixa("POST", "/api/orders/o-1/partial-payments", {
        "items": [{"item_id": "i-burger", "quantity": 3}], "payments": [{"method": "pix", "amount": 99.0}]})
    assert status == 400 and "só 2 unidade(s)" in body["detail"]

    # Paga o resto por itens: leva exatamente o que falta e a comanda fecha sem pagamento novo.
    status, body = caixa("POST", "/api/orders/o-1/partial-payments", {
        "items": [{"item_id": "i-burger", "quantity": 2}, {"item_id": "i-chopp", "quantity": 2}],
        "payments": [{"method": "credit", "amount": 92.4}]})
    assert status == 200, body
    assert body["remaining"] == 0
    assert caixa("POST", "/api/orders/o-1/close", {"payments": []})[0] == 200
    assert total_sales(db) == 125.4


def test_unidade_paga_nao_e_cancelada_nem_recebe_desconto(db):
    caixa("POST", "/api/orders/o-1/partial-payments", {
        "items": [{"item_id": "i-chopp", "quantity": 2}], "payments": [{"method": "pix", "amount": 26.4}]})
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-chopp/cancel",
                         {"quantity": 1, "reason": "erro", **ADMIN_CREDS})
    assert status == 409 and "Estorne" in body["detail"]
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-chopp/discount",
                         {"type": "percent", "value": 5, "reason": "x"})
    assert status == 400 and "não foram pagas" in body["detail"]


def test_comanda_com_parte_paga_nao_e_cancelada_nem_vira_cortesia(db):
    caixa("POST", "/api/orders/o-1/partial-payments", {"amount": 10.0, "payments": [{"method": "pix", "amount": 10.0}]})
    status, body = caixa("PATCH", "/api/orders/o-1/cancel", {"reason": "desistiu", **ADMIN_CREDS})
    assert status == 409 and "Estorne" in body["detail"]
    status, body = caixa("PATCH", "/api/orders/o-1/comp", {"is_comp": True, "comp_reason": "permuta"})
    assert status == 409 and "Estorne" in body["detail"]
    assert order(db)["is_closed"] is False and order(db)["is_comp"] is False


def test_pedido_online_ou_nostfood_nao_aceita_parcial_nem_desconto(db):
    order(db).update({"source": "online", "external_source": "nostfood"})
    status, _ = caixa("POST", "/api/orders/o-1/partial-payments",
                      {"amount": 10.0, "payments": [{"method": "pix", "amount": 10.0}]})
    assert status == 409
    status, _ = caixa("PATCH", "/api/orders/o-1/item/i-chopp/discount", {"type": "percent", "value": 5, "reason": "x"})
    assert status == 409


def test_mesa_com_varias_comandas_continua_funcionando(db):
    db.orders.docs.append(salon_order("o-2", tab=211, items=[item("i-suco", "p-suco", "Suco", 1, 8.0, "drink")]))
    caixa("POST", "/api/orders/o-1/partial-payments", {"amount": 25.4, "payments": [{"method": "pix", "amount": 25.4}]})
    assert "paid_amount" not in order(db, "o-2")
    assert caixa("POST", "/api/orders/o-2/close", {"payments": [{"method": "cash", "amount": 8.8}]})[0] == 200
    assert order(db, "o-1")["is_closed"] is False and billing.remaining_cents(order(db, "o-1")) == 10000
    assert caixa("POST", "/api/orders/o-1/close", {"payments": [{"method": "debit", "amount": 100.0}]})[0] == 200
    assert total_sales(db) == 134.2


def test_mudanca_no_meio_bloqueia_com_409(db, monkeypatch):
    # O caixa leu a comanda; antes de gravar o desconto, outro terminal recebeu uma parcial.
    stale = copy.deepcopy(order(db))
    caixa("POST", "/api/orders/o-1/partial-payments", {"amount": 10.0, "payments": [{"method": "pix", "amount": 10.0}]})
    real = server.db.orders.find_one

    async def stale_once(query=None, projection=None, **kw):
        if query == {"id": "o-1"} and not getattr(stale_once, "used", False):
            stale_once.used = True
            return copy.deepcopy(stale)
        return await real(query, projection, **kw)

    monkeypatch.setattr(server.db.orders, "find_one", stale_once)
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-burger/discount",
                         {"type": "percent", "value": 5, "reason": "cliente fiel"})
    assert status == 409 and "mudou" in body["detail"]
    assert "discount_pct" not in line(db, "i-burger")


# =====================================================================
# Estorno
# =====================================================================
def _pay_one_burger(db):
    status, body = caixa("POST", "/api/orders/o-1/partial-payments", {
        "items": [{"item_id": "i-burger", "quantity": 1}], "payments": [{"method": "cash", "amount": 50.0}]})
    assert status == 200
    return body["partial_payment"]["id"]


def test_estorno_so_admin_com_motivo(db):
    pid = _pay_one_burger(db)
    path = f"/api/orders/o-1/partial-payments/{pid}/reverse"
    status, body = caixa("POST", path, {"reason": "cobrado errado"})
    assert status == 403 and "administrador" in body["detail"]
    status, body = caixa("POST", path, {"reason": "", **ADMIN_CREDS})
    assert status == 400 and "motivo" in body["detail"]
    status, _ = caixa("POST", path, {"reason": "cobrado errado", "admin_email": "admin@x", "admin_password": "errada"})
    assert status == 403
    assert order(db)["paid_amount"] == 33.0 and total_sales(db) == 33.0


def test_estorno_desfaz_valor_itens_e_caixa(db):
    pid = _pay_one_burger(db)
    status, body = caixa("POST", f"/api/orders/o-1/partial-payments/{pid}/reverse",
                         {"reason": "cobrado errado", **ADMIN_CREDS})
    assert status == 200, body
    o = order(db)
    assert o["paid_amount"] == 0 and line(db, "i-burger")["paid_quantity"] == 0
    entry = o["partial_payments"][0]
    assert entry["status"] == "reversed" and entry["reversal_reason"] == "cobrado errado"
    assert entry["reversed_by_name"] == "Admin Bia" and entry["reversed_by_cashier_name"] == "Caixa Ana"
    assert db.payments.docs == []
    assert len(db.payment_reversals.docs) == 1 and db.payment_reversals.docs[0]["reversal_reason"] == "cobrado errado"
    assert total_sales(db) == 0

    status, _ = admin("POST", f"/api/orders/o-1/partial-payments/{pid}/reverse", {"reason": "de novo"})
    assert status == 409
    # Depois do estorno a comanda volta a cobrar tudo e fecha normalmente.
    assert caixa("POST", "/api/orders/o-1/close", {"payments": [{"method": "pix", "amount": 125.4}]})[0] == 200


def test_admin_logado_estorna_sem_digitar_senha(db):
    pid = _pay_one_burger(db)
    status, body = admin("POST", f"/api/orders/o-1/partial-payments/{pid}/reverse", {"reason": "teste"})
    assert status == 200 and body["reversed"]["reversed_by_name"] == "Admin Bia"


# =====================================================================
# B) Desconto por item
# =====================================================================
def test_desconto_e_cortesia_com_10_por_cento(db):
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-chopp/discount",
                         {"quantity": 1, "type": "percent", "value": 10, "reason": "chopp quente"})
    assert status == 200, body
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-burger/courtesy",
                         {"is_courtesy": True, "quantity": 1, "reason": "aniversário"})
    assert status == 200, body
    # 2 x 30 + 1 cortesia + 1 x 10,80 + 1 x 12 = 82,80; 10% sobre o cobrado = 8,28
    assert body["subtotal"] == 82.8 and body["service_fee"] == 8.28 and body["total"] == 91.08
    assert body["item_discount_total"] == 1.2 and body["item_courtesy_total"] == 30.0
    disc = next(i for i in body["items"] if i.get("discount_pct"))
    assert disc["quantity"] == 1 and disc["unit_price"] == 10.8 and disc["discount_original_price"] == 12.0
    assert disc["discount_reason"] == "chopp quente" and disc["discount_by_name"] == "Caixa Ana" and disc["discount_at"]


def test_desconto_em_reais_por_unidade(db):
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-burger/discount",
                         {"type": "value", "value": 3.0, "reason": "demorou"})
    assert status == 200, body
    burger = next(i for i in body["items"] if i["id"] == "i-burger")
    assert burger["quantity"] == 3 and burger["unit_price"] == 27.0 and burger["discount_pct"] == 10.0
    assert body["item_discount_total"] == 9.0


def test_caixa_ate_10_por_cento_acima_so_admin(db):
    body = {"type": "percent", "value": 15, "reason": "reclamação"}
    status, resp = caixa("PATCH", "/api/orders/o-1/item/i-burger/discount", body)
    assert status == 403 and "administrador" in resp["detail"]
    assert line(db, "i-burger")["unit_price"] == 30.0

    status, resp = caixa("PATCH", "/api/orders/o-1/item/i-burger/discount", {**body, **ADMIN_CREDS})
    assert status == 200, resp
    burger = line(db, "i-burger")
    assert burger["unit_price"] == 25.5 and burger["discount_by_name"] == "Caixa Ana"
    assert burger["discount_approved_by_name"] == "Admin Bia"


def test_admin_logado_da_desconto_maior(db):
    status, body = admin("PATCH", "/api/orders/o-1/item/i-burger/discount",
                         {"type": "percent", "value": 40, "reason": "teste"})
    assert status == 200 and line(db, "i-burger")["unit_price"] == 18.0


def test_desconto_de_100_por_cento_manda_usar_cortesia(db):
    status, body = admin("PATCH", "/api/orders/o-1/item/i-burger/discount",
                         {"type": "percent", "value": 100, "reason": "x"})
    assert status == 400 and "Cortesia" in body["detail"]


def test_desconto_exige_motivo(db):
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-burger/discount", {"type": "percent", "value": 5})
    assert status == 400 and "motivo" in body["detail"]


def test_tirar_desconto_volta_o_preco_e_junta_a_linha(db):
    caixa("PATCH", "/api/orders/o-1/item/i-burger/discount",
          {"quantity": 1, "type": "percent", "value": 10, "reason": "x"})
    split = next(i for i in order(db)["items"] if i.get("split_from") == "i-burger")
    status, body = caixa("DELETE", f"/api/orders/o-1/item/{split['id']}/discount")
    assert status == 200, body
    burgers = [i for i in body["items"] if i["product_id"] == "p-burger"]
    assert len(burgers) == 1 and burgers[0]["quantity"] == 3 and burgers[0]["unit_price"] == 30.0
    assert "discount_pct" not in burgers[0] and body["item_discount_total"] == 0 and body["total"] == 125.4


# =====================================================================
# C) Cortesia por quantidade
# =====================================================================
def test_cortesia_de_1_de_3_lanches(db):
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-burger/courtesy",
                         {"is_courtesy": True, "quantity": 1, "reason": "aniversário"})
    assert status == 200, body
    burgers = [i for i in body["items"] if i["product_id"] == "p-burger"]
    assert [(i["quantity"], i["unit_price"], i["is_courtesy"]) for i in burgers] == [(2, 30.0, False), (1, 0, True)]
    gift = burgers[1]
    assert gift["courtesy_original_price"] == 30.0 and gift["courtesy_reason"] == "aniversário"
    assert gift["courtesy_by_name"] == "Caixa Ana" and gift["courtesy_at"] and gift["split_from"] == "i-burger"
    assert body["subtotal"] == 84.0 and body["service_fee"] == 8.4 and body["item_courtesy_total"] == 30.0

    # Continua baixando estoque das 3 unidades no fechamento.
    assert caixa("POST", "/api/orders/o-1/close", {"payments": [{"method": "pix", "amount": 92.4}]})[0] == 200
    assert sum(q for p, q in db.deducted if p == "p-burger") == 3


def test_desmarcar_cortesia_devolve_o_preco_e_junta_a_linha(db):
    caixa("PATCH", "/api/orders/o-1/item/i-burger/courtesy",
          {"is_courtesy": True, "quantity": 1, "reason": "aniversário"})
    gift = next(i for i in order(db)["items"] if i.get("is_courtesy"))
    status, body = caixa("PATCH", f"/api/orders/o-1/item/{gift['id']}/courtesy", {"is_courtesy": False})
    assert status == 200, body
    burgers = [i for i in body["items"] if i["product_id"] == "p-burger"]
    assert len(burgers) == 1 and burgers[0]["quantity"] == 3 and burgers[0]["unit_price"] == 30.0
    assert body["total"] == 125.4 and body["item_courtesy_total"] == 0


def test_cortesia_em_item_com_desconto_usa_o_preco_cheio(db):
    caixa("PATCH", "/api/orders/o-1/item/i-chopp/discount", {"type": "percent", "value": 10, "reason": "x"})
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-chopp/courtesy",
                         {"is_courtesy": True, "quantity": 1, "reason": "cliente"})
    assert status == 200
    gift = next(i for i in body["items"] if i.get("is_courtesy"))
    assert gift["courtesy_original_price"] == 12.0 and "discount_pct" not in gift
    assert body["item_courtesy_total"] == 12.0 and body["item_discount_total"] == 1.2  # o outro chopp segue com desconto


def test_cortesia_quantidade_invalida(db):
    status, body = caixa("PATCH", "/api/orders/o-1/item/i-burger/courtesy",
                         {"is_courtesy": True, "quantity": 4, "reason": "x"})
    assert status == 400


# =====================================================================
# Relatórios
# =====================================================================
def test_fechamento_separa_desconto_cortesia_e_promocao(db):
    caixa("PATCH", "/api/orders/o-1/item/i-chopp/discount", {"type": "percent", "value": 10, "reason": "x"})
    caixa("PATCH", "/api/orders/o-1/item/i-burger/courtesy", {"is_courtesy": True, "quantity": 1, "reason": "y"})
    total = order(db)["total"]
    assert caixa("POST", "/api/orders/o-1/close", {"payments": [{"method": "pix", "amount": total}]})[0] == 200
    status, report = caixa("GET", "/api/cash-register/preview")
    assert status == 200
    assert report["item_discount_total"] == 2.4 and report["item_courtesy_total"] == 30.0
    assert report["item_promo_total"] == 0


def test_previa_mostra_parciais_de_comandas_abertas(db):
    caixa("POST", "/api/orders/o-1/partial-payments", {"amount": 20.0, "payments": [{"method": "pix", "amount": 20.0}]})
    status, report = caixa("GET", "/api/cash-register/preview")
    assert status == 200
    assert report["open_partial_payments"] == {"orders": 1, "amount": 20.0}
    assert report["open_orders"] == 1  # o fechamento do caixa continua bloqueado
