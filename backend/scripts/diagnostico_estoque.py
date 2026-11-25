#!/usr/bin/env python3
"""Diagnóstico de estoque, receitas e CMV. SOMENTE LEITURA.

Mostra por que lanches, porções e insumos não baixam do estoque:
  1. produtos sem receita (e quais deles têm ficha técnica mas não receita);
  2. receitas com problema: ingrediente inexistente, quantidade zero/negativa,
     unidade suspeita (ex.: 150 num item em kg) e insumo sem custo;
  3. itens de estoque que nenhuma receita usa;
  4. baixas que falharam: itens de comandas fechadas sem baixa (no banco) e,
     com --log, as linhas de falha exportadas dos logs do Render.

Regras da baixa hoje (server.py, deduct_stock): o produto com receita em
`recipes` baixa os ingredientes; sem receita, baixa o item de estoque ligado
direto ao produto (product_id); sem nenhum dos dois, não baixa nada. A ficha
técnica (`technical_sheets`) NÃO participa da baixa nem do CMV.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê arquivo .env).
Não escreve nada no banco: só usa find, find_one e count_documents.
Não imprime dados de clientes (nome, telefone, endereço): só produtos,
insumos, quantidades, ids de pedido e números de comanda/mesa.

Uso:
    python3 backend/scripts/diagnostico_estoque.py
    python3 backend/scripts/diagnostico_estoque.py --dias 60 --log render.log
Opções:
    --dias N          janela das comandas fechadas analisadas (padrão 30)
    --limite N        máximo de linhas por lista (padrão 50)
    --log ARQUIVO     log exportado do Render para contar falhas de baixa
    --max-kg X        acima de X por porção, item em kg/litro é suspeito (padrão 1)
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient
from pymongo.errors import PyMongoError

UNIDADES_GRANDES = {"kg", "liter"}   # 1 por porção já é muito
UNIDADES_PEQUENAS = {"gram"}         # menos de 1 g por porção é estranho
MAX_UNIDADES = 20                    # mais de 20 "un" por porção é estranho

PROJ_PRODUTO = {"_id": 0, "id": 1, "name": 1, "type": 1, "category_id": 1, "is_available": 1}
PROJ_ESTOQUE = {"_id": 0, "id": 1, "name": 1, "product_id": 1, "unit": 1, "quantity": 1,
                "unit_cost": 1, "stock_type": 1, "category": 1}
# Só o necessário do pedido; nunca customer_name/phone/address.
PROJ_PEDIDO = {"_id": 0, "id": 1, "status": 1, "closed_at": 1, "source": 1,
               "tab_number": 1, "table_number": 1, "order_code": 1,
               "items.product_id": 1, "items.product_name": 1, "items.status": 1,
               "items.quantity": 1, "items.stock_deducted": 1}

# Linhas de log que indicam baixa que falhou.
RE_FALHA_CLOSE = re.compile(r"\[close_order\] Baixa falhou para (?P<produto>.*?): (?P<motivo>.*)$")
RE_FALHA_STATUS = re.compile(r'"PUT /api/orders/[^/\s]+/item/[^/\s]+/status[^"]*" 400')


def num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fmt(q):
    q = num(q)
    return str(int(q)) if q == int(q) else f"{q:.3f}".rstrip("0").rstrip(".")


def nome_estoque(item, produtos):
    if item.get("name"):
        return item["name"]
    p = produtos.get(item.get("product_id"))
    return (p or {}).get("name") or f"(sem nome, id {item.get('id')})"


def unidade_suspeita(qtd, unidade, max_kg=1.0):
    """Motivo se a quantidade por porção parece digitada na unidade errada."""
    q = num(qtd)
    if unidade in UNIDADES_GRANDES and q > max_kg:
        return f"{fmt(q)} {unidade} por porção: parece digitado em g/ml"
    if unidade in UNIDADES_PEQUENAS and 0 < q < 1:
        return f"{fmt(q)} {unidade} por porção: parece digitado em kg"
    if unidade == "unit" and q > MAX_UNIDADES:
        return f"{fmt(q)} un por porção: confira"
    return None


def analisar_receitas(recipes, estoque, produtos, max_kg=1.0):
    """Devolve lista de (produto, problema)."""
    problemas = []
    for r in recipes:
        prod = produtos.get(r.get("product_id"))
        nome_prod = (prod or {}).get("name") or f"(produto inexistente, id {r.get('product_id')})"
        if not prod:
            problemas.append((nome_prod, "receita de produto que não existe mais"))
        ingredientes = r.get("ingredients") or []
        if not ingredientes:
            problemas.append((nome_prod, "receita sem ingredientes (não baixa nada)"))
        for ing in ingredientes:
            sid = ing.get("stock_item_id")
            item = estoque.get(sid)
            if not sid or not item:
                problemas.append((nome_prod, f"ingrediente inexistente no estoque (id {sid}): a baixa inteira falha"))
                continue
            nome_ing = nome_estoque(item, produtos)
            q = num(ing.get("quantity"))
            if q <= 0:
                problemas.append((nome_prod, f"{nome_ing}: quantidade {fmt(q)} (ignorada na baixa)"))
                continue
            motivo = unidade_suspeita(q, item.get("unit"), max_kg)
            if motivo:
                problemas.append((nome_prod, f"{nome_ing}: {motivo}"))
            if num(item.get("unit_cost")) <= 0:
                problemas.append((nome_prod, f"{nome_ing}: insumo sem custo (CMV fica zerado)"))
    return problemas


def falhas_no_banco(orders, produtos, com_receita, com_estoque_direto):
    """Itens de comandas fechadas (não canceladas) sem baixa, por produto.

    Separa os que DEVERIAM ter baixado (produto com receita ou estoque direto)
    dos que não baixam por falta de cadastro."""
    falhou = defaultdict(lambda: {"itens": 0, "qtd": 0.0, "pedidos": []})
    sem_cadastro = defaultdict(lambda: {"itens": 0, "qtd": 0.0})
    for o in orders:
        if o.get("status") == "cancelled":
            continue
        for it in o.get("items") or []:
            if it.get("status") == "cancelled" or it.get("stock_deducted"):
                continue
            pid = it.get("product_id")
            nome = (produtos.get(pid) or {}).get("name") or it.get("product_name") or pid
            if pid in com_receita or pid in com_estoque_direto:
                f = falhou[nome]
                f["itens"] += 1
                f["qtd"] += num(it.get("quantity"))
                if len(f["pedidos"]) < 5 and o.get("id") not in f["pedidos"]:
                    f["pedidos"].append(o.get("id"))
            else:
                s = sem_cadastro[nome]
                s["itens"] += 1
                s["qtd"] += num(it.get("quantity"))
    return falhou, sem_cadastro


def falhas_no_log(linhas):
    """Conta falhas de baixa num log exportado do Render."""
    por_produto = Counter()
    exemplo = {}
    status_400 = 0
    for linha in linhas:
        linha = linha.rstrip("\n")
        m = RE_FALHA_CLOSE.search(linha)
        if m:
            produto = m.group("produto").strip()
            por_produto[produto] += 1
            exemplo.setdefault(produto, m.group("motivo").strip()[:200])
        elif RE_FALHA_STATUS.search(linha):
            status_400 += 1
    return por_produto, exemplo, status_400


def _lista(titulo, linhas, limite):
    print(f"\n{titulo}: {len(linhas)}")
    for linha in linhas[:limite]:
        print(f"  - {linha}")
    if len(linhas) > limite:
        print(f"  ... e mais {len(linhas) - limite} (use --limite)")


def relatorio(db, dias=30, limite=50, log_linhas=None, max_kg=1.0, agora=None) -> int:
    agora = agora or datetime.now(timezone.utc)
    produtos = {p["id"]: p for p in db.products.find({}, PROJ_PRODUTO) if p.get("id")}
    categorias = {c.get("id"): c.get("name") for c in db.categories.find({}, {"_id": 0, "id": 1, "name": 1})}
    estoque = {s["id"]: s for s in db.stock.find({}, PROJ_ESTOQUE) if s.get("id")}
    recipes = list(db.recipes.find({}, {"_id": 0, "id": 1, "product_id": 1, "ingredients": 1}))
    fichas = {f.get("product_id") for f in db.technical_sheets.find({}, {"_id": 0, "product_id": 1})}
    prod_recipes = list(db.production_recipes.find(
        {}, {"_id": 0, "produced_stock_item_id": 1, "ingredients": 1}))

    com_receita = {r.get("product_id") for r in recipes if r.get("ingredients")}
    com_estoque_direto = {s.get("product_id") for s in estoque.values() if s.get("product_id")}

    print("=" * 70)
    print("DIAGNÓSTICO DE ESTOQUE E CMV (somente leitura)")
    print("=" * 70)
    print(f"Produtos: {len(produtos)} | receitas: {len(recipes)} | fichas técnicas: {len(fichas)} "
          f"| itens de estoque: {len(estoque)} | fórmulas de produção: {len(prod_recipes)}")

    def rotulo(p):
        cat = categorias.get(p.get("category_id")) or "sem categoria"
        tipo = {"food": "comida", "drink": "bebida"}.get(p.get("type"), p.get("type") or "?")
        extra = "" if p.get("is_available", True) else ", indisponível"
        return f"{p.get('name')} ({tipo}, {cat}{extra})"

    ordenados = sorted(produtos.values(), key=lambda p: (str(p.get("type")), str(p.get("name"))))
    nada = [rotulo(p) for p in ordenados if p["id"] not in com_receita and p["id"] not in com_estoque_direto]
    ficha_sem_receita = [rotulo(p) for p in ordenados if p["id"] in fichas and p["id"] not in com_receita]
    so_direto = [rotulo(p) for p in ordenados if p["id"] not in com_receita and p["id"] in com_estoque_direto]

    print("\n--- 1. PRODUTOS SEM RECEITA ---")
    _lista("Sem receita e sem estoque direto (NUNCA baixam nada)", nada, limite)
    _lista("Com ficha técnica mas SEM receita (a ficha não baixa estoque)", ficha_sem_receita, limite)
    _lista("Só estoque direto, modelo antigo (baixa 1 para 1; ex.: bebidas)", so_direto, limite)

    print("\n--- 2. RECEITAS COM PROBLEMA ---")
    problemas = analisar_receitas(recipes, estoque, produtos, max_kg)
    _lista("Problemas encontrados", [f"{p}: {m}" for p, m in problemas], limite)

    print("\n--- 3. ITENS DE ESTOQUE ---")
    usados = {ing.get("stock_item_id") for r in recipes for ing in (r.get("ingredients") or [])}
    for f in prod_recipes:
        for ing in f.get("ingredients") or []:
            usados.add(ing.get("stock_item_id"))
        usados.add(f.get("produced_stock_item_id"))
    nao_usados = []
    for s in sorted(estoque.values(), key=lambda s: nome_estoque(s, produtos)):
        if s["id"] in usados:
            continue
        ligado = " — ligado direto a produto (modelo antigo)" if s.get("product_id") in produtos else ""
        nao_usados.append(f"{nome_estoque(s, produtos)}: {fmt(s.get('quantity'))} {s.get('unit')}{ligado}")
    _lista("Itens que nenhuma receita usa", nao_usados, limite)
    negativos = [f"{nome_estoque(s, produtos)}: {fmt(s.get('quantity'))} {s.get('unit')}"
                 for s in estoque.values() if num(s.get("quantity")) < 0]
    _lista("Itens com saldo negativo", negativos, limite)

    print(f"\n--- 4. BAIXAS QUE FALHARAM (comandas fechadas nos últimos {dias} dias) ---")
    desde = (agora - timedelta(days=dias)).isoformat()
    orders = list(db.orders.find({"is_closed": True, "closed_at": {"$gte": desde}}, PROJ_PEDIDO))
    falhou, sem_cadastro = falhas_no_banco(orders, produtos, com_receita, com_estoque_direto)
    print(f"Comandas fechadas analisadas: {len(orders)}")
    _lista("Deveriam ter baixado e NÃO baixaram (produto tem receita ou estoque direto)",
           [f"{n}: {v['itens']} item(ns), qtd {fmt(v['qtd'])} — ex.: pedidos {', '.join(map(str, v['pedidos']))}"
            for n, v in sorted(falhou.items(), key=lambda kv: -kv[1]["itens"])], limite)
    _lista("Vendidos sem baixa por falta de cadastro (sem receita e sem estoque direto)",
           [f"{n}: {v['itens']} item(ns), qtd {fmt(v['qtd'])}"
            for n, v in sorted(sem_cadastro.items(), key=lambda kv: -kv[1]["itens"])], limite)

    if log_linhas is not None:
        por_produto, exemplo, status_400 = falhas_no_log(log_linhas)
        _lista("No log: 'Baixa falhou' no fechamento, por produto",
               [f"{p}: {n} vez(es) — ex.: {exemplo[p]}" for p, n in por_produto.most_common()], limite)
        print(f"\nNo log: mudanças de status de item recusadas com 400 (inclui falta de estoque): {status_400}")
    else:
        print("\n(Sem --log: falhas registradas só nos logs do Render não foram contadas.)")

    print("\nNada foi gravado no banco.")
    return 0


def main(argv=None, client_factory=MongoClient) -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico de estoque e CMV (somente leitura).")
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--limite", type=int, default=50)
    ap.add_argument("--log", dest="log")
    ap.add_argument("--max-kg", type=float, default=1.0)
    args = ap.parse_args(argv)
    if args.dias <= 0 or args.limite <= 0 or args.max_kg <= 0:
        print("Erro: --dias, --limite e --max-kg devem ser maiores que zero.", file=sys.stderr)
        return 2

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    faltando = [n for n, v in (("MONGO_URL", mongo_url), ("DB_NAME", db_name)) if not v]
    if faltando:
        print(f"Erro: defina as variáveis de ambiente: {', '.join(faltando)}", file=sys.stderr)
        return 2

    log_linhas = None
    if args.log:
        try:
            with open(args.log, encoding="utf-8", errors="replace") as fh:
                log_linhas = fh.readlines()
        except OSError as exc:
            print(f"Erro ao ler o log ({type(exc).__name__}).", file=sys.stderr)
            return 2

    kwargs = {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000}
    if mongo_url.startswith("mongodb+srv://") or "mongodb.net" in mongo_url:
        kwargs["tls"] = True

    try:
        client = client_factory(mongo_url, **kwargs)
        try:
            return relatorio(client[db_name], args.dias, args.limite, log_linhas, args.max_kg)
        finally:
            client.close()
    except PyMongoError as exc:
        print(f"Erro ao consultar o banco ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
