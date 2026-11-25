"""GET /api/reports/sales-by-table: cancelado, teste e "Não recebido" não contam.

Teste OFFLINE: captura o pipeline enviado ao banco e confere o filtro contra
documentos de exemplo (o banco falso não executa aggregate).
Rodar: cd backend && python -m pytest tests/test_sales_by_table.py
"""
from _fake_mongo import FakeDB, match
from _offline_app import call, server, token_for

CAIXA = {"id": "u-caixa", "name": "Caixa", "email": "c@x", "role": "cashier", "is_active": True}

DOCS = [
    {"is_closed": True, "closed_at": "2999-01-01", "total": 50, "status": "delivered"},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 52, "status": "cancelled"},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 49, "status": "delivered", "is_test": True},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 40, "status": "delivered",
     "payment_status": "not_received"},
    {"is_closed": True, "closed_at": "2999-01-01", "total": 30, "status": "delivered", "is_comp": True},
    {"is_closed": False, "closed_at": None, "total": 20, "status": "pending"},
    {"is_closed": True, "closed_at": "2000-01-01", "total": 10, "status": "delivered"},
]


def test_sales_by_table_ignora_cancelado_teste_e_nao_recebido(monkeypatch):
    db = FakeDB()
    db.users.docs.append(dict(CAIXA))
    pipelines = []

    class Agg:
        def __init__(self, pipeline):
            pipelines.append(pipeline)

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(db.orders, "aggregate", lambda p: Agg(p), raising=False)

    status, body = call("GET", "/api/reports/sales-by-table", token=token_for(CAIXA["id"]))
    assert status == 200 and body["rows"] == []
    assert len(pipelines) == 1
    # Fica: venda normal e cortesia (que o relatório separa em comp_total).
    assert [d["total"] for d in DOCS if match(d, pipelines[0][0]["$match"])] == [50, 30]


def test_mesmo_filtro_de_venda_sem_a_cortesia():
    from datetime import datetime, timezone
    base = server._sold_orders_match(datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert base == {"is_closed": True, "closed_at": {"$gte": "2026-11-24T00:00:00+00:00"},
                    "is_comp": {"$ne": True}, "status": {"$ne": "cancelled"},
                    "is_test": {"$ne": True}, "payment_status": {"$ne": "not_received"}}
