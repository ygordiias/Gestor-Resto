"""/reports/sales e /reports/profit: cancelado, teste e "Não recebido" não contam como venda.

Teste OFFLINE: captura os pipelines enviados ao banco e confere os filtros
contra documentos de exemplo (o banco falso não executa aggregate).
Rodar: cd backend && python -m pytest tests/test_reports_sales.py
"""
from _fake_mongo import FakeDB, match
from _offline_app import call, server, token_for

ADMIN = {"id": "u-admin", "name": "Admin", "email": "a@x", "role": "admin", "is_active": True}

DOCS = [
    {"is_closed": True, "closed_at": "2999-01-01", "total": 50, "status": "delivered"},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 52, "status": "cancelled"},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 49, "status": "delivered", "is_test": True},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 40, "status": "delivered",
     "payment_status": "not_received"},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 30, "status": "delivered", "is_comp": True},
]


def _capture(monkeypatch, path):
    db = FakeDB()
    db.users.docs.append(dict(ADMIN))
    pipelines = []

    class Agg:
        def __init__(self, p):
            pipelines.append(p)

        async def to_list(self, n):
            return []

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(db.orders, "aggregate", lambda p: Agg(p), raising=False)
    assert call("GET", path, token=token_for(ADMIN["id"]))[0] == 200
    return pipelines


def test_sales_report_ignores_cancelled(monkeypatch):
    pipelines = _capture(monkeypatch, "/api/reports/sales")
    assert len(pipelines) == 2
    for p in pipelines:
        assert [d["total"] for d in DOCS if match(d, p[0]["$match"])] == [50]

    # linhas de item canceladas (cancelamento parcial) também saem do ranking de produtos
    stages = pipelines[1]
    unwind = next(i for i, st in enumerate(stages) if "$unwind" in st)
    item_match = stages[unwind + 1]["$match"]
    assert not match({"items": {"status": "cancelled"}}, item_match)
    assert match({"items": {"status": "delivered"}}, item_match)


def test_profit_report_ignores_cancelled(monkeypatch):
    pipelines = _capture(monkeypatch, "/api/reports/profit")
    # cortesia continua contando no lucro, como antes; só cancelado/teste/não recebido saem
    assert [d["total"] for d in DOCS if match(d, pipelines[0][0]["$match"])] == [50, 30]
