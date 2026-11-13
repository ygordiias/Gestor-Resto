#!/usr/bin/env python3
"""Diagnóstico do caixa aberto. SOMENTE LEITURA.

Lista as comandas fechadas desde a abertura do caixa que BLOQUEIAM o
fechamento (POST /api/cash-register/close), usando as mesmas regras do servidor:
  - sem pagamento (total > 0 e nenhum pagamento registrado);
  - pagamento menor que o total;
  - troco maior que o dinheiro recebido;
  - forma de pagamento inválida.
Também aponta sinais de duplo clique (pagamentos repetidos) e compara o
total_sales do caixa com a soma das comandas válidas.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê arquivo .env).
Não escreve nada no banco: só usa find, find_one e count_documents.
Não imprime dados de clientes (nome, telefone, endereço); só ids, números de
comanda/mesa, valores, formas de pagamento e horários.

Uso:
    python3 backend/scripts/diagnostico_caixa.py
"""
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Mesmas formas aceitas pelo fechamento do caixa (server.py, close_register).
METODOS_VALIDOS = {"cash", "pix", "credit", "debit", "card", "voucher"}
JANELA_DUPLICADO_S = 10  # pagamentos iguais com menos de 10 s: possível duplo clique


def cents(value):
    return round(float(value or 0) * 100)


def brl(c):
    return f"R$ {c / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_dt(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def identificar(order):
    partes = []
    if order.get("tab_number") is not None:
        partes.append(f"comanda {order['tab_number']}")
    if order.get("table_number") is not None:
        partes.append(f"mesa {order['table_number']}")
    return ", ".join(partes) or "sem comanda/mesa"


def possiveis_duplicados(payments):
    vistos = []
    achados = 0
    for p in sorted(payments, key=lambda x: str(x.get("created_at", ""))):
        t = parse_dt(p.get("created_at"))
        chave = (p.get("method"), cents(p.get("amount")))
        for (k, tv) in vistos:
            if k == chave and t and tv and abs((t - tv).total_seconds()) <= JANELA_DUPLICADO_S:
                achados += 1
                break
        vistos.append((chave, t))
    return achados


def analisar(order, payments):
    """Mesma ordem de regras do close_register. Retorna (motivos, números)."""
    total = cents(order.get("total"))
    pago = sum(cents(p.get("amount")) for p in payments)
    dinheiro = sum(cents(p.get("amount")) for p in payments if p.get("method") == "cash")
    troco = pago - total
    invalidos = sorted({str(p.get("method")) for p in payments if p.get("method") not in METODOS_VALIDOS})

    motivos = []
    if not payments and total > 0:
        motivos.append("SEM PAGAMENTO")
    else:
        if pago < total:
            motivos.append(f"PAGAMENTO MENOR QUE O TOTAL (faltam {brl(total - pago)})")
        elif troco > dinheiro:
            motivos.append(f"TROCO ({brl(troco)}) MAIOR QUE O DINHEIRO RECEBIDO ({brl(dinheiro)})")
        if invalidos:
            motivos.append(f"FORMA DE PAGAMENTO INVÁLIDA: {', '.join(invalidos)}")
    return motivos, {"total": total, "pago": pago, "dinheiro": dinheiro, "troco": troco}


def main() -> int:
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
        client = MongoClient(mongo_url, **kwargs)
        try:
            db = client[db_name]
            return relatorio(db)
        finally:
            client.close()
    except PyMongoError as exc:
        print(f"Erro ao consultar o banco ({type(exc).__name__}).", file=sys.stderr)
        return 1


def relatorio(db) -> int:
    register = db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if not register:
        print("Nenhum caixa aberto.")
        return 0

    opened_at = register["opened_at"]
    agora = datetime.now(timezone.utc).isoformat()
    print("=== CAIXA ABERTO ===")
    print(f"id:          {register.get('id')}")
    print(f"aberto em:   {opened_at} (UTC)")
    print(f"aberto por:  {register.get('opened_by', '-')}")
    print(f"total_sales gravado no caixa: {brl(cents(register.get('total_sales')))}")
    print()

    abertas = db.orders.count_documents({"is_closed": False, "source": {"$ne": "online"}})
    if abertas:
        print(f"ATENÇÃO: {abertas} comanda(s) presencial(is) ainda aberta(s) também bloqueiam o fechamento.\n")

    orders = list(db.orders.find(
        {"is_closed": True, "closed_at": {"$gte": opened_at, "$lte": agora}},
        {"_id": 0, "id": 1, "tab_number": 1, "table_number": 1, "total": 1,
         "status": 1, "is_comp": 1, "source": 1, "closed_at": 1},
    ).sort("closed_at", 1))

    contagem = {"canceladas": 0, "cortesia": 0, "online": 0, "validas": 0}
    soma_validas = 0
    problemas = []
    avisos_duplicados = []  # comandas válidas, mas com pagamento repetido

    for order in orders:
        if order.get("status") == "cancelled":
            contagem["canceladas"] += 1
            continue
        if order.get("is_comp"):
            contagem["cortesia"] += 1
            continue
        if order.get("source") == "online":
            contagem["online"] += 1
            continue

        payments = list(db.payments.find(
            {"order_id": order["id"]},
            {"_id": 0, "method": 1, "amount": 1, "created_at": 1},
        ))
        motivos, n = analisar(order, payments)
        if motivos:
            problemas.append((order, payments, motivos, n))
        else:
            contagem["validas"] += 1
            soma_validas += n["total"]
            if possiveis_duplicados(payments):
                avisos_duplicados.append((order, payments))

    print(f"Comandas fechadas desde a abertura: {len(orders)} "
          f"(válidas {contagem['validas']}, canceladas {contagem['canceladas']}, "
          f"cortesia {contagem['cortesia']}, online {contagem['online']}, "
          f"INCONSISTENTES {len(problemas)})")
    print()

    for i, (order, payments, motivos, n) in enumerate(problemas, 1):
        print(f"--- [{i}] {identificar(order)} ---")
        print(f"order_id:    {order['id']}")
        print(f"fechada em:  {order.get('closed_at')} (UTC)")
        print(f"motivo:      {' | '.join(motivos)}")
        print(f"total:       {brl(n['total'])}")
        print(f"pago:        {brl(n['pago'])}   (dinheiro {brl(n['dinheiro'])})")
        print(f"diferença:   {brl(n['pago'] - n['total'])}   (pago - total)")
        if payments:
            print("pagamentos:")
            for p in sorted(payments, key=lambda x: str(x.get("created_at", ""))):
                print(f"    {str(p.get('method')):<8} {brl(cents(p.get('amount'))):>14}   {p.get('created_at')}")
        else:
            print("pagamentos:  nenhum")
        dup = possiveis_duplicados(payments)
        if dup:
            print(f"ATENÇÃO:     {dup} pagamento(s) repetido(s) em até {JANELA_DUPLICADO_S}s (possível duplo clique)")
        print()

    if avisos_duplicados:
        print("=== AVISO: comandas VÁLIDAS com pagamento repetido (não bloqueiam o fechamento) ===")
        for order, payments in avisos_duplicados:
            print(f"aviso: {identificar(order)}  order_id={order['id']}  "
                  f"{possiveis_duplicados(payments)} pagamento(s) repetido(s) em até {JANELA_DUPLICADO_S}s")
            for p in sorted(payments, key=lambda x: str(x.get("created_at", ""))):
                print(f"    {str(p.get('method')):<8} {brl(cents(p.get('amount'))):>14}   {p.get('created_at')}")
        print()

    gravado = cents(register.get("total_sales"))
    soma_todas = soma_validas + sum(n["total"] for _, _, _, n in problemas)
    print("=== CONFERÊNCIA DO total_sales ===")
    print(f"gravado no caixa:                          {brl(gravado)}")
    print(f"soma das comandas válidas:                 {brl(soma_validas)}")
    print(f"soma válidas + inconsistentes:             {brl(soma_todas)}")
    if gravado != soma_todas:
        print(f"DIFERENÇA (gravado - válidas+inconsist.):  {brl(gravado - soma_todas)}"
              "   <- pode indicar fechamento somado duas vezes")
    print("\nNada foi alterado no banco.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
