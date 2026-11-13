"""Etapa 2: backend/scripts/diagnostico_caixa.py é somente leitura e aplica
as mesmas regras do fechamento do caixa.

Teste OFFLINE com banco falso que FALHA em qualquer tentativa de escrita.
Rodar: cd backend && python -m pytest tests/test_diagnostico_caixa.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import diagnostico_caixa as diag  # noqa: E402

OPENED = "2026-11-02T10:00:00+00:00"


class _Cursor(list):
    def sort(self, key, direction=1):
        return _Cursor(sorted(self, key=lambda d: str(d.get(key, "")), reverse=direction < 0))


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            val = doc.get(k)
            for op, arg in v.items():
                if op == "$gte" and not (val is not None and str(val) >= str(arg)):
                    return False
                if op == "$lte" and not (val is not None and str(val) <= str(arg)):
                    return False
                if op == "$ne" and val == arg:
                    return False
        elif doc.get(k) != v:
            return False
    return True


class ReadOnlyCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query=None, projection=None):
        return _Cursor(dict(d) for d in self.docs if _match(d, query or {}))

    def find_one(self, query=None, projection=None):
        found = self.find(query)
        return found[0] if found else None

    def count_documents(self, query):
        return len(self.find(query))

    def __getattr__(self, name):
        raise AssertionError(f"tentativa de escrita/método não permitido: {name}")


class FakeDB:
    def __init__(self, registers, orders, payments):
        self.cash_registers = ReadOnlyCollection(registers)
        self.orders = ReadOnlyCollection(orders)
        self.payments = ReadOnlyCollection(payments)


def _order(oid, total, **kw):
    base = {"id": oid, "total": total, "is_closed": True, "closed_at": "2026-11-02T12:00:00+00:00",
            "status": "delivered", "tab_number": int(oid[-1]) + 200 if oid[-1].isdigit() else None,
            "customer_name": "NAO-DEVE-APARECER", "customer_phone": "NAO-DEVE-APARECER"}
    base.update(kw)
    return base


def _pay(oid, method, amount, at="2026-11-02T12:00:00+00:00"):
    return {"order_id": oid, "method": method, "amount": amount, "created_at": at}


@pytest.fixture
def db():
    orders = [
        _order("o1", 50.0),                         # válida
        _order("o2", 40.0),                         # sem pagamento
        _order("o3", 60.0),                         # pago menor
        _order("o4", 30.0),                         # troco > dinheiro (pix 50 p/ total 30)
        _order("o5", 20.0),                         # método inválido
        _order("o6", 10.0, status="cancelled"),     # ignorada
        _order("o7", 15.0, is_comp=True),           # ignorada
        _order("o8", 25.0, source="online"),        # ignorada
        _order("o9", 99.0, closed_at="2026-11-01T09:00:00+00:00"),  # antes da abertura
    ]
    payments = [
        _pay("o1", "cash", 50.0),
        _pay("o3", "pix", 30.0),
        _pay("o4", "pix", 50.0),
        _pay("o5", "boleto", 20.0),
        _pay("o1", "cash", 50.0, at="2026-11-02T12:00:03+00:00"),  # duplicado
    ]
    reg = [{"id": "reg-1", "is_open": True, "opened_at": OPENED, "opened_by": "Operador", "total_sales": 250.0}]
    return FakeDB(reg, orders, payments)


def test_report_lists_exactly_the_inconsistent_orders(db, capsys):
    assert diag.relatorio(db) == 0
    out = capsys.readouterr().out
    assert "INCONSISTENTES 4" in out
    for oid in ("o2", "o3", "o4", "o5"):
        assert f"order_id:    {oid}" in out
    for oid in ("o1", "o6", "o7", "o8", "o9"):
        assert f"order_id:    {oid}" not in out
    assert "SEM PAGAMENTO" in out
    assert "PAGAMENTO MENOR QUE O TOTAL" in out
    assert "TROCO" in out
    assert "FORMA DE PAGAMENTO INVÁLIDA: boleto" in out
    assert "Nada foi alterado no banco." in out


def test_duplicate_on_valid_order_is_warned_not_blocking(db, capsys):
    diag.relatorio(db)
    out = capsys.readouterr().out
    assert "aviso: comanda 201  order_id=o1" in out
    assert "INCONSISTENTES 4" in out


def test_no_customer_data_printed(db, capsys):
    diag.relatorio(db)
    assert "NAO-DEVE-APARECER" not in capsys.readouterr().out


def test_duplicate_payment_detected():
    pays = [_pay("x", "cash", 10.0), _pay("x", "cash", 10.0, at="2026-11-02T12:00:05+00:00")]
    assert diag.possiveis_duplicados(pays) == 1


def test_no_open_register(capsys):
    assert diag.relatorio(FakeDB([], [], [])) == 0
    assert "Nenhum caixa aberto" in capsys.readouterr().out


def test_missing_env_does_not_connect(monkeypatch, capsys):
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.setattr(diag, "MongoClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("conectou")))
    assert diag.main() == 2
    assert "MONGO_URL" in capsys.readouterr().err
