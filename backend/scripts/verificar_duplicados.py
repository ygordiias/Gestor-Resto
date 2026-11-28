#!/usr/bin/env python3
"""Verifica se o campo `id` pode receber índice único. SOMENTE LEITURA.

Antes de criar um índice único em `id`, é preciso saber se há:
  - documentos sem `id` (ausente, nulo ou que não é texto): para o MongoDB,
    dois documentos sem o campo contam como duplicados (os dois valem null);
  - o mesmo `id` em mais de um documento.

Se qualquer um dos dois aparecer, o índice único falha ao ser criado. Neste
caso não corrija nada às cegas: mostre o resultado ao responsável.

Coleções verificadas:
  - orders e cash_registers: recebem índice único em `id` (db_indexes.py);
  - payments, invoices e payment_reversals: só informativo.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê arquivo .env).
Não escreve nada no banco: só usa count_documents e aggregate (sem $out/$merge).
Não imprime dados de clientes: só nomes de coleção, contagens e os `id`
repetidos (UUIDs gerados pelo sistema).

Uso:
    python backend/scripts/verificar_duplicados.py
Código de saída: 0 sem problema nas coleções com índice único; 1 com problema;
2 erro de conexão ou de configuração.
"""
import os
import sys

from pymongo import MongoClient
from pymongo.errors import PyMongoError

COM_INDICE_UNICO = ("orders", "cash_registers")
SO_INFORMATIVO = ("payments", "invoices", "payment_reversals")
MAX_EXEMPLOS = 20


def verificar(db, nome):
    col = db[nome]
    total = col.count_documents({})
    sem_id = col.count_documents({"id": {"$not": {"$type": "string"}}})
    repetidos = list(col.aggregate([
        {"$match": {"id": {"$type": "string"}}},
        {"$group": {"_id": "$id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$sort": {"n": -1, "_id": 1}},
    ], allowDiskUse=True))
    return {"total": total, "sem_id": sem_id, "repetidos": repetidos}


def main():
    url, nome_db = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not url or not nome_db:
        print("Defina MONGO_URL e DB_NAME no ambiente.", file=sys.stderr)
        return 2
    try:
        client = MongoClient(url, serverSelectionTimeoutMS=15000)
        db = client[nome_db]
        print(f"Banco: {nome_db} (somente leitura)\n")
        problema = False
        for nome in COM_INDICE_UNICO + SO_INFORMATIVO:
            r = verificar(db, nome)
            unico = nome in COM_INDICE_UNICO
            ok = r["sem_id"] == 0 and not r["repetidos"]
            if unico and not ok:
                problema = True
            marca = "OK" if ok else ("PROBLEMA" if unico else "atenção")
            tipo = "índice único" if unico else "informativo"
            print(f"[{marca}] {nome} ({tipo}): {r['total']} documentos, "
                  f"{r['sem_id']} sem id, {len(r['repetidos'])} id repetidos")
            for g in r["repetidos"][:MAX_EXEMPLOS]:
                print(f"    id {g['_id']} aparece {g['n']} vezes")
            if len(r["repetidos"]) > MAX_EXEMPLOS:
                print(f"    ... e mais {len(r['repetidos']) - MAX_EXEMPLOS}")
        print()
        if problema:
            print("RESULTADO: há duplicados ou documentos sem id. NÃO crie os índices únicos.")
            return 1
        print("RESULTADO: nenhum duplicado. Os índices únicos podem ser criados.")
        return 0
    except PyMongoError as e:
        # Só o tipo do erro: a mensagem do driver pode conter o endereço do banco.
        print(f"Erro ao acessar o MongoDB ({type(e).__name__}).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
