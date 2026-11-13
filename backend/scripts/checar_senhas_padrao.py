#!/usr/bin/env python3
"""Verifica se contas antigas ainda usam a senha padrão. SOMENTE LEITURA.

Lê MONGO_URL e DB_NAME das variáveis de ambiente.
Pede as senhas antigas com getpass (não aparecem na tela e não ficam no
código nem no histórico do shell). Para cada conta imprime apenas
"ainda usa senha padrão", "OK" ou "conta não encontrada".
Nunca imprime senha nem hash. Não escreve nada no banco.

Uso:
    python3 backend/scripts/checar_senhas_padrao.py EMAIL [EMAIL ...]

Os e-mails das contas a verificar entram como argumentos; não há lista no
código. Sem argumentos, mostra o uso e sai sem conectar no banco.
"""
import getpass
import os
import sys

from passlib.context import CryptContext
from pymongo import MongoClient
from pymongo.errors import PyMongoError

USO = "Uso: python3 backend/scripts/checar_senhas_padrao.py EMAIL [EMAIL ...]"


def main() -> int:
    contas = [a.strip() for a in sys.argv[1:] if a.strip()]
    if not contas or any(a in ("-h", "--help") for a in contas):
        print(USO, file=sys.stderr)
        return 2

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    faltando = [n for n, v in (("MONGO_URL", mongo_url), ("DB_NAME", db_name)) if not v]
    if faltando:
        print(f"Erro: defina as variáveis de ambiente: {', '.join(faltando)}", file=sys.stderr)
        return 2

    senhas = {}
    for email in contas:
        senhas[email] = getpass.getpass(f"Senha antiga de {email} (Enter para pular): ")

    kwargs = {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000}
    if mongo_url.startswith("mongodb+srv://") or "mongodb.net" in mongo_url:
        kwargs["tls"] = True

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    try:
        client = MongoClient(mongo_url, **kwargs)
        try:
            users = client[db_name].users
            for email in contas:
                if not senhas[email]:
                    print(f"{email}: pulado")
                    continue
                doc = users.find_one({"email": email}, {"_id": 0, "password": 1})
                if not doc or not doc.get("password"):
                    print(f"{email}: conta não encontrada")
                    continue
                try:
                    igual = pwd.verify(senhas[email], doc["password"])
                except (ValueError, TypeError):
                    igual = False
                print(f"{email}: {'ainda usa senha padrão' if igual else 'OK'}")
        finally:
            client.close()
    except PyMongoError as exc:
        print(f"Erro ao consultar o banco ({type(exc).__name__}).", file=sys.stderr)
        return 1
    finally:
        senhas.clear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
