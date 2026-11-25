"""Estoque, etapa 1: backend/scripts/diagnostico_estoque.py é somente leitura.

Teste OFFLINE com banco falso que FALHA em qualquer tentativa de escrita.
Rodar: cd backend && python -m pytest tests/test_diagnostico_estoque.py
"""
import copy
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import diagnostico_estoque as de  # noqa: E402

AGORA = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
RECENTE = "2026-11-10T20:00:00+00:00"
ANTIGO = "2026-08-01T20:00:00+00:00"


def _match(doc, query):
    for k, v in query.items():
        val = doc.get(k)
        if isinstance(v, dict):
            for op, arg in v.items():
                if op == "$gte" and not (val is not None and str(val) >= str(arg)):
                    return False
        elif val != v:
            return False
    return True


def _project(doc, proj):
    doc = copy.deepcopy(doc)
    doc.pop("_id", None)
    incl = [k for k, v in (proj or {}).items() if v == 1]
    if not incl:
        return doc
    out = {}
    sub = [k.split(".", 1)[1] for k in incl if k.startswith("items.")]
    for k in incl:
        if "." not in k and k in doc:
            out[k] = doc[k]
    if sub and "items" in doc:
        out["items"] = [{s: it[s] for s in sub if s in it} for it in doc["items"]]
    return out


class ReadOnly:
    def __init__(self, name, docs, log):
        self.name, self.docs, self.log = name, docs, log

    def find(self, query=None, projection=None):
        self.log.append((self.name, projection))
        return [_project(d, projection) for d in self.docs if _match(d, query or {})]

    def find_one(self, query=None, projection=None):
        r = self.find(query, projection)
        return r[0] if r else None

    def count_documents(self, query):
        return len(self.find(query))

    def __getattr__(self, attr):  # qualquer escrita
        raise AssertionError(f"escrita proibida: {self.name}.{attr}")


class FakeDB:
    def __init__(self, data):
        self.log = []
        self.cols = {k: ReadOnly(k, v, self.log) for k, v in data.items()}

    def __getattr__(self, name):
        if name.startswith("_") or name in ("log", "cols"):
            raise AttributeError(name)
        return self.cols.setdefault(name, ReadOnly(name, [], self.log))

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def data():
    return {
        "categories": [{"id": "c1", "name": "Lanches"}, {"id": "c2", "name": "Bebidas"}],
        "products": [
            {"id": "p-burger", "name": "Hambúrguer Amós", "type": "food", "category_id": "c1"},
            {"id": "p-batata", "name": "Batata individual", "type": "food", "category_id": "c1"},
            {"id": "p-coca", "name": "Coca lata", "type": "drink", "category_id": "c2"},
            {"id": "p-porcao", "name": "Porção de frango", "type": "food", "category_id": "c1"},
            {"id": "p-suco", "name": "Suco", "type": "drink", "category_id": "c2"},
        ],
        "stock": [
            {"id": "s-carne", "name": "Carne moída", "unit": "kg", "quantity": 5, "unit_cost": 40},
            {"id": "s-pao", "name": "Pão", "unit": "unit", "quantity": 30, "unit_cost": 0},
            {"id": "s-batata", "name": "Batata", "unit": "gram", "quantity": 2000, "unit_cost": 0.02},
            {"id": "s-coca", "product_id": "p-coca", "unit": "unit", "quantity": 24, "unit_cost": 3},
            {"id": "s-sal", "name": "Sal", "unit": "kg", "quantity": -1, "unit_cost": 2},
            {"id": "s-burger-pronto", "name": "Hambúrguer 150g pronto", "unit": "unit", "quantity": 10, "unit_cost": 6},
        ],
        "recipes": [
            {"id": "r1", "product_id": "p-burger", "ingredients": [
                {"stock_item_id": "s-carne", "quantity": 150},   # digitado em g num item em kg
                {"stock_item_id": "s-pao", "quantity": 1},       # sem custo
            ]},
            {"id": "r2", "product_id": "p-batata", "ingredients": [
                {"stock_item_id": "s-batata", "quantity": 0.15},  # digitado em kg num item em g
                {"stock_item_id": "s-sumiu", "quantity": 1},      # ingrediente inexistente
            ]},
            {"id": "r3", "product_id": "p-apagado", "ingredients": [{"stock_item_id": "s-pao", "quantity": 0}]},
        ],
        "technical_sheets": [{"product_id": "p-porcao"}, {"product_id": "p-burger"}],
        "production_recipes": [{"produced_stock_item_id": "s-burger-pronto",
                                "ingredients": [{"stock_item_id": "s-carne", "quantity": 1.5}]}],
        "orders": [
            {"id": "o1", "is_closed": True, "closed_at": RECENTE, "status": "delivered", "tab_number": 201,
             "customer_name": "NAO-DEVE-APARECER", "customer_phone": "11999990000", "address": "Rua Secreta",
             "items": [
                 {"product_id": "p-burger", "product_name": "Hambúrguer Amós", "quantity": 2, "status": "delivered", "stock_deducted": False},
                 {"product_id": "p-coca", "product_name": "Coca lata", "quantity": 1, "status": "delivered", "stock_deducted": True},
                 {"product_id": "p-porcao", "product_name": "Porção de frango", "quantity": 1, "status": "delivered", "stock_deducted": False},
                 {"product_id": "p-batata", "product_name": "Batata individual", "quantity": 1, "status": "cancelled", "stock_deducted": False},
             ]},
            {"id": "o2", "is_closed": True, "closed_at": RECENTE, "status": "cancelled",
             "items": [{"product_id": "p-burger", "quantity": 5, "status": "pending", "stock_deducted": False}]},
            {"id": "o3", "is_closed": True, "closed_at": ANTIGO, "status": "delivered",
             "items": [{"product_id": "p-burger", "quantity": 9, "status": "delivered", "stock_deducted": False}]},
            {"id": "o4", "is_closed": False, "status": "pending",
             "items": [{"product_id": "p-burger", "quantity": 7, "status": "pending", "stock_deducted": False}]},
        ],
    }


def _run(data, capsys, **kw):
    db = FakeDB(copy.deepcopy(data))
    before = copy.deepcopy(data)
    assert de.relatorio(db, agora=AGORA, **kw) == 0
    out = capsys.readouterr().out
    assert {k: c.docs for k, c in db.cols.items() if k in before} == before  # nada mudou
    return out, db


def _bloco(out, inicio, fim):
    return out[out.index(inicio):out.index(fim)]


def test_report_is_read_only_and_has_no_customer_data(data, capsys):
    out, db = _run(data, capsys)
    for segredo in ("NAO-DEVE-APARECER", "11999990000", "Rua Secreta"):
        assert segredo not in out
    proj = [p for n, p in db.log if n == "orders"]
    assert proj and all(not any(k.startswith("customer") or k == "address" for k in p) for p in proj)
    assert "Nada foi gravado no banco." in out


def test_products_without_recipe(data, capsys):
    out, _ = _run(data, capsys)
    nunca = _bloco(out, "NUNCA baixam nada", "Com ficha técnica")
    assert "Porção de frango" in nunca and "Suco" in nunca
    assert "Hambúrguer Amós" not in nunca and "Coca lata" not in nunca
    ficha = _bloco(out, "Com ficha técnica", "Só estoque direto")
    assert "Porção de frango" in ficha and "Hambúrguer Amós" not in ficha
    direto = _bloco(out, "Só estoque direto", "--- 2.")
    assert "Coca lata" in direto


def test_recipe_problems(data, capsys):
    out, _ = _run(data, capsys)
    bloco = _bloco(out, "--- 2.", "--- 3.")
    assert "Carne moída: 150 kg por porção: parece digitado em g/ml" in bloco
    assert "Batata: 0.15 gram por porção: parece digitado em kg" in bloco
    assert "ingrediente inexistente no estoque (id s-sumiu)" in bloco
    assert "Pão: insumo sem custo" in bloco
    assert "receita de produto que não existe mais" in bloco
    assert "quantidade 0" in bloco


def test_unused_and_negative_stock(data, capsys):
    out, _ = _run(data, capsys)
    bloco = _bloco(out, "Itens que nenhuma receita usa", "Itens com saldo negativo")
    assert "Coca lata" in bloco and "ligado direto a produto" in bloco
    assert "Sal" in bloco
    assert "Carne moída" not in bloco and "Pão" not in bloco
    assert "Hambúrguer 150g pronto" not in bloco  # usado na produção
    neg = _bloco(out, "Itens com saldo negativo", "--- 4.")
    assert "Sal: -1 kg" in neg


def test_failed_deductions_from_database(data, capsys):
    out, _ = _run(data, capsys)
    bloco = _bloco(out, "--- 4.", "Vendidos sem baixa")
    assert "Comandas fechadas analisadas: 2" in bloco  # o1 e o2 (cancelada); o3 é antiga, o4 aberta
    assert "Hambúrguer Amós: 1 item(ns), qtd 2 — ex.: pedidos o1" in bloco
    assert "Coca lata" not in bloco and "Batata" not in bloco  # baixou / item cancelado
    sem = out[out.index("Vendidos sem baixa"):]
    assert "Porção de frango: 1 item(ns), qtd 1" in sem


def test_window_in_days(data, capsys):
    out, _ = _run(data, capsys, dias=200)
    assert "Hambúrguer Amós: 2 item(ns), qtd 11" in out  # o1 + o3


def test_log_parsing(data, capsys):
    log = [
        "2026-11-10 WARNING [close_order] Baixa falhou para Hambúrguer Amós: Estoque insuficiente: Carne moída: solicitado 300.0, disponivel 5.0\n",
        "2026-11-10 WARNING [close_order] Baixa falhou para Hambúrguer Amós: Estoque insuficiente: x\n",
        'INFO: 1.2.3.4:0 - "PUT /api/orders/o1/item/i1/status HTTP/1.1" 400 Bad Request\n',
        'INFO: 1.2.3.4:0 - "PUT /api/orders/o1/item/i1/status HTTP/1.1" 200 OK\n',
        "linha qualquer\n",
    ]
    out, _ = _run(data, capsys, log_linhas=log)
    assert "Hambúrguer Amós: 2 vez(es) — ex.: Estoque insuficiente: Carne moída: solicitado 300.0" in out
    assert "recusadas com 400 (inclui falta de estoque): 1" in out


def test_without_log_says_so(data, capsys):
    out, _ = _run(data, capsys)
    assert "Sem --log" in out


def test_limit(data, capsys):
    out, _ = _run(data, capsys, limite=1)
    assert "... e mais" in out


@pytest.mark.parametrize("q,unit,suspeito", [
    (0.15, "kg", False), (1, "kg", False), (1.5, "kg", True), (150, "liter", True),
    (150, "gram", False), (0.2, "gram", True), (2, "unit", False), (50, "unit", True),
])
def test_unit_rules(q, unit, suspeito):
    assert (de.unidade_suspeita(q, unit) is not None) == suspeito


def test_missing_env_does_not_connect(monkeypatch, capsys):
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    def nao_conecte(*a, **k):
        raise AssertionError("conectou")

    assert de.main([], client_factory=nao_conecte) == 2
    assert "MONGO_URL" in capsys.readouterr().err


def test_main_runs_with_fake_client(data, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("MONGO_URL", "mongodb://teste-offline:1")
    monkeypatch.setenv("DB_NAME", "teste")
    log = tmp_path / "render.log"
    log.write_text("[close_order] Baixa falhou para Suco: x\n", encoding="utf-8")
    db = FakeDB(copy.deepcopy(data))

    class Client:
        def __getitem__(self, name):
            assert name == "teste"
            return db

        def close(self):
            pass

    assert de.main(["--log", str(log)], client_factory=lambda *a, **k: Client()) == 0
    assert "Suco: 1 vez(es)" in capsys.readouterr().out


def test_bad_log_path(monkeypatch, capsys):
    monkeypatch.setenv("MONGO_URL", "mongodb://teste-offline:1")
    monkeypatch.setenv("DB_NAME", "teste")
    assert de.main(["--log", "/caminho/que/nao/existe.log"],
                   client_factory=lambda *a, **k: (_ for _ in ()).throw(AssertionError("conectou"))) == 2
