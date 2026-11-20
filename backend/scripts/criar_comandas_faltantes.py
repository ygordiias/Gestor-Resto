#!/usr/bin/env python3
"""Cria as comandas físicas que faltam na coleção physical_tabs. IDEMPOTENTE.

A faixa vem de backend/physical_tabs.py (PHYSICAL_TAB_MIN / PHYSICAL_TAB_MAX,
padrão 200 a 291), a mesma usada pelo servidor e pelo frontend.

- Só cria números que ainda não existem ($setOnInsert com upsert): nunca
  duplica, nunca altera comanda existente e nunca mexe em vínculos abertos.
- Rodar duas vezes dá o mesmo resultado: na segunda, nada é criado.
- --dry-run só lista o que seria criado; não escreve nada.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê arquivo .env).
Nunca imprime o MONGO_URL.

Uso:
    MONGO_URL=... DB_NAME=... python3 backend/scripts/criar_comandas_faltantes.py --dry-run
    MONGO_URL=... DB_NAME=... python3 backend/scripts/criar_comandas_faltantes.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import physical_tabs  # noqa: E402


def faltantes(collection):
    low, high = physical_tabs.tab_range()
    existentes = {
        doc["number"]
        for doc in collection.find({"number": {"$gte": low, "$lte": high}}, {"_id": 0, "number": 1})
    }
    return [n for n in range(low, high + 1) if n not in existentes]


def _faixas(numeros):
    """[231, 232, 233, 240] -> '231 a 233, 240'."""
    partes, inicio, anterior = [], None, None
    for n in numeros:
        if inicio is None:
            inicio = anterior = n
        elif n == anterior + 1:
            anterior = n
        else:
            partes.append(f"{inicio}" if inicio == anterior else f"{inicio} a {anterior}")
            inicio = anterior = n
    if inicio is not None:
        partes.append(f"{inicio}" if inicio == anterior else f"{inicio} a {anterior}")
    return ", ".join(partes)


def executar(collection, dry_run, out=print):
    low, high = physical_tabs.tab_range()
    lista = faltantes(collection)
    out(f"Faixa configurada: {low} a {high}")
    if not lista:
        out("Nenhuma comanda faltando. Nada a fazer.")
        return 0
    if dry_run:
        out(f"[dry-run] Seriam criadas {len(lista)} comanda(s): {_faixas(lista)}")
        return 0
    criadas = 0
    for number in lista:
        result = collection.update_one(
            {"number": number}, {"$setOnInsert": physical_tabs.new_tab_doc(number)}, upsert=True)
        if result.upserted_id is not None:
            criadas += 1
    out(f"Criadas {criadas} comanda(s): {_faixas(lista)}")
    return criadas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cria só as comandas físicas que faltam (idempotente).")
    ap.add_argument("--dry-run", action="store_true", help="só mostra o que seria criado")
    args = ap.parse_args(argv)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    faltando = [n for n, v in (("MONGO_URL", mongo_url), ("DB_NAME", db_name)) if not v]
    if faltando:
        print(f"Erro: defina as variáveis de ambiente: {', '.join(faltando)}", file=sys.stderr)
        return 2

    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    kwargs = {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000}
    if mongo_url.startswith("mongodb+srv://") or "mongodb.net" in mongo_url:
        kwargs["tls"] = True
    try:
        client = MongoClient(mongo_url, **kwargs)
        try:
            print(f"Banco: {db_name}")
            executar(client[db_name].physical_tabs, args.dry_run)
        finally:
            client.close()
    except PyMongoError as exc:
        # Só o tipo do erro: a mensagem pode conter detalhes da conexão.
        print(f"Erro ao acessar o banco ({type(exc).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
