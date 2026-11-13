"""Etapa 2: backend/scripts/ajustar_excesso_pagamento.py.

Teste OFFLINE. Reaproveita o banco falso de test_corrigir_comandas_caixa.py:
dá ERRO em qualquer delete/replace/drop e simula transação.
Rodar: cd backend && python -m pytest tests/test_ajustar_excesso_pagamento.py
"""
import copy
import json
import os
import stat
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import ajustar_excesso_pagamento as aj  # noqa: E402
import diagnostico_caixa as diag  # noqa: E402
from test_corrigir_comandas_caixa import CLOSED, OPENED, Client, Store  # noqa: E402

T2 = "2026-11-02T12:00:02+00:00"


def _order(oid, total, **kw):
    d = {"id": oid, "total": total, "is_closed": True, "closed_at": CLOSED, "status": "delivered",
         "source": "table", "tab_number": 200 + int(oid[1:]), "customer_name": "NAO-DEVE-APARECER"}
    d.update(kw)
    return d


def _pay(pid, oid, method, amount, at=CLOSED, **kw):
    d = {"_id": pid, "id": pid, "order_id": oid, "method": method, "amount": amount, "created_at": at}
    d.update(kw)
    return d


@pytest.fixture
def store():
    return Store({
        "cash_registers": [{"id": "reg-1", "is_open": True, "opened_at": OPENED, "total_sales": 300.0}],
        "users": [
            {"id": "adm", "name": "Admin", "email": "adm@example.invalid", "role": "admin", "is_active": True},
            {"id": "cx", "name": "Caixa", "email": "cx@example.invalid", "role": "cashier", "is_active": True},
        ],
        "orders": [
            _order("o1", 30.0),   # pix duplicado: 30 + 30
            _order("o2", 45.0),   # cartão a mais: debit 20 + credit 40 (excesso 15)
            _order("o3", 20.0),   # excesso maior que o último: pix 50 + debit 5 (excesso 35)
            _order("o4", 25.0),   # tem dinheiro: cash 10 + pix 30
            _order("o5", 40.0),   # consistente
            _order("o6", 60.0),   # pago menor (não é excesso)
            _order("o7", 10.0, is_comp=True),
            _order("o8", 10.0, status="cancelled"),
            _order("o9", 10.0, source="online"),
            _order("o10", 10.0, closed_at="2026-11-01T09:00:00+00:00"),
            _order("o11", 10.0),  # último já ajustado antes
        ],
        "payments": [
            _pay("p1a", "o1", "pix", 30.0), _pay("p1b", "o1", "pix", 30.0, at=T2),
            _pay("p2a", "o2", "debit", 20.0), _pay("p2b", "o2", "credit", 40.0, at=T2),
            _pay("p3a", "o3", "pix", 50.0), _pay("p3b", "o3", "debit", 5.0, at=T2),
            _pay("p4a", "o4", "cash", 10.0), _pay("p4b", "o4", "pix", 30.0, at=T2),
            _pay("p5a", "o5", "pix", 40.0),
            _pay("p6a", "o6", "pix", 30.0),
            _pay("p11a", "o11", "pix", 20.0, amount_original=25.0, justificativa="x"),
        ],
    })


@pytest.fixture
def run(store, monkeypatch, tmp_path):
    monkeypatch.setenv("MONGO_URL", "mongodb://teste-offline:1")
    monkeypatch.setenv("DB_NAME", "teste")

    def _run(*args, confirm=aj.CONFIRMACAO):
        argv = list(args) + ["--backup-dir", str(tmp_path)]
        return aj.main(argv, client_factory=lambda *a, **k: Client(store), entrada=lambda _: confirm)
    return _run


def _p(store, pid):
    return next(p for p in store.data["payments"] if p["_id"] == pid)


def _consistente(store, oid):
    order = next(o for o in store.data["orders"] if o["id"] == oid)
    pays = [p for p in store.data["payments"] if p["order_id"] == oid]
    return diag.analisar(order, pays)[0] == []


OP = ("--operador", "adm@example.invalid")


# ------------------------------------------------------------------ dry-run
def test_dry_run_default_writes_nothing(store, run, tmp_path, capsys):
    before = copy.deepcopy(store.data)
    assert run(*OP, "--ajustar", "o1", "--ajustar", "o2") == 0
    out = capsys.readouterr().out
    assert "SIMULAÇÃO" in out and "DRY-RUN: nada foi gravado" in out
    assert store.data == before and store.writes == []
    assert list(tmp_path.iterdir()) == []


def test_dry_run_shows_before_after(run, capsys):
    run(*OP, "--ajustar", "o2")
    out = capsys.readouterr().out
    assert "excesso: R$ 15,00" in out
    linhas = [" ".join(l.split()) for l in out.splitlines()]
    assert any(l.startswith("debit R$ 20,00 -> R$ 20,00") and "AJUSTADO" not in l for l in linhas)
    assert any(l.startswith("credit R$ 40,00 -> R$ 25,00") and l.endswith("<- AJUSTADO") for l in linhas)
    assert "pago R$ 45,00 = total R$ 45,00 -> CONSISTENTE" in out


def test_dry_run_flags_zeroed_duplicate(run, capsys):
    run(*OP, "--ajustar", "o1")
    assert "fica R$ 0,00: provável duplicado" in capsys.readouterr().out


def test_no_customer_data_printed(run, capsys):
    run(*OP, "--ajustar", "o1")
    out = capsys.readouterr()
    assert "NAO-DEVE-APARECER" not in out.out + out.err


# ------------------------------------------------------------------ gravação
def test_apply_adjusts_last_non_cash_with_trace(store, run):
    assert run("--apply", *OP, "--ajustar", "o2") == 0
    p = _p(store, "p2b")
    assert p["amount"] == 25.0 and p["amount_original"] == 40.0
    assert p["amount_ajustado_por_id"] == "adm" and p["amount_ajustado_em"] > CLOSED
    assert "sem dinheiro para troco" in p["justificativa"]
    assert _p(store, "p2a")["amount"] == 20.0 and "amount_original" not in _p(store, "p2a")
    assert _consistente(store, "o2")


def test_apply_duplicate_pix_becomes_zero_not_deleted(store, run):
    assert run("--apply", *OP, "--ajustar", "o1") == 0
    assert len([p for p in store.data["payments"] if p["order_id"] == "o1"]) == 2
    assert _p(store, "p1b")["amount"] == 0.0 and _p(store, "p1b")["amount_original"] == 30.0
    assert _p(store, "p1a")["amount"] == 30.0
    assert _consistente(store, "o1")


def test_apply_several_in_one_transaction(store, run):
    assert run("--apply", *OP, "--ajustar", "o1", "--ajustar", "o2") == 0
    assert _consistente(store, "o1") and _consistente(store, "o2")


def test_apply_does_not_touch_total_sales_or_orders(store, run):
    before_orders = copy.deepcopy(store.data["orders"])
    run("--apply", *OP, "--ajustar", "o1")
    assert store.data["cash_registers"][0]["total_sales"] == 300.0
    assert store.data["orders"] == before_orders


def test_apply_saves_backup_first(store, run, tmp_path):
    run("--apply", *OP, "--ajustar", "o2")
    (arq,) = list(tmp_path.iterdir())
    assert arq.name.startswith("backup_ajuste_") and arq.suffix == ".json"
    assert stat.S_IMODE(arq.stat().st_mode) == 0o600
    dados = json.loads(arq.read_text(encoding="utf-8"))
    credit = next(p for p in dados["payments"]["o2"] if p["_id"] == "p2b")
    assert credit["amount"] == 40.0 and "amount_original" not in credit  # estado ANTES


def test_wrong_confirmation_writes_nothing(store, run, tmp_path):
    before = copy.deepcopy(store.data)
    assert run("--apply", *OP, "--ajustar", "o1", confirm="sim") == 1
    assert store.data == before and list(tmp_path.iterdir()) == []


def test_transaction_unsupported_writes_nothing(store, run, capsys):
    store.unsupported = True
    before = copy.deepcopy(store.data)
    assert run("--apply", *OP, "--ajustar", "o1") == 1
    assert "não aceita transações" in capsys.readouterr().err
    assert store.data == before


def test_change_between_plan_and_apply_is_refused(store, run, monkeypatch):
    real = aj.aplicar

    def mudou(client, db, plano):
        _p(store, "p2a")["amount"] = 21.0  # alguém mexeu
        return real(client, db, plano)

    monkeypatch.setattr(aj, "aplicar", mudou)
    assert run("--apply", *OP, "--ajustar", "o2") == 1
    assert _p(store, "p2b")["amount"] == 40.0 and "amount_original" not in _p(store, "p2b")


# ------------------------------------------------------------------ recusas
@pytest.mark.parametrize("oid,trecho", [
    ("o3", "maior que o último pagamento"),
    ("o4", "dinheiro"),
    ("o5", "já está consistente"),
    ("o6", "não é maior que o total"),
    ("o7", "cortesia"),
    ("o8", "cancelada"),
    ("o9", "online"),
    ("o10", "antes da abertura"),
    ("o11", "já tem ajuste"),
    ("nao-existe", "não encontrada"),
])
def test_refusals_write_nothing(store, run, capsys, oid, trecho):
    before = copy.deepcopy(store.data)
    assert run("--apply", *OP, "--ajustar", oid) == 1
    assert trecho in capsys.readouterr().err
    assert store.data == before


def test_one_bad_refuses_all(store, run):
    before = copy.deepcopy(store.data)
    assert run("--apply", *OP, "--ajustar", "o1", "--ajustar", "o4") == 1
    assert store.data == before


def test_same_order_twice_refused(store, run, capsys):
    assert run(*OP, "--ajustar", "o1", "--ajustar", "o1") == 1
    assert "mais de uma vez" in capsys.readouterr().err


@pytest.mark.parametrize("operador", ["cx@example.invalid", "ninguem@example.invalid"])
def test_operador_must_be_admin(store, run, operador):
    before = copy.deepcopy(store.data)
    assert run("--apply", "--operador", operador, "--ajustar", "o1") == 1
    assert store.data == before


def test_second_run_refused_after_adjust(store, run, capsys):
    assert run("--apply", *OP, "--ajustar", "o1") == 0
    assert run("--apply", *OP, "--ajustar", "o1") == 1
    assert "já está consistente" in capsys.readouterr().err


def test_backup_dir_inside_repo_refused(store, monkeypatch, capsys):
    monkeypatch.setenv("MONGO_URL", "mongodb://teste-offline:1")
    monkeypatch.setenv("DB_NAME", "teste")
    before = copy.deepcopy(store.data)
    rc = aj.main(["--apply", *OP, "--ajustar", "o1", "--backup-dir", str(aj.REPO_ROOT / "backend")],
                 client_factory=lambda *a, **k: Client(store), entrada=lambda _: aj.CONFIRMACAO)
    assert rc == 1 and "dentro do repositório" in capsys.readouterr().err
    assert store.data == before


def test_missing_env_does_not_connect(monkeypatch, capsys):
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    def nao_conecte(*a, **k):
        raise AssertionError("conectou")

    assert aj.main([*OP, "--ajustar", "o1"], client_factory=nao_conecte) == 2
    assert "MONGO_URL" in capsys.readouterr().err
