#!/usr/bin/env python3
"""Prepara o banco LOCAL de teste com o cardápio da produção e cria um admin.

Origem (somente leitura): MONGO_URL e DB_NAME lidos do arquivo .env
(padrão: backend/.env; outro arquivo com --env). Na origem o script só faz
find/count: nunca grava, apaga nem cria índices. A URL nunca é impressa.

Destino (fixo): mongodb://localhost:27017 / gestor_resto_teste. O script aborta
se o destino não for localhost ou se origem e destino forem o mesmo banco.

Copia apenas o cardápio e a configuração:
    products, categories, recipes, production_recipes, technical_sheets,
    stock, settings
Nada de pedidos, caixa, pagamentos, notas ou usuários. Cada coleção copiada
é esvaziada no destino e recebe a cópia (mesmos _id).

Depois cria (ou atualiza a senha/perfil de) um usuário no banco local, com o
e-mail passado por argumento e a senha digitada no terminal (sem eco).

Uso:
    python backend/scripts/preparar_banco_teste.py --email voce@exemplo.com --dry-run
    python backend/scripts/preparar_banco_teste.py --email voce@exemplo.com
"""
import argparse
import getpass
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import PyMongoError

DESTINO_URL = "mongodb://localhost:27017"
DESTINO_DB = "gestor_resto_teste"
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}

COLECOES = [
    "products",
    "categories",
    "recipes",
    "production_recipes",
    "technical_sheets",
    "stock",
    "settings",
]

MIN_SENHA = 12
LOTE = 500
ENV_PADRAO = Path(__file__).resolve().parent.parent / ".env"


def erro(msg: str) -> int:
    print(f"ERRO: {msg}", file=sys.stderr)
    return 1


def hosts_da_url(url: str) -> set:
    """Hosts de uma URL mongodb:// (aceita lista host1,host2). Sem credenciais."""
    netloc = urlsplit(url).netloc.rsplit("@", 1)[-1]
    hosts = set()
    for parte in netloc.split(","):
        parte = parte.strip()
        if parte.startswith("["):  # IPv6: [::1]:27017
            hosts.add(parte[1:].split("]", 1)[0].lower())
        elif parte:
            hosts.add(parte.split(":", 1)[0].lower())
    return hosts


def destino_e_local() -> bool:
    return DESTINO_URL.startswith("mongodb://") and hosts_da_url(DESTINO_URL) <= HOSTS_LOCAIS


def ler_origem(env_path: Path):
    if not env_path.is_file():
        return None, None, f"arquivo {env_path} não encontrado (precisa de MONGO_URL e DB_NAME da produção)."
    valores = dotenv_values(env_path)
    url = (valores.get("MONGO_URL") or "").strip()
    db = (valores.get("DB_NAME") or "").strip()
    faltando = [n for n, v in (("MONGO_URL", url), ("DB_NAME", db)) if not v]
    if faltando:
        return None, None, f"{env_path} sem {', '.join(faltando)}."
    return url, db, None


def mesmo_banco(origem_url: str, origem_db: str) -> bool:
    return origem_db == DESTINO_DB and hosts_da_url(origem_url) <= HOSTS_LOCAIS


def pedir_senha() -> str:
    senha = getpass.getpass(f"Senha do admin local (mínimo {MIN_SENHA} caracteres): ")
    if len(senha) < MIN_SENHA:
        raise ValueError(f"senha com menos de {MIN_SENHA} caracteres.")
    if getpass.getpass("Repita a senha: ") != senha:
        raise ValueError("as senhas não conferem.")
    return senha


def copiar_colecao(origem_db, destino_db, nome: str) -> int:
    destino = destino_db[nome]
    destino.delete_many({})
    total = 0
    lote = []
    for doc in origem_db[nome].find({}):
        lote.append(doc)
        if len(lote) >= LOTE:
            destino.insert_many(lote, ordered=False)
            total += len(lote)
            lote = []
    if lote:
        destino.insert_many(lote, ordered=False)
        total += len(lote)
    return total


def gravar_admin(destino_db, email: str, nome: str, perfil: str, senha: str) -> str:
    from passlib.context import CryptContext

    hash_senha = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(senha)
    agora = datetime.now(timezone.utc).isoformat()
    resultado = destino_db.users.update_one(
        {"email": email},
        {
            "$set": {"password": hash_senha, "role": perfil, "is_active": True},
            "$setOnInsert": {"id": str(uuid.uuid4()), "name": nome, "email": email, "created_at": agora},
        },
        upsert=True,
    )
    return "criado" if resultado.upserted_id is not None else "atualizado (senha e perfil)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--email", required=True, help="e-mail do admin a criar no banco local")
    ap.add_argument("--nome", default="Admin Teste", help="nome do admin (padrão: Admin Teste)")
    ap.add_argument("--perfil", default="admin", choices=["admin", "superadmin"])
    ap.add_argument("--env", type=Path, default=ENV_PADRAO, help="arquivo .env com MONGO_URL/DB_NAME da produção")
    ap.add_argument("--dry-run", action="store_true", help="só mostra o que faria; não grava nada")
    args = ap.parse_args()

    email = args.email.strip().lower()
    if "@" not in email:
        return erro("e-mail inválido.")

    # 1) Trava do destino: antes de qualquer conexão.
    if not destino_e_local():
        return erro("o destino não é localhost. Abortado.")

    origem_url, origem_db_nome, problema = ler_origem(args.env)
    if problema:
        return erro(problema)
    if mesmo_banco(origem_url, origem_db_nome):
        return erro("origem e destino são o mesmo banco. Abortado.")

    modo = "DRY-RUN (nada será gravado)" if args.dry_run else "EXECUÇÃO"
    print(f"Modo: {modo}")
    print(f"Origem : banco '{origem_db_nome}' (somente leitura; URL omitida)")
    print(f"Destino: {DESTINO_URL} / {DESTINO_DB}")

    senha = None
    if not args.dry_run:
        try:
            senha = pedir_senha()
        except ValueError as exc:
            return erro(str(exc))

    kwargs = {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000}
    if origem_url.startswith("mongodb+srv://") or "mongodb.net" in origem_url:
        kwargs["tls"] = True

    origem_cli = destino_cli = None
    try:
        origem_cli = MongoClient(origem_url, **kwargs)
        destino_cli = MongoClient(DESTINO_URL, serverSelectionTimeoutMS=5000)
        origem_cli.admin.command("ping")
        destino_cli.admin.command("ping")
        origem = origem_cli[origem_db_nome]
        destino = destino_cli[DESTINO_DB]

        print(f"\n{'COLEÇÃO':<20}{'ORIGEM':>8}{'DESTINO HOJE':>14}")
        for nome in COLECOES:
            print(f"{nome:<20}{origem[nome].count_documents({}):>8}{destino[nome].count_documents({}):>14}")

        existe = destino.users.find_one({"email": email}, {"_id": 0, "role": 1})
        acao_admin = "atualizar senha/perfil" if existe else "criar"
        print(f"\nAdmin {email} ({args.perfil}): {acao_admin} no banco local.")

        if args.dry_run:
            print("\nDry-run: nenhuma gravação feita. Rode sem --dry-run para executar.")
            return 0

        print()
        for nome in COLECOES:
            print(f"Copiado {nome}: {copiar_colecao(origem, destino, nome)} documentos")
        print(f"Admin {email}: {gravar_admin(destino, email, args.nome, args.perfil, senha)}")
        print("\nPronto.")
        return 0
    except PyMongoError as exc:
        # Só o tipo do erro: a mensagem pode conter detalhes da conexão.
        return erro(f"falha no banco ({type(exc).__name__}).")
    finally:
        for cli in (origem_cli, destino_cli):
            if cli is not None:
                cli.close()


if __name__ == "__main__":
    sys.exit(main())
