"""fix/estoque-cmv: conversão de unidade, baixa que nunca bloqueia nem é
silenciosa, aviso ao lançar e CMV com `incomplete`.

Teste OFFLINE (sem servidor e sem MongoDB): banco falso em memória.
Rodar: cd backend && python -m pytest tests/test_estoque_cmv.py
"""
import asyncio
import copy

import pytest
from _offline_app import call, server, token_for


# =====================================================================
# Banco falso mínimo (find_one, find().to_list, insert_one, update_one, delete_one)
# =====================================================================
def _match(doc, query):
    return all(doc.get(k) == v for k, v in query.items())


class _Result:
    def __init__(self, matched=0, deleted=0):
        self.matched_count = matched
        self.modified_count = matched
        self.deleted_count = deleted


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return [copy.deepcopy(d) for d in self._docs[:n]]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [copy.deepcopy(d) for d in (docs or [])]

    async def find_one(self, query, projection=None, session=None):
        for d in self.docs:
            if _match(d, query):
                return copy.deepcopy(d)
        return None

    def find(self, query=None, projection=None):
        return _Cursor([d for d in self.docs if _match(d, query or {})])

    async def insert_one(self, doc, session=None):
        self.docs.append(copy.deepcopy(doc))

    async def update_one(self, query, update, session=None, upsert=False):
        for d in self.docs:
            if _match(d, query):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k, v in update.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v
                return _Result(matched=1)
        return _Result()

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return _Result(deleted=1)
        return _Result()


class FakeDB:
    def __init__(self, **cols):
        self._cols = {k: FakeCollection(v) for k, v in cols.items()}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._cols.setdefault(name, FakeCollection())


USERS = [
    {"id": "u-admin", "name": "Admin", "email": "a@example.invalid", "role": "admin"},
    {"id": "u-waiter", "name": "Garçom", "email": "w@example.invalid", "role": "waiter"},
]

PRODUCTS = [
    {"id": "p-lanche", "name": "X-Burger", "price": 30.0, "category_id": "c1", "type": "food"},
    {"id": "p-suco", "name": "Suco", "price": 10.0, "category_id": "c2", "type": "drink"},
    {"id": "p-antigo", "name": "Porção antiga", "price": 20.0, "category_id": "c1", "type": "food"},
    {"id": "p-sem", "name": "Sem receita", "price": 15.0, "category_id": "c1", "type": "food"},
]

STOCK = [
    {"id": "s-carne", "name": "Carne", "unit": "kg", "quantity": 10.0, "unit_cost": 40.0, "min_quantity": 1},
    {"id": "s-pao", "name": "Pão", "unit": "unit", "quantity": 50.0, "unit_cost": 1.5, "min_quantity": 5},
    {"id": "s-leite", "name": "Leite", "unit": "liter", "quantity": 5.0, "unit_cost": 6.0, "min_quantity": 1},
    {"id": "s-batata", "name": "Batata", "unit": "kg", "quantity": 8.0, "unit_cost": 5.0, "min_quantity": 1},
]

RECIPES = [
    # receita nova, com unidade: 150 g de carne (insumo em kg) + 1 pão
    {"id": "r-lanche", "product_id": "p-lanche", "ingredients": [
        {"stock_item_id": "s-carne", "quantity": 150, "unit": "gram"},
        {"stock_item_id": "s-pao", "quantity": 1},
    ]},
    # 300 ml de leite (insumo em litro)
    {"id": "r-suco", "product_id": "p-suco", "ingredients": [
        {"stock_item_id": "s-leite", "quantity": 300, "unit": "ml"},
    ]},
    # receita antiga, sem unidade: 0,4 já está em kg (não pode mudar)
    {"id": "r-antigo", "product_id": "p-antigo", "ingredients": [
        {"stock_item_id": "s-batata", "quantity": 0.4},
    ]},
]


@pytest.fixture
def fdb(monkeypatch):
    db = FakeDB(users=USERS, products=PRODUCTS, stock=STOCK, recipes=RECIPES)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.sio, "emit", noop)
    monkeypatch.setattr(server, "send_whatsapp_message", noop)
    return db


def run(coro):
    return asyncio.run(coro)


def qty(db, sid):
    return next(d for d in db.stock.docs if d["id"] == sid)["quantity"]


def failures(db):
    return db.stock_deduction_failures.docs


# =====================================================================
# 1) Conversão de unidade
# =====================================================================
@pytest.mark.parametrize("q,f,t,expected", [
    (150, "g", "kg", 0.15), (150, "gram", "kg", 0.15), (1.5, "kg", "gram", 1500),
    (300, "ml", "liter", 0.3), (0.5, "l", "ml", 500), (2, "un", "unit", 2), (250, "g", "g", 250),
])
def test_convert_quantity(q, f, t, expected):
    assert server.convert_quantity(q, f, t) == pytest.approx(expected)


@pytest.mark.parametrize("f,t", [("g", "liter"), ("ml", "kg"), ("un", "kg"), ("xícara", "kg"), ("g", None)])
def test_convert_quantity_invalid(f, t):
    with pytest.raises(server.UnitConversionError):
        server.convert_quantity(1, f, t)


def test_ingredient_without_unit_keeps_legacy_quantity():
    # Sem "unit" a quantidade NÃO é convertida (receitas existentes intactas).
    assert server.ingredient_qty_in_stock_unit({"quantity": 150}, {"unit": "kg"}) == 150
    assert server.ingredient_qty_in_stock_unit({"quantity": 150, "unit": ""}, {"unit": "kg"}) == 150


# =====================================================================
# 2) Baixa
# =====================================================================
def test_deduct_converts_grams_to_kg(fdb):
    assert run(server.deduct_stock("p-lanche", 2, order_code="o1")) == []
    assert qty(fdb, "s-carne") == pytest.approx(10 - 0.3)
    assert qty(fdb, "s-pao") == pytest.approx(48)
    assert failures(fdb) == []


def test_deduct_converts_ml_to_liter(fdb):
    run(server.deduct_stock("p-suco", 3))
    assert qty(fdb, "s-leite") == pytest.approx(5 - 0.9)


def test_deduct_legacy_recipe_unchanged(fdb):
    run(server.deduct_stock("p-antigo", 2))
    assert qty(fdb, "s-batata") == pytest.approx(8 - 0.8)


def test_shortage_deducts_anyway_and_records(fdb):
    out = run(server.deduct_stock("p-lanche", 100, order_code="o9"))  # 15 kg de carne, há 10
    assert qty(fdb, "s-carne") == pytest.approx(-5)          # ficou negativo
    assert qty(fdb, "s-pao") == pytest.approx(-50)
    kinds = sorted(f["kind"] for f in failures(fdb))
    assert kinds == ["saldo_insuficiente", "saldo_insuficiente"]
    assert len(out) == 2
    # cada falha traz produto, insumo, tipo e pedidos
    for f in failures(fdb):
        assert f["product_id"] == "p-lanche" and f["product_name"] == "X-Burger"
        assert f["last_orders"] == ["o9"]
    assert sorted((f["stock_item_id"], f["stock_item_name"]) for f in failures(fdb)) == [
        ("s-carne", "Carne"), ("s-pao", "Pão")]


def test_missing_ingredient_recorded_others_deducted(fdb):
    fdb.recipes.docs[0]["ingredients"].append({"stock_item_id": "s-sumiu", "quantity": 1})
    run(server.deduct_stock("p-lanche", 1, order_code="o5"))
    assert qty(fdb, "s-pao") == pytest.approx(49)               # baixa parcial
    assert qty(fdb, "s-carne") == pytest.approx(10 - 0.15)
    [f] = failures(fdb)
    assert (f["kind"], f["product_id"], f["stock_item_id"], f["last_orders"]) == (
        "insumo_inexistente", "p-lanche", "s-sumiu", ["o5"])


def test_incompatible_unit_recorded_not_deducted(fdb):
    fdb.recipes.docs[1]["ingredients"][0]["unit"] = "gram"  # g x litro
    run(server.deduct_stock("p-suco", 1))
    assert qty(fdb, "s-leite") == pytest.approx(5)
    [f] = failures(fdb)
    assert (f["kind"], f["stock_item_id"], f["stock_item_name"]) == ("unidade_incompativel", "s-leite", "Leite")


def test_no_recipe_no_stock_does_not_record_failure(fdb):
    # decisão (2): sem registro por venda; vira incomplete no CMV
    assert run(server.deduct_stock("p-sem", 1, order_code="o1")) == []
    assert failures(fdb) == []


def test_repeated_failure_aggregates(fdb):
    run(server.deduct_stock("p-lanche", 100, order_code="o1"))
    run(server.deduct_stock("p-lanche", 100, order_code="o2"))
    assert len(failures(fdb)) == 2                    # carne e pão
    for f in failures(fdb):
        assert f["occurrences"] == 2
        assert f["last_orders"] == ["o2", "o1"]


def test_legacy_direct_stock_shortage_deducts_anyway(fdb):
    fdb.stock.docs.append({"id": "s-refri", "product_id": "p-sem", "unit": "unit", "quantity": 1.0})
    run(server.deduct_stock("p-sem", 3))
    assert qty(fdb, "s-refri") == pytest.approx(-2)
    assert [f["kind"] for f in failures(fdb)] == ["saldo_insuficiente"]


def test_failure_recording_never_raises(fdb, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(fdb.stock_deduction_failures, "find_one", boom)
    # não pode levantar: a venda segue e a baixa acontece
    out = run(server.deduct_stock("p-lanche", 100))
    assert len(out) == 2
    assert qty(fdb, "s-carne") == pytest.approx(-5)


def test_restore_converts_units(fdb):
    run(server.deduct_stock("p-lanche", 2))
    run(server.restore_stock("p-lanche", 2))
    assert qty(fdb, "s-carne") == pytest.approx(10)
    assert qty(fdb, "s-pao") == pytest.approx(50)


# =====================================================================
# 3) Aviso ao lançar: receita só avisa; legado continua bloqueando
# =====================================================================
def _items(*pairs):
    return [{"product_id": p, "quantity": q, "product_name": p} for p, q in pairs]


def test_validate_recipe_shortage_only_warns(fdb):
    warnings = run(server.validate_stock(_items(("p-lanche", 100))))
    assert any("Carne" in w and "negativo" in w for w in warnings)
    assert qty(fdb, "s-carne") == 10  # validar não baixa nada


def test_validate_sums_items_sharing_ingredient(fdb):
    # 2 linhas de 30 lanches = 9 kg de carne (resta 1 = mínimo) -> estoque baixo
    warnings = run(server.validate_stock(_items(("p-lanche", 30), ("p-lanche", 30))))
    assert any("Carne" in w and "estoque baixo" in w for w in warnings)


def test_validate_no_warning_when_ok(fdb):
    assert run(server.validate_stock(_items(("p-lanche", 1)))) == []


def test_validate_legacy_direct_stock_only_warns(fdb):
    # decisão (1): estoque ligado direto ao produto também só avisa
    fdb.stock.docs.append({"id": "s-refri", "product_id": "p-sem", "unit": "unit", "quantity": 1.0})
    warnings = run(server.validate_stock(_items(("p-sem", 3))))
    assert any("solicitado 3" in w and "negativo" in w for w in warnings)


def test_validate_legacy_direct_stock_zero_only_warns(fdb):
    fdb.stock.docs.append({"id": "s-refri", "product_id": "p-sem", "unit": "unit", "quantity": 0})
    warnings = run(server.validate_stock(_items(("p-sem", 1))))
    assert any("sem estoque" in w for w in warnings)


def test_validate_never_raises_on_db_error(fdb, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(fdb.stock, "find_one", boom)
    assert run(server.validate_stock(_items(("p-lanche", 1)))) == []


# =====================================================================
# 4) CMV: mesmo formato + incomplete / incomplete_reason
# =====================================================================
def _admin():
    return token_for("u-admin")


CMV_KEYS = {"product_id", "product_name", "sale_price", "cost", "profit", "margin",
            "has_recipe", "ingredients_detail", "incomplete", "incomplete_reason"}
REPORT_KEYS = {"product_id", "product_name", "category_id", "sale_price", "cost", "profit",
               "margin", "has_recipe", "incomplete", "incomplete_reason"}
ING_KEYS = {"stock_item_id", "quantity", "unit_cost", "line_cost", "ingredient_name", "unit",
            "recipe_unit", "quantity_in_stock_unit", "incomplete", "incomplete_reason"}


def test_product_cmv_converts_and_keeps_format(fdb):
    status, data = call("GET", "/api/products/p-lanche/cmv", _admin())
    assert status == 200
    assert set(data) == CMV_KEYS
    # 0,150 kg x R$ 40 = 6,00 ; 1 pão x 1,50 = 1,50
    assert data["cost"] == pytest.approx(7.5)
    assert data["profit"] == pytest.approx(22.5)
    assert data["margin"] == pytest.approx(75.0)
    assert data["incomplete"] is False and data["incomplete_reason"] == ""
    carne = data["ingredients_detail"][0]
    assert set(carne) == ING_KEYS
    assert carne["quantity"] == 150 and carne["unit"] == "kg"        # campos de sempre
    assert carne["recipe_unit"] == "gram" and carne["quantity_in_stock_unit"] == pytest.approx(0.15)
    assert carne["line_cost"] == pytest.approx(6.0)
    assert all(isinstance(data[k], float) for k in ("sale_price", "cost", "profit", "margin"))


def test_product_cmv_legacy_recipe_same_value_as_before(fdb):
    _, data = call("GET", "/api/products/p-antigo/cmv", _admin())
    assert data["cost"] == pytest.approx(0.4 * 5.0)


def test_product_without_recipe_is_incomplete(fdb):
    _, data = call("GET", "/api/products/p-sem/cmv", _admin())
    assert data["cost"] == 0.0 and isinstance(data["cost"], float)
    assert data["has_recipe"] is False
    assert data["incomplete"] is True and data["incomplete_reason"] == "sem receita"


def test_cmv_incomplete_when_cost_missing_or_ingredient_missing(fdb):
    next(d for d in fdb.stock.docs if d["id"] == "s-pao")["unit_cost"] = 0
    fdb.recipes.docs[0]["ingredients"].append({"stock_item_id": "s-sumiu", "quantity": 1})
    _, data = call("GET", "/api/products/p-lanche/cmv", _admin())
    assert data["incomplete"] is True
    assert "Pão: insumo sem custo" in data["incomplete_reason"]
    assert "insumo não encontrado" in data["incomplete_reason"]


def test_cmv_report_keeps_format(fdb):
    status, rows = call("GET", "/api/cmv/report", _admin())
    assert status == 200
    assert len(rows) == len(PRODUCTS)
    for r in rows:
        assert set(r) == REPORT_KEYS
    by_id = {r["product_id"]: r for r in rows}
    assert by_id["p-suco"]["cost"] == pytest.approx(0.3 * 6.0)
    assert by_id["p-sem"]["incomplete"] is True


# =====================================================================
# 5) Receita: unidade validada ao salvar; quantidades nunca reescritas
# =====================================================================
def test_create_recipe_normalizes_unit(fdb):
    body = {"product_id": "p-sem", "ingredients": [
        {"stock_item_id": "s-batata", "quantity": 200, "unit": "g"},
        {"stock_item_id": "s-pao", "quantity": 2},
    ]}
    status, data = call("POST", "/api/recipes", _admin(), body)
    assert status == 200
    saved = fdb.recipes.docs[-1]["ingredients"]
    assert saved[0] == {"stock_item_id": "s-batata", "quantity": 200, "unit": "gram"}
    assert saved[1] == {"stock_item_id": "s-pao", "quantity": 2}   # sem unit: intacto
    assert data["total_cost"] == pytest.approx(0.2 * 5 + 2 * 1.5)


@pytest.mark.parametrize("unit,msg", [("ml", "incompatível"), ("xícara", "desconhecida")])
def test_create_recipe_rejects_bad_unit(fdb, unit, msg):
    body = {"product_id": "p-sem", "ingredients": [{"stock_item_id": "s-batata", "quantity": 1, "unit": unit}]}
    status, data = call("POST", "/api/recipes", _admin(), body)
    assert status == 400 and msg in data["detail"]


def test_update_recipe_without_units_keeps_quantities(fdb):
    body = {"ingredients": [{"stock_item_id": "s-batata", "quantity": 0.4}]}
    status, _ = call("PUT", "/api/recipes/r-antigo", _admin(), body)
    assert status == 200
    assert fdb.recipes.docs[2]["ingredients"] == [{"stock_item_id": "s-batata", "quantity": 0.4}]


# =====================================================================
# 6) Falhas visíveis: listar e resolver (só admin)
# =====================================================================
def test_failures_list_and_resolve(fdb):
    fdb.recipes.docs[0]["ingredients"].append({"stock_item_id": "s-sumiu", "quantity": 1})
    run(server.deduct_stock("p-lanche", 1, order_code="o1"))
    status, rows = call("GET", "/api/stock/deduction-failures", _admin())
    assert status == 200 and len(rows) == 1
    fid = rows[0]["id"]
    status, _ = call("POST", f"/api/stock/deduction-failures/{fid}/resolve", _admin())
    assert status == 200
    _, rows = call("GET", "/api/stock/deduction-failures", _admin())
    assert rows == []
    status, _ = call("POST", f"/api/stock/deduction-failures/{fid}/resolve", _admin())
    assert status == 404
    # nova venda depois de resolvida abre uma nova pendência
    run(server.deduct_stock("p-lanche", 1, order_code="o2"))
    _, rows = call("GET", "/api/stock/deduction-failures", _admin())
    assert len(rows) == 1 and rows[0]["occurrences"] == 1


def test_failures_admin_only(fdb):
    status, _ = call("GET", "/api/stock/deduction-failures", token_for("u-waiter"))
    assert status == 403
