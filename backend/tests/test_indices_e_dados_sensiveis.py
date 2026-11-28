"""PR 1: índices, pedidos abertos sem limite, chave fiscal e CPF escondidos.

Teste OFFLINE (banco falso em memória, sem servidor e sem rede).
Rodar: cd backend && python -m pytest tests/test_indices_e_dados_sensiveis.py
"""
import asyncio
import logging

import pytest

import db_indexes
from _fake_mongo import FakeDB
from _offline_app import call, server, token_for

ADMIN = {"id": "u-admin", "name": "Admin", "email": "admin@x", "role": "admin", "is_active": True}
CAIXA = {"id": "u-caixa", "name": "Caixa", "email": "caixa@x", "role": "cashier", "is_active": True}
CPF = "123.456.789-09"


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    fake.users.docs += [dict(ADMIN), dict(CAIXA)]
    monkeypatch.setattr(server, "db", fake)
    return fake


# ---------- índices ----------

def test_indices_criados_com_nome_e_sem_unico(db):
    ok, failed = asyncio.run(db_indexes.ensure_indexes(db, logging.getLogger("teste")))
    assert failed == []
    assert len(ok) == len(db_indexes.INDEXES)
    assert [f for f, _ in db.payments.indexes] == [["order_id"], ["register_id"], ["created_at", "_id"]]
    assert db.orders.indexes[0][0] == ["is_closed", "closed_at"]
    # Nenhum índice único neste passo: dependem do verificar_duplicados.py.
    for col in ("orders", "payments", "invoices", "cash_registers", "payment_reversals"):
        assert all(not opts["unique"] for _, opts in db[col].indexes)
        assert all(opts["name"] for _, opts in db[col].indexes)


def test_falha_de_indice_nao_derruba_e_segue_para_os_proximos(db):
    async def boom(*a, **k):
        raise RuntimeError("conflito de definição")
    db.payments.create_index = boom
    ok, failed = asyncio.run(db_indexes.ensure_indexes(db, logging.getLogger("teste")))
    assert failed == ["payments_order_id", "payments_register_id", "payments_created_at"]
    assert "invoices_order_id" in ok and "payment_reversals_order_id" in ok


# ---------- pedidos abertos ----------

def test_pedidos_abertos_sem_limite_e_em_ordem(db):
    # 150 abertos (antes o corte era 100), gravados fora de ordem, e 1 fechado.
    for n in range(150):
        db.orders.docs.append({"_id": n, "id": f"o-{n}", "is_closed": False, "items": [],
                               "created_at": f"2026-11-27T{(149 - n) // 60:02d}:{(149 - n) % 60:02d}:00+00:00"})
    db.orders.docs.append({"_id": 999, "id": "fechado", "is_closed": True, "items": []})
    status, data = call("GET", "/api/orders/open", token_for(CAIXA["id"]))
    assert status == 200
    assert len(data) == 150
    assert [o["created_at"] for o in data] == sorted(o["created_at"] for o in data)
    assert data[0]["id"] == "o-149" and "fechado" not in {o["id"] for o in data}


def test_nostfood_kds_tambem_sem_limite(db, monkeypatch):
    import nostfood_integration as nf
    monkeypatch.setattr(nf.S, "db", db)
    db.orders.docs += [{"_id": n, "id": f"o-{n}", "is_closed": False, "created_at": f"2026-11-27T10:{n % 60:02d}:{n // 60:02d}"}
                       for n in range(130)]
    assert len(asyncio.run(nf._open_orders())) == 130


# ---------- chave da API fiscal ----------

def test_get_settings_nunca_devolve_a_chave(db):
    db.settings.docs.append({"_id": "fiscal", "taxEnabled": True, "taxApiKey": "segredo-123"})
    status, data = call("GET", "/api/settings", token_for(ADMIN["id"]))
    assert status == 200
    assert data["fiscal"] == {"taxEnabled": True, "taxApiKeyConfigured": True}
    assert "segredo-123" not in str(data)


def test_get_settings_sem_chave(db):
    status, data = call("GET", "/api/settings", token_for(ADMIN["id"]))
    assert status == 200 and data["fiscal"] == {"taxApiKeyConfigured": False}


def _fiscal(db):
    return next(d for d in db.settings.docs if d["_id"] == "fiscal")


def test_salvar_com_chave_vazia_mantem_a_chave(db):
    db.settings.docs.append({"_id": "fiscal", "taxEnabled": True, "taxApiKey": "segredo-123"})
    # O formulário reenvia o que recebeu do GET, com a chave vazia.
    body = {"fiscal": {"taxEnabled": False, "taxApiKey": "", "taxApiKeyConfigured": True}}
    assert call("PUT", "/api/settings", token_for(ADMIN["id"]), body)[0] == 200
    assert _fiscal(db) == {"_id": "fiscal", "taxEnabled": False, "taxApiKey": "segredo-123"}


def test_salvar_chave_nova_e_remover(db):
    db.settings.docs.append({"_id": "fiscal", "taxApiKey": "antiga"})
    call("PUT", "/api/settings", token_for(ADMIN["id"]), {"fiscal": {"taxApiKey": "  nova  "}})
    assert _fiscal(db)["taxApiKey"] == "nova"
    call("PUT", "/api/settings", token_for(ADMIN["id"]), {"fiscal": {"taxApiKey": "", "taxApiKeyClear": True}})
    assert "taxApiKey" not in _fiscal(db)
    assert call("GET", "/api/settings", token_for(ADMIN["id"]))[1]["fiscal"]["taxApiKeyConfigured"] is False


def test_settings_continua_so_admin(db):
    assert call("GET", "/api/settings", token_for(CAIXA["id"]))[0] == 403


# ---------- CPF nas notas ----------

@pytest.mark.parametrize("cpf, esperado", [
    ("123.456.789-09", "***.456.***-**"),
    ("12345678909", "***.456.***-**"),
    ("123", "***"),
    (None, None),
    ("", ""),
])
def test_mask_cpf(cpf, esperado):
    assert server.mask_cpf(cpf) == esperado


def test_get_invoices_esconde_cpf_completo(db):
    db.invoices.docs.append({"_id": 1, "id": "nf-1", "order_id": "o-1", "customer_name": "Cliente",
                             "customer_cpf": CPF, "number": "NF-1", "status": "mock", "total": 10.0})
    status, data = call("GET", "/api/invoices", token_for(CAIXA["id"]))
    assert status == 200
    assert data[0]["customer_cpf"] == "***.456.***-**"
    assert "789" not in str(data) and "12345678909" not in str(data)
    # O banco continua com o CPF original: só a resposta é mascarada.
    assert db.invoices.docs[0]["customer_cpf"] == CPF


def test_post_invoice_grava_cpf_e_devolve_mascarado(db):
    db.orders.docs.append({"_id": 1, "id": "o-1", "total": 25.0, "is_closed": True})
    status, data = call("POST", "/api/invoices", token_for(CAIXA["id"]),
                        {"order_id": "o-1", "customer_name": "Cliente", "customer_cpf": CPF})
    assert status == 200
    assert data["customer_cpf"] == "***.456.***-**"
    assert db.invoices.docs[0]["customer_cpf"] == CPF
