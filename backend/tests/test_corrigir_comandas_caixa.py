"""Etapa 2: backend/scripts/corrigir_comandas_caixa.py.

Teste OFFLINE com banco falso que:
  - dá ERRO em qualquer delete/replace/drop;
  - simula transação (escritas só valem no commit; erro descarta tudo);
  - pode simular servidor sem suporte a transação.
Rodar: cd backend && python -m pytest tests/test_corrigir_comandas_caixa.py
"""
import argparse
import copy
import json
import os
import stat
import sys

import pytest
from pymongo.errors import OperationFailure

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import corrigir_comandas_caixa as cc  # noqa: E402

OPENED = "2026-11-02T10:00:00+00:00"
CLOSED = "2026-11-02T12:00:00+00:00"


# ------------------------------------------------------------------ banco falso
def _match(doc, query):
    for k, v in query.items():
        val = doc.get(k)
        if isinstance(v, dict):
            for op, arg in v.items():
                if op == "$gte" and not (val is not None and str(val) >= str(arg)):
                    return False
                if op == "$lte" and not (val is not None and str(val) <= str(arg)):
                    return False
                if op == "$ne" and val == arg:
                    return False
        elif val != v:
            return False
    return True


class _Res:
    def __init__(self, n):
        self.matched_count = self.modified_count = n


class Store:
    def __init__(self, data):
        self.data = data
        self.unsupported = False
        self.writes = []


class Session:
    def __init__(self, store):
        self.store, self.working = store, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def start_transaction(self):
        return Txn(self)


class Txn:
    def __init__(self, s):
        self.s = s

    def __enter__(self):
        self.s.working = copy.deepcopy(self.s.store.data)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.s.store.data = self.s.working
        self.s.working = None
        return False


class Collection:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def _docs(self, session):
        if session is not None:
            if self.store.unsupported:
                raise OperationFailure("Transaction numbers are only allowed on a replica set member or mongos", code=20)
            return session.working[self.name]
        return self.store.data[self.name]

    def find(self, query=None, projection=None, session=None):
        return [copy.deepcopy(d) for d in self._docs(session) if _match(d, query or {})]

    def find_one(self, query=None, projection=None, session=None):
        found = self.find(query, projection, session=session)
        return found[0] if found else None

    def insert_many(self, docs, session=None):
        self.store.writes.append((self.name, "insert_many"))
        self._docs(session).extend(copy.deepcopy(docs))

    def update_one(self, query, update, session=None):
        self.store.writes.append((self.name, "update_one"))
        for d in self._docs(session):
            if _match(d, query):
                d.update(copy.deepcopy(update.get("$set", {})))
                return _Res(1)
        return _Res(0)

    def __getattr__(self, name):
        # delete_one, delete_many, replace_one, drop, find_one_and_delete...
        raise AssertionError(f"operação proibida no banco: {self.name}.{name}")


class DB:
    def __init__(self, store):
        for n in ("orders", "payments", "cash_registers", "users"):
            setattr(self, n, Collection(store, n))


class Client:
    def __init__(self, store):
        self.store = store
        self.closed = False

    def __getitem__(self, name):
        return DB(self.store)

    def start_session(self):
        return Session(self.store)

    def close(self):
        self.closed = True


def _order(oid, total, **kw):
    d = {"id": oid, "total": total, "is_closed": True, "closed_at": CLOSED, "status": "delivered",
         "source": "table", "tab_number": 200 + int(oid[1:]), "customer_name": "NAO-DEVE-APARECER"}
    d.update(kw)
    return d


def _pay(oid, method, amount, at=CLOSED):
    return {"id": f"p-{oid}-{method}-{at}", "order_id": oid, "method": method, "amount": amount, "created_at": at}


@pytest.fixture
def store():
    return Store({
        "cash_registers": [{"id": "reg-1", "is_open": True, "opened_at": OPENED, "total_sales": 200.0}],
        "users": [
            {"id": "adm", "name": "Admin", "email": "adm@example.invalid", "role": "admin", "is_active": True},
            {"id": "sup", "name": "Super", "email": "sup@example.invalid", "role": "superadmin"},
            {"id": "cx", "name": "Caixa", "email": "cx@example.invalid", "role": "cashier", "is_active": True},
            {"id": "adm-off", "name": "Antigo", "email": "off@example.invalid", "role": "admin",
             "is_active": False},
            {"id": "dup1", "name": "Dup 1", "email": "dup@example.invalid", "role": "admin", "is_active": True},
            {"id": "dup2", "name": "Dup 2", "email": "dup@example.invalid", "role": "admin", "is_active": True},
        ],
        "orders": [
            _order("o1", 50.0),   # válida
            _order("o2", 40.0),   # sem pagamento
            _order("o3", 60.0),   # pago menor (pix 30)
            _order("o4", 30.0),   # pix duplicado -> troco sem dinheiro
            _order("o5", 70.0, is_comp=True),
            _order("o6", 10.0, closed_at="2026-11-01T09:00:00+00:00"),  # antes da abertura
        ],
        "payments": [
            _pay("o1", "cash", 50.0),
            _pay("o3", "pix", 30.0),
            _pay("o4", "pix", 30.0), _pay("o4", "pix", 30.0, at="2026-11-02T12:00:02+00:00"),
        ],
    })


@pytest.fixture
def run(store, monkeypatch, tmp_path):
    monkeypatch.setenv("MONGO_URL", "mongodb://teste-offline:1")
    monkeypatch.setenv("DB_NAME", "teste")

    def _run(*args, confirm=cc.CONFIRMACAO):
        argv = list(args) + ["--backup-dir", str(tmp_path)]
        return cc.main(argv, client_factory=lambda *a, **k: Client(store), entrada=lambda _: confirm)
    return _run


def _payments(store, oid):
    return [p for p in store.data["payments"] if p["order_id"] == oid]


# ------------------------------------------------------------------ argumentos
def test_parse_pagamento_ok():
    assert cc.parse_pagamento("o2:pix:40.00") == ("o2", "pix", 4000)
    assert cc.parse_pagamento("ab-12:cash:7,5") == ("ab-12", "cash", 750)


@pytest.mark.parametrize("texto", ["o2:pix", "o2:boleto:10", "o2:pix:0", "o2:pix:-1", "o2:pix:abc",
                                   "o2:pix:1.234", ":pix:10", "o2:pix:NaN", "o2:pix:inf"])
def test_parse_pagamento_invalido(texto):
    with pytest.raises(argparse.ArgumentTypeError):
        cc.parse_pagamento(texto)


def test_operador_e_pagamento_obrigatorios():
    with pytest.raises(SystemExit):
        cc.parse_args(["--pagamento", "o2:pix:40"])
    with pytest.raises(SystemExit):
        cc.parse_args(["--operador", "adm"])


# ------------------------------------------------------------------ dry-run
def test_dry_run_is_default_and_writes_nothing(store, run, tmp_path, capsys):
    before = copy.deepcopy(store.data)
    assert run("--operador", "adm", "--pagamento", "o2:pix:40.00") == 0
    out = capsys.readouterr().out
    assert "SIMULAÇÃO" in out and "DRY-RUN: nada foi gravado" in out
    assert "SEM PAGAMENTO" in out and "CONSISTENTE" in out
    assert store.data == before and store.writes == []
    assert list(tmp_path.iterdir()) == []  # nem backup na simulação


def test_dry_run_shows_total_sales_calculation(run, capsys):
    run("--operador", "adm", "--pagamento", "o2:pix:40.00", "--pagamento", "o3:pix:30.00")
    out = capsys.readouterr().out
    # válidas depois: o1 50 + o2 40 + o3 60 = 150; gravado 200
    assert "R$ 200,00" in out and "R$ 150,00" in out and "R$ -50,00" in out
    assert "NÃO será alterado" in out


def test_no_customer_data_printed(run, capsys):
    run("--operador", "adm", "--pagamento", "o2:pix:40.00")
    out = capsys.readouterr()
    assert "NAO-DEVE-APARECER" not in out.out + out.err


# ------------------------------------------------------------------ gravação
def test_apply_registers_payment_with_audit(store, run, tmp_path):
    assert run("--apply", "--operador", "adm", "--pagamento", "o2:pix:40.00") == 0
    (p,) = _payments(store, "o2")
    assert p["method"] == "pix" and p["amount"] == 40.0
    assert p["created_by_id"] == "adm" and p["register_id"] == "reg-1"
    assert p["justificativa"] == "regularização de inconsistência do caixa"
    assert p["regularizacao"] is True and p["created_at"] > CLOSED
    assert store.data["cash_registers"][0]["total_sales"] == 200.0  # sem flag: não muda


def test_apply_saves_backup_before_writing(store, run, tmp_path):
    original_o3 = copy.deepcopy(store.data["orders"][2])
    run("--apply", "--operador", "adm", "--pagamento", "o3:pix:30.00")
    (arq,) = list(tmp_path.iterdir())
    assert arq.name.startswith("backup_caixa_") and arq.suffix == ".json"
    assert stat.S_IMODE(arq.stat().st_mode) == 0o600
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert dados["cash_register"]["id"] == "reg-1"
    assert dados["orders"] == [original_o3]
    assert len(dados["payments"]["o3"]) == 1  # estado ANTES da correção


def test_apply_several_orders_in_one_transaction(store, run):
    assert run("--apply", "--operador", "adm", "--pagamento", "o2:cash:20", "--pagamento", "o2:pix:20",
               "--pagamento", "o3:debit:30") == 0
    assert len(_payments(store, "o2")) == 2 and len(_payments(store, "o3")) == 2


def test_corrigir_total_sales_only_with_flag(store, run):
    run("--apply", "--corrigir-total-sales", "--operador", "adm",
        "--pagamento", "o2:pix:40", "--pagamento", "o3:pix:30")
    assert store.data["cash_registers"][0]["total_sales"] == 150.0


def test_corrigir_total_sales_without_apply_does_nothing(store, run):
    before = copy.deepcopy(store.data)
    run("--corrigir-total-sales", "--operador", "adm", "--pagamento", "o2:pix:40")
    assert store.data == before


def test_wrong_confirmation_writes_nothing(store, run, tmp_path):
    before = copy.deepcopy(store.data)
    assert run("--apply", "--operador", "adm", "--pagamento", "o2:pix:40", confirm="sim") == 1
    assert store.data == before and list(tmp_path.iterdir()) == []


def test_transaction_unsupported_writes_nothing(store, run, capsys):
    store.unsupported = True
    before = copy.deepcopy(store.data)
    assert run("--apply", "--operador", "adm", "--pagamento", "o2:pix:40") == 1
    assert "não aceita transações" in capsys.readouterr().err
    assert store.data == before


def test_change_between_plan_and_apply_is_refused(store, run, monkeypatch):
    real = cc.aplicar

    def mudou_no_meio(client, db, plano, corrigir):
        store.data["payments"].append(_pay("o2", "cash", 1.0))  # alguém mexeu
        return real(client, db, plano, corrigir)

    monkeypatch.setattr(cc, "aplicar", mudou_no_meio)
    assert run("--apply", "--operador", "adm", "--pagamento", "o2:pix:40") == 1
    assert len(_payments(store, "o2")) == 1  # só o que "alguém" pôs; o script não gravou


# ------------------------------------------------------------------ recusas
@pytest.mark.parametrize("args,trecho", [
    (["--pagamento", "o1:pix:10"], "já está consistente"),
    (["--pagamento", "o3:pix:10"], "continuaria inconsistente"),       # ainda falta
    (["--pagamento", "o4:cash:10"], "continuaria inconsistente"),      # pix duplicado não se resolve somando
    (["--pagamento", "o5:pix:70"], "cortesia"),
    (["--pagamento", "o6:pix:10"], "antes da abertura"),
    (["--pagamento", "nao-existe:pix:10"], "não encontrada"),
])
def test_refusals_write_nothing(store, run, capsys, args, trecho):
    before = copy.deepcopy(store.data)
    assert run("--apply", "--operador", "adm", *args) == 1
    assert trecho in capsys.readouterr().err
    assert store.data == before


@pytest.mark.parametrize("operador,trecho", [
    ("cx", "papel admin ou superadmin"),
    ("adm-off", "desativado"),
    ("ninguem", "não encontrado"),
    ("cx@example.invalid", "papel admin ou superadmin"),
    ("off@example.invalid", "desativado"),
    ("nao-existe@example.invalid", "não encontrado"),
    ("ADM@example.invalid", "não encontrado"),   # e-mail comparado exatamente
    ("dup@example.invalid", "2 contas"),
])
def test_operador_must_be_unique_active_admin(store, run, capsys, operador, trecho):
    before = copy.deepcopy(store.data)
    assert run("--apply", "--operador", operador, "--pagamento", "o2:pix:40") == 1
    assert trecho in capsys.readouterr().err
    assert store.data == before


@pytest.mark.parametrize("operador,esperado", [
    ("adm@example.invalid", "adm"), ("sup@example.invalid", "sup"), ("adm", "adm"),
    ("  adm@example.invalid  ", "adm"),
])
def test_operador_by_email_or_id(store, run, operador, esperado):
    assert run("--apply", "--operador", operador, "--pagamento", "o2:pix:40.00") == 0
    (p,) = _payments(store, "o2")
    assert p["created_by_id"] == esperado  # grava o id, mesmo quando informado o e-mail


def test_dry_run_shows_operador_email(run, capsys):
    run("--operador", "adm@example.invalid", "--pagamento", "o2:pix:40.00")
    assert "Admin <adm@example.invalid> (admin, id adm)" in capsys.readouterr().out


def test_no_open_register(store, run, capsys):
    store.data["cash_registers"][0]["is_open"] = False
    assert run("--operador", "adm", "--pagamento", "o2:pix:40") == 1
    assert "Nenhum caixa aberto" in capsys.readouterr().err


def test_one_bad_item_refuses_all(store, run):
    before = copy.deepcopy(store.data)
    assert run("--apply", "--operador", "adm", "--pagamento", "o2:pix:40", "--pagamento", "o1:pix:5") == 1
    assert store.data == before


def test_duplicated_pix_is_listed_not_removed(store, run, capsys):
    # o4 não se corrige somando pagamento; mas o duplicado nunca é apagado.
    run("--apply", "--operador", "adm", "--pagamento", "o4:cash:10")
    assert len(_payments(store, "o4")) == 2


def test_backup_dir_inside_repo_refused(store, monkeypatch, capsys):
    monkeypatch.setenv("MONGO_URL", "mongodb://teste-offline:1")
    monkeypatch.setenv("DB_NAME", "teste")
    before = copy.deepcopy(store.data)
    rc = cc.main(["--apply", "--operador", "adm", "--pagamento", "o2:pix:40",
                  "--backup-dir", str(cc.REPO_ROOT / "backend")],
                 client_factory=lambda *a, **k: Client(store), entrada=lambda _: cc.CONFIRMACAO)
    assert rc == 1 and "dentro do repositório" in capsys.readouterr().err
    assert store.data == before


def test_missing_env_does_not_connect(monkeypatch, capsys):
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    def nao_conecte(*a, **k):
        raise AssertionError("conectou")

    assert cc.main(["--operador", "adm", "--pagamento", "o2:pix:40"], client_factory=nao_conecte) == 2
    assert "MONGO_URL" in capsys.readouterr().err
