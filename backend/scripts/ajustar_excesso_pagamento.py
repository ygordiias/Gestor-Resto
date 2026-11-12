#!/usr/bin/env python3
"""Ajusta pagamento em cartão/Pix MAIOR que o total da comanda (sem dinheiro
para troco), que trava o fechamento do caixa aberto.

SIMULAÇÃO (--dry-run) É O PADRÃO: sem --apply, nada é gravado.

Para cada --ajustar ORDER_ID:
  - confere que a comanda é presencial, fechada, não cancelada, não cortesia,
    pertence ao caixa aberto e está INCONSISTENTE hoje;
  - exige que NÃO haja pagamento em dinheiro e que o pago seja maior que o total;
  - reduz o excesso (pago - total) do ÚLTIMO pagamento não-dinheiro, para que
    a soma fique igual ao total. Se o excesso for igual ao último pagamento
    (caso típico de Pix duplicado), ele fica com R$ 0,00 e o valor original
    continua guardado nele;
  - confere, pelas mesmas regras do fechamento do caixa, que a comanda fica
    CONSISTENTE depois do ajuste.

Rastro no próprio pagamento (nada é substituído sem registro):
  amount_original, amount_ajustado_em, amount_ajustado_por_id, justificativa.

Regras de segurança (as mesmas de corrigir_comandas_caixa.py):
  - Não apaga nada. Não cria nem remove pagamento; só ajusta o valor de um.
  - Recusa: excesso maior que o último pagamento não-dinheiro, comanda com
    dinheiro, comanda já consistente, cortesia/cancelada/online, pagamento
    que já foi ajustado antes. Se um pedido for recusado, nenhum é gravado.
  - Backup em ~/backup_ajuste_AAAAMMDD_HHMM.json (fora do repositório) antes
    de gravar. Confirmação digitada. Transação: tudo ou nada; sem suporte a
    transação, para sem gravar.
  - total_sales do caixa não é alterado por este script.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê .env).
Não imprime dados de clientes.

Uso:
    # simulação (padrão)
    python3 backend/scripts/ajustar_excesso_pagamento.py \\
        --operador admin@exemplo.com --ajustar <ORDER_ID> --ajustar <ORDER_ID>
    # gravar de verdade
    python3 backend/scripts/ajustar_excesso_pagamento.py --apply \\
        --operador admin@exemplo.com --ajustar <ORDER_ID>
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from corrigir_comandas_caixa import CONFIRMACAO, REPO_ROOT, Recusa, _transacao_nao_suportada, buscar_operador
from diagnostico_caixa import analisar, brl, cents, identificar

JUSTIFICATIVA = ("regularização de inconsistência do caixa: "
                 "pagamento em cartão/Pix maior que o total, sem dinheiro para troco")


def parse_args(argv):
    ap = argparse.ArgumentParser(
        description="Ajusta excesso de pagamento cartão/Pix em comandas do caixa aberto (dry-run por padrão).")
    ap.add_argument("--ajustar", action="append", required=True, metavar="ORDER_ID",
                    help="comanda a ajustar; repita para várias")
    ap.add_argument("--operador", required=True,
                    help="e-mail (ou id) do admin/superadmin ativo responsável pelo ajuste")
    ap.add_argument("--apply", action="store_true", help="grava de verdade (sem isto, só simula)")
    ap.add_argument("--backup-dir", default=str(Path.home()),
                    help="pasta do backup (padrão: sua pasta pessoal; nunca dentro do repositório)")
    return ap.parse_args(argv)


# --------------------------------------------------------------------------
# Planejamento (somente leitura)
# --------------------------------------------------------------------------
def _pagamentos(db, order_id, session=None):
    """Pagamentos da comanda, com _id, em ordem cronológica estável."""
    pays = db.payments.find({"order_id": order_id}, session=session)
    return sorted(pays, key=lambda p: (str(p.get("created_at", "")), str(p.get("_id", ""))))


def _resumo(p):
    return {"method": p.get("method"), "amount": p.get("amount"), "created_at": p.get("created_at")}


def _ordem_conferencia(order):
    return {k: order.get(k) for k in ("id", "tab_number", "table_number", "total", "closed_at",
                                      "status", "is_closed", "is_comp", "source")}


def planejar(db, order_ids, operador_ident):
    register = db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if not register:
        raise Recusa("Nenhum caixa aberto.")
    operador = buscar_operador(db, operador_ident)

    vistos = set()
    itens = []
    for order_id in order_ids:
        order_id = order_id.strip()
        if not order_id:
            raise Recusa("--ajustar vazio.")
        if order_id in vistos:
            raise Recusa(f"{order_id}: informado mais de uma vez.")
        vistos.add(order_id)

        order = db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise Recusa(f"{order_id}: comanda não encontrada.")
        if not order.get("is_closed"):
            raise Recusa(f"{order_id}: comanda ainda aberta.")
        if order.get("status") == "cancelled" or order.get("is_comp") or order.get("source") == "online":
            raise Recusa(f"{order_id}: cancelada, cortesia ou online não entram na conferência do caixa.")
        if str(order.get("closed_at") or "") < str(register["opened_at"]):
            raise Recusa(f"{order_id}: fechada antes da abertura do caixa atual.")

        pays = _pagamentos(db, order_id)
        motivos_antes, n_antes = analisar(order, pays)
        if not motivos_antes:
            raise Recusa(f"{order_id}: comanda já está consistente; nada a ajustar.")
        if any(p.get("method") == "cash" for p in pays):
            raise Recusa(f"{order_id}: há pagamento em dinheiro nesta comanda; ajuste manual necessário.")
        excesso = n_antes["pago"] - n_antes["total"]
        if excesso <= 0:
            raise Recusa(f"{order_id}: o pago não é maior que o total "
                         f"({' | '.join(motivos_antes)}); use corrigir_comandas_caixa.py.")

        alvo = pays[-1] if pays else None  # sem dinheiro: o último é não-dinheiro
        if alvo is None or alvo.get("method") == "cash":
            raise Recusa(f"{order_id}: nenhum pagamento não-dinheiro para ajustar.")
        if "amount_original" in alvo or "justificativa" in alvo:
            raise Recusa(f"{order_id}: o último pagamento já tem ajuste/justificativa registrado; "
                         "ajuste manual necessário.")
        valor_alvo = cents(alvo.get("amount"))
        if excesso > valor_alvo:
            raise Recusa(f"{order_id}: excesso {brl(excesso)} maior que o último pagamento "
                         f"({alvo.get('method')} {brl(valor_alvo)}).")
        novo_valor = valor_alvo - excesso

        depois = [dict(p) for p in pays]
        depois[-1]["amount"] = novo_valor / 100
        motivos_depois, n_depois = analisar(order, depois)
        if motivos_depois:
            raise Recusa(f"{order_id}: continuaria inconsistente após o ajuste ({' | '.join(motivos_depois)}).")

        itens.append({
            "order": order, "pagamentos": pays, "depois": depois, "alvo_id": alvo["_id"],
            "valor_original": alvo.get("amount"), "valor_novo_cents": novo_valor, "excesso": excesso,
            "motivos_antes": motivos_antes, "n_antes": n_antes, "n_depois": n_depois,
        })
    return {"register": register, "operador": operador, "itens": itens}


def imprimir_plano(plano, apply):
    reg = plano["register"]
    op = plano["operador"]
    print(f"=== {'GRAVAÇÃO' if apply else 'SIMULAÇÃO (dry-run): nada será gravado'} ===")
    print(f"caixa aberto: {reg.get('id')}  (aberto em {reg.get('opened_at')} UTC)")
    print(f"operador:     {op.get('name')} <{op.get('email')}> ({op.get('role')}, id {op.get('id')})")
    print(f"justificativa: {JUSTIFICATIVA}")
    print()
    for i, item in enumerate(plano["itens"], 1):
        o = item["order"]
        print(f"--- [{i}] {identificar(o)}  order_id={o['id']} ---")
        print(f"hoje:    {' | '.join(item['motivos_antes'])}")
        print(f"total:   {brl(item['n_antes']['total'])}   pago: {brl(item['n_antes']['pago'])}   "
              f"excesso: {brl(item['excesso'])}")
        print("pagamentos (antes -> depois):")
        for antes, dep in zip(item["pagamentos"], item["depois"]):
            a, d = cents(antes.get("amount")), cents(dep.get("amount"))
            marca = ""
            if antes["_id"] == item["alvo_id"]:
                marca = "   <- AJUSTADO" + (" (fica R$ 0,00: provável duplicado)" if d == 0 else "")
            print(f"    {str(antes.get('method')):<8} {brl(a):>14} -> {brl(d):>14}   {antes.get('created_at')}{marca}")
        print(f"depois:  pago {brl(item['n_depois']['pago'])} = total {brl(item['n_depois']['total'])} -> CONSISTENTE")
        print()
    print("total_sales do caixa: não é alterado por este script.")
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
    return pasta / f"backup_ajuste_{agora.strftime('%Y%m%d_%H%M')}.json"


def salvar_backup(db, plano, caminho):
    if caminho.exists():
        raise Recusa(f"Backup {caminho} já existe; aguarde um minuto ou use outra --backup-dir.")
    dados = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "motivo": JUSTIFICATIVA,
        "cash_register": plano["register"],
        "orders": [db.orders.find_one({"id": i["order"]["id"]}, {"_id": 0}) for i in plano["itens"]],
        "payments": {i["order"]["id"]: list(db.payments.find({"order_id": i["order"]["id"]}))
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


def aplicar(client, db, plano):
    """Ajusta numa transação. Reconfere comanda e pagamentos dentro dela."""
    agora = datetime.now(timezone.utc).isoformat()
    operador_id = plano["operador"]["id"]
    ajustados = 0
    with client.start_session() as session:
        with session.start_transaction():
            if not db.cash_registers.find_one({"id": plano["register"]["id"], "is_open": True},
                                              {"_id": 0}, session=session):
                raise Recusa("O caixa foi fechado ou mudou durante o ajuste.")
            for item in plano["itens"]:
                oid = item["order"]["id"]
                order = db.orders.find_one({"id": oid}, {"_id": 0}, session=session)
                if _ordem_conferencia(order) != _ordem_conferencia(item["order"]):
                    raise Recusa(f"{oid}: a comanda mudou desde a simulação. Rode de novo.")
                atuais = _pagamentos(db, oid, session=session)
                if [_resumo(p) for p in atuais] != [_resumo(p) for p in item["pagamentos"]]:
                    raise Recusa(f"{oid}: os pagamentos mudaram desde a simulação. Rode de novo.")
                res = db.payments.update_one(
                    {"_id": item["alvo_id"], "order_id": oid, "amount": item["valor_original"]},
                    {"$set": {
                        "amount": item["valor_novo_cents"] / 100,
                        "amount_original": item["valor_original"],
                        "amount_ajustado_em": agora,
                        "amount_ajustado_por_id": operador_id,
                        "justificativa": JUSTIFICATIVA,
                    }},
                    session=session,
                )
                if getattr(res, "modified_count", 0) != 1:
                    raise Recusa(f"{oid}: o pagamento mudou durante o ajuste; nada foi gravado.")
                ajustados += 1
    return ajustados


# --------------------------------------------------------------------------
def main(argv=None, client_factory=MongoClient, entrada=input):
    args = parse_args(argv if argv is not None else sys.argv[1:])

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
            plano = planejar(db, args.ajustar, args.operador)
            imprimir_plano(plano, args.apply)
            if not args.apply:
                print("DRY-RUN: nada foi gravado. Para gravar, rode de novo com --apply.")
                return 0

            caminho = caminho_backup(args.backup_dir)
            if entrada(f"Digite {CONFIRMACAO} para gravar: ").strip() != CONFIRMACAO:
                print("Cancelado. Nada foi gravado.")
                return 1
            salvar_backup(db, plano, caminho)
            print(f"Backup salvo em {caminho}")
            n = aplicar(client, db, plano)
            print(f"OK: {n} pagamento(s) ajustado(s). Rode diagnostico_caixa.py para conferir.")
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
