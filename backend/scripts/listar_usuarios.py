#!/usr/bin/env python3
"""Lista os usuários do sistema. SOMENTE LEITURA.

Lê MONGO_URL e DB_NAME das variáveis de ambiente (não lê arquivo .env).
Mostra apenas: nome, e-mail, perfil, is_active e data de criação.
Nunca busca nem imprime senha ou hash: a consulta pede só os campos acima.

Uso:
    MONGO_URL=... DB_NAME=... python backend/scripts/listar_usuarios.py
"""
import os
import sys

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Projeção por lista de permissão: só estes campos saem do banco.
CAMPOS = {"_id": 0, "name": 1, "email": 1, "role": 1, "is_active": 1, "created_at": 1}


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
            usuarios = list(
                client[db_name].users.find({}, CAMPOS).sort([("role", 1), ("email", 1)])
            )
        finally:
            client.close()
    except PyMongoError as exc:
        # Só o tipo do erro: a mensagem pode conter detalhes da conexão.
        print(f"Erro ao consultar o banco ({type(exc).__name__}).", file=sys.stderr)
        return 1

    cab = ("NOME", "E-MAIL", "PERFIL", "ATIVO", "CRIADO EM")
    linhas = [
        (
            str(u.get("name", "")),
            str(u.get("email", "")),
            str(u.get("role", "")),
            "sim" if u.get("is_active", True) else "NÃO",
            str(u.get("created_at", ""))[:19],
        )
        for u in usuarios
    ]
    larg = [max(len(c), *(len(l[i]) for l in linhas)) if linhas else len(c) for i, c in enumerate(cab)]
    fmt = "  ".join(f"{{:<{w}}}" for w in larg)
    print(fmt.format(*cab))
    print(fmt.format(*("-" * w for w in larg)))
    for l in linhas:
        print(fmt.format(*l))
    print(f"\nTotal: {len(linhas)} usuário(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
