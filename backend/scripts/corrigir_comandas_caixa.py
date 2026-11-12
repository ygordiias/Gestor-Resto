#!/usr/bin/env python3
"""Regulariza comandas que travam o fechamento do caixa aberto.

SIMULAÇÃO (--dry-run) É O PADRÃO: sem --apply, nada é gravado.

O que faz, para cada --pagamento ORDER_ID:METODO:VALOR informado:
  - confere que a comanda é presencial, fechada, não cancelada, não cortesia
    e pertence ao caixa aberto;
  - confere que ela está INCONSISTENTE hoje (mesmas regras do fechamento do
    caixa) e que fica CONSISTENTE depois do pagamento informado;
  - registra o pagamento que faltou com autoria (--operador: e-mail ou id de
    um admin/superadmin ativo), caixa aberto, data real e justificativa fixa.

Regras de segurança:
  - Não apaga nada. Não altera nenhum pagamento existente.
  - Pagamento duplicado em pix/cartão: só é listado, nunca removido.
  - total_sales do caixa: o cálculo é sempre mostrado; só é alterado com
    --corrigir-total-sales junto com --apply.
  - Antes de gravar, salva o estado atual das comandas, dos pagamentos delas
    e do caixa em ~/backup_caixa_AAAAMMDD_HHMM.json (fora do repositório).
  - Grava tudo numa transação: ou entra tudo, ou nada. Sem suporte a
    transação, para sem gravar.
  - Pede confirmação digitada antes de gravar.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê .env).
Não imprime dados de clientes.

Uso:
    # simulação (padrão)
    python3 backend/scripts/corrigir_comandas_caixa.py \\
        --operador admin@exemplo.com --pagamento <ORDER_ID>:pix:40.00
    # gravar de verdade
    python3 backend/scripts/corrigir_comandas_caixa.py --apply \\
        --operador admin@exemplo.com --pagamento <ORDER_ID>:pix:40.00
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from diagnostico_caixa import METODOS_VALIDOS, analisar, brl, cents, identificar, possiveis_duplicados

JUSTIFICATIVA = "regularização de inconsistência do caixa"
CONFIRMACAO = "CONFIRMO"
REPO_ROOT = Path(__file__).resolve().parents[2]
PAPEIS_OPERADOR = {"admin", "superadmin"}


class Recusa(Exception):
    """Pedido de correção recusado: nada será gravado."""


# --------------------------------------------------------------------------
# Argumentos
# --------------------------------------------------------------------------
def parse_pagamento(texto):
    """'ORDER_ID:METODO:VALOR' -> (order_id, metodo, centavos)."""
    partes = texto.rsplit(":", 2)
    if len(partes) != 3 or not all(p.strip() for p in partes):
        raise argparse.ArgumentTypeError(f"formato inválido '{texto}' (use ORDER_ID:METODO:VALOR)")
    order_id, metodo, valor = (p.strip() for p in partes)
    if metodo not in METODOS_VALIDOS:
        raise argparse.ArgumentTypeError(
            f"forma de pagamento inválida '{metodo}' (use: {', '.join(sorted(METODOS_VALIDOS))})")
    try:
        dec = Decimal(valor.replace(",", "."))
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"valor inválido '{valor}'")
    if not dec.is_finite() or dec <= 0 or dec.as_tuple().exponent < -2:
        raise argparse.ArgumentTypeError(f"valor inválido '{valor}' (maior que zero, até 2 casas)")
    return order_id, metodo, int(dec * 100)


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Regulariza comandas inconsistentes do caixa aberto (dry-run por padrão).")
    ap.add_argument("--pagamento", action="append", type=parse_pagamento, required=True,
                    metavar="ORDER_ID:METODO:VALOR",
                    help="pagamento a registrar; repita para várias comandas ou formas")
    ap.add_argument("--operador", required=True,
                    help="e-mail (ou id) do admin/superadmin ativo responsável pela correção")
    ap.add_argument("--apply", action="store_true", help="grava de verdade (sem isto, só simula)")
    ap.add_argument("--corrigir-total-sales", action="store_true",
                    help="com --apply, ajusta total_sales do caixa para o valor calculado mostrado")
    ap.add_argument("--backup-dir", default=str(Path.home()),
                    help="pasta do backup (padrão: sua pasta pessoal; nunca dentro do repositório)")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------
# Planejamento (somente leitura)
# --------------------------------------------------------------------------
def _pagamentos_da_comanda(db, order_id, session=None):
    pays = db.payments.find({"order_id": order_id},
                            {"_id": 0, "method": 1, "amount": 1, "created_at": 1},
                            session=session)
    # Ordem estável: a conferência dentro da transação compara listas.
    return sorted(({"method": p.get("method"), "amount": p.get("amount"), "created_at": p.get("created_at")}
                   for p in pays),
                  key=lambda p: (str(p["created_at"]), str(p["method"]), str(p["amount"])))


def _ordem_conferencia(order):
    return {k: order.get(k) for k in ("id", "tab_number", "table_number", "total", "closed_at",
                                      "status", "is_closed", "is_comp", "source")}


def buscar_operador(db, identificacao):
    """Aceita o e-mail (contém "@") ou o id. Exige conta única, ativa e
    com papel admin ou superadmin. O e-mail é comparado exatamente como
    está gravado (a normalização de e-mail ainda é pendência do projeto)."""
    campos = {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "is_active": 1}
    chave = "email" if "@" in identificacao else "id"
    encontrados = list(db.users.find({chave: identificacao.strip()}, campos))
    if not encontrados:
        raise Recusa(f"Operador não encontrado ({chave} informado).")
    if len(encontrados) > 1:
        raise Recusa(f"Há {len(encontrados)} contas com esse {chave}; use o id do usuário.")
    operador = encontrados[0]
    if operador.get("is_active", True) is False:
        raise Recusa("Operador está desativado.")
    if operador.get("role") not in PAPEIS_OPERADOR:
        raise Recusa("Operador precisa ter papel admin ou superadmin.")
    return operador


def planejar(db, pedidos, operador_id):
    """Valida tudo e devolve o plano. Levanta Recusa se qualquer item falhar."""
    register = db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if not register:
        raise Recusa("Nenhum caixa aberto.")

    operador = buscar_operador(db, operador_id)

    por_comanda = {}
    for order_id, metodo, valor in pedidos:
        por_comanda.setdefault(order_id, []).append({"method": metodo, "amount_cents": valor})

    itens = []
    for order_id, novos in por_comanda.items():
        order = db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise Recusa(f"{order_id}: comanda não encontrada.")
        if not order.get("is_closed"):
            raise Recusa(f"{order_id}: comanda ainda aberta (feche pelo Caixa).")
        if order.get("status") == "cancelled" or order.get("is_comp") or order.get("source") == "online":
            raise Recusa(f"{order_id}: cancelada, cortesia ou online não entram na conferência do caixa.")
        if str(order.get("closed_at") or "") < str(register["opened_at"]):
            raise Recusa(f"{order_id}: fechada antes da abertura do caixa atual.")

        atuais = _pagamentos_da_comanda(db, order_id)
        motivos_antes, n_antes = analisar(order, atuais)
        if not motivos_antes:
            raise Recusa(f"{order_id}: comanda já está consistente; nenhum pagamento será adicionado.")

        simulados = atuais + [{"method": p["method"], "amount": p["amount_cents"] / 100} for p in novos]
        motivos_depois, n_depois = analisar(order, simulados)
        if motivos_depois:
            raise Recusa(
                f"{order_id}: com os pagamentos informados continuaria inconsistente "
                f"({' | '.join(motivos_depois)}). Este script só registra pagamento que faltou; "
                "troco sem dinheiro ou forma inválida precisam de outra correção.")

        itens.append({
            "order": order, "atuais": atuais, "novos": novos,
            "motivos_antes": motivos_antes, "n_antes": n_antes, "n_depois": n_depois,
            "duplicados": possiveis_duplicados(atuais),
        })

    calculo = calcular_total_sales(db, register, {i["order"]["id"]: i for i in itens})
    return {"register": register, "operador": operador, "itens": itens, "total_sales": calculo}


def calcular_total_sales(db, register, corrigidas):
    """Soma das comandas válidas depois da correção (mesmas regras do caixa)."""
    agora = datetime.now(timezone.utc).isoformat()
    soma = 0
    for order in db.orders.find({"is_closed": True, "closed_at": {"$gte": register["opened_at"], "$lte": agora}},
                                {"_id": 0}):
        if order.get("status") == "cancelled" or order.get("is_comp") or order.get("source") == "online":
            continue
        pays = _pagamentos_da_comanda(db, order["id"])
        if order["id"] in corrigidas:
            pays = pays + [{"method": p["method"], "amount": p["amount_cents"] / 100}
                           for p in corrigidas[order["id"]]["novos"]]
        motivos, n = analisar(order, pays)
        if not motivos:
            soma += n["total"]
    gravado = cents(register.get("total_sales"))
    return {"gravado": gravado, "calculado": soma, "diferenca": soma - gravado}


def imprimir_plano(plano, apply, corrigir_total):
    reg = plano["register"]
    print(f"=== {'GRAVAÇÃO' if apply else 'SIMULAÇÃO (dry-run): nada será gravado'} ===")
    print(f"caixa aberto: {reg.get('id')}  (aberto em {reg.get('opened_at')} UTC)")
    op = plano["operador"]
    print(f"operador:     {op.get('name')} <{op.get('email')}> ({op.get('role')}, id {op.get('id')})")
    print(f"justificativa: {JUSTIFICATIVA}")
    print()
    for i, item in enumerate(plano["itens"], 1):
        o = item["order"]
        print(f"--- [{i}] {identificar(o)}  order_id={o['id']} ---")
        print(f"hoje:    {' | '.join(item['motivos_antes'])}")
        print(f"         total {brl(item['n_antes']['total'])}, pago {brl(item['n_antes']['pago'])}")
        for p in item["novos"]:
            print(f"incluir: {p['method']:<8} {brl(p['amount_cents']):>14}")
        print(f"depois:  pago {brl(item['n_depois']['pago'])}, troco {brl(max(item['n_depois']['troco'], 0))} -> CONSISTENTE")
        if item["duplicados"]:
            print(f"aviso:   {item['duplicados']} pagamento(s) repetido(s) já existentes. NÃO serão removidos.")
        print()
    c = plano["total_sales"]
    print("=== total_sales do caixa ===")
    print(f"gravado hoje:                         {brl(c['gravado'])}")
    print(f"soma das comandas válidas (depois):   {brl(c['calculado'])}")
    print(f"diferença (calculado - gravado):      {brl(c['diferenca'])}")
    if c["diferenca"] == 0:
        print("total_sales já confere; não será alterado.")
    elif apply and corrigir_total:
        print(f"total_sales SERÁ ajustado de {brl(c['gravado'])} para {brl(c['calculado'])}.")
    else:
        print("total_sales NÃO será alterado (use --corrigir-total-sales com --apply para ajustar).")
    print()


# --------------------------------------------------------------------------
# Backup e gravação
# --------------------------------------------------------------------------
def caminho_backup(backup_dir, agora=None):
    pasta = Path(backup_dir).expanduser().resolve()
    try:
        pasta.relative_to(REPO_ROOT)
        raise Recusa(f"A pasta de backup não pode ficar dentro do repositório ({REPO_ROOT}).")
    except ValueError:
        pass
    agora = agora or datetime.now()
    return pasta / f"backup_caixa_{agora.strftime('%Y%m%d_%H%M')}.json"


def salvar_backup(db, plano, caminho):
    if caminho.exists():
        raise Recusa(f"Backup {caminho} já existe; aguarde um minuto ou use outra --backup-dir.")
    dados = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "motivo": JUSTIFICATIVA,
        "cash_register": plano["register"],
        "orders": [db.orders.find_one({"id": i["order"]["id"]}, {"_id": 0}) for i in plano["itens"]],
        "payments": {i["order"]["id"]: list(db.payments.find({"order_id": i["order"]["id"]}, {"_id": 0}))
                     for i in plano["itens"]},
    }
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    json.loads(caminho.read_text(encoding="utf-8"))  # confere que o arquivo é legível
    return caminho


def aplicar(client, db, plano, corrigir_total):
    """Grava numa transação. Reconfere tudo dentro dela antes de inserir."""
    agora = datetime.now(timezone.utc).isoformat()
    reg = plano["register"]
    docs = []
    with client.start_session() as session:
        with session.start_transaction():
            atual_reg = db.cash_registers.find_one({"id": reg["id"], "is_open": True}, {"_id": 0}, session=session)
            if not atual_reg:
                raise Recusa("O caixa foi fechado ou mudou durante a correção.")
            for item in plano["itens"]:
                oid = item["order"]["id"]
                order = db.orders.find_one({"id": oid}, {"_id": 0}, session=session)
                if _ordem_conferencia(order) != _ordem_conferencia(item["order"]):
                    raise Recusa(f"{oid}: a comanda mudou desde a simulação. Rode de novo.")
                if _pagamentos_da_comanda(db, oid, session=session) != item["atuais"]:
                    raise Recusa(f"{oid}: os pagamentos mudaram desde a simulação. Rode de novo.")
                for p in item["novos"]:
                    docs.append({
                        "id": str(uuid.uuid4()),
                        "order_id": oid,
                        "amount": p["amount_cents"] / 100,
                        "method": p["method"],
                        "created_at": agora,
                        "created_by_id": plano["operador"]["id"],
                        "register_id": reg["id"],
                        "justificativa": JUSTIFICATIVA,
                        "regularizacao": True,
                    })
            db.payments.insert_many(docs, session=session)

            c = plano["total_sales"]
            if corrigir_total and c["diferenca"] != 0:
                res = db.cash_registers.update_one(
                    {"id": reg["id"], "is_open": True, "total_sales": atual_reg.get("total_sales")},
                    {"$set": {"total_sales": c["calculado"] / 100}},
                    session=session,
                )
                if getattr(res, "modified_count", 0) != 1:
                    raise Recusa("total_sales mudou durante a correção; nada foi gravado.")
    return docs


def _transacao_nao_suportada(exc):
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    return code in (20, 263) or "replica set" in text or "transaction numbers" in text


# --------------------------------------------------------------------------
def main(argv=None, client_factory=MongoClient, entrada=input):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.corrigir_total_sales and not args.apply:
        print("Aviso: --corrigir-total-sales só tem efeito com --apply. Simulando.\n")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    faltando = [n for n, v in (("MONGO_URL", mongo_url), ("DB_NAME", db_name)) if not v]
    if faltando:
        print(f"Erro: defina as variáveis de ambiente: {', '.join(faltando)}", file=sys.stderr)
        return 2

    kwargs = {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000}
    if mongo_url.startswith("mongodb+srv://") or "mongodb.net" in mongo_url:
        kwargs["tls"] = True

    try:
        client = client_factory(mongo_url, **kwargs)
        try:
            db = client[db_name]
            plano = planejar(db, args.pagamento, args.operador)
            imprimir_plano(plano, args.apply, args.corrigir_total_sales)
            if not args.apply:
                print("DRY-RUN: nada foi gravado. Para gravar, rode de novo com --apply.")
                return 0

            caminho = caminho_backup(args.backup_dir)
            if entrada(f"Digite {CONFIRMACAO} para gravar: ").strip() != CONFIRMACAO:
                print("Cancelado. Nada foi gravado.")
                return 1
            salvar_backup(db, plano, caminho)
            print(f"Backup salvo em {caminho}")
            docs = aplicar(client, db, plano, args.corrigir_total_sales)
            print(f"OK: {len(docs)} pagamento(s) registrado(s). Rode diagnostico_caixa.py para conferir.")
            return 0
        finally:
            client.close()
    except Recusa as exc:
        print(f"RECUSADO: {exc}\nNada foi gravado.", file=sys.stderr)
        return 1
    except PyMongoError as exc:
        if _transacao_nao_suportada(exc):
            print("ERRO: o banco não aceita transações. Nada foi gravado.", file=sys.stderr)
        else:
            print(f"ERRO no banco ({type(exc).__name__}). Nada foi gravado.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
