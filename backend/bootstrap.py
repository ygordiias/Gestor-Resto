"""Verificações de startup.

- require_secret_key(): SECRET_KEY obrigatória, sem valor padrão, mínimo de
  32 caracteres. Se faltar ou for curta, o servidor não sobe. Nunca mostra a chave.
- ensure_initial_superadmin(): criação do primeiro superadmin a partir de
  variáveis de ambiente.

Regras do superadmin inicial:
- Se já existir QUALQUER usuário com role "superadmin", não faz nada.
- Caso contrário, lê INITIAL_SUPERADMIN_EMAIL e INITIAL_SUPERADMIN_PASSWORD
  (e, opcional, INITIAL_SUPERADMIN_NAME).
- Variáveis ausentes: registra AVISO e segue (o servidor não pode cair por isso).
- E-mail já cadastrado com outro perfil: registra ERRO e NÃO promove a conta.
- Nunca registra senha nem hash. Nunca derruba o servidor.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

MIN_SECRET_KEY_LENGTH = 32

_SECRET_KEY_HELP = (
    "O servidor não vai iniciar sem ela.\n"
    "Gere uma chave com:\n"
    "    python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
    "e defina SECRET_KEY no ambiente (Render: Environment do serviço backend; "
    "local: backend/.env)."
)


def require_secret_key(env=None) -> str:
    """Devolve SECRET_KEY exatamente como definida, ou encerra o processo.

    Encerra (SystemExit(1)) se faltar, estiver vazia/só espaços ou tiver menos
    de MIN_SECRET_KEY_LENGTH caracteres. A mensagem nunca contém o valor nem
    o tamanho da chave.
    """
    env = os.environ if env is None else env
    key = env.get("SECRET_KEY")

    if key is None or not key.strip():
        problema = "ERRO FATAL: a variável de ambiente SECRET_KEY não está definida."
    elif len(key) < MIN_SECRET_KEY_LENGTH:
        problema = (
            "ERRO FATAL: SECRET_KEY é curta demais "
            f"(mínimo de {MIN_SECRET_KEY_LENGTH} caracteres)."
        )
    else:
        return key

    # Só stderr: roda antes do logging ser configurado, e o Render já
    # captura o stderr nos logs do serviço.
    print(f"{problema}\n{_SECRET_KEY_HELP}", file=sys.stderr)
    raise SystemExit(1)


MIN_PASSWORD_LENGTH = 12

ENV_EMAIL = "INITIAL_SUPERADMIN_EMAIL"
ENV_PASSWORD = "INITIAL_SUPERADMIN_PASSWORD"
ENV_NAME = "INITIAL_SUPERADMIN_NAME"


def _default_hash(password: str) -> str:
    from passlib.context import CryptContext

    return CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)


async def ensure_initial_superadmin(db, logger, env=None, hash_password=None) -> str:
    """Garante o superadmin inicial. Retorna um código do que aconteceu
    (útil para testes): exists | missing_env | invalid_env | email_conflict |
    created | error.
    """
    env = os.environ if env is None else env
    hash_password = hash_password or _default_hash

    try:
        if await db.users.find_one({"role": "superadmin"}, {"_id": 0, "id": 1}):
            logger.info("Superadmin já existe; criação inicial ignorada.")
            return "exists"

        email = (env.get(ENV_EMAIL) or "").strip()
        password = env.get(ENV_PASSWORD) or ""
        name = (env.get(ENV_NAME) or "").strip() or "Super Admin"

        if not email or not password:
            logger.warning(
                "AVISO: nenhum superadmin cadastrado e %s/%s não definidas. "
                "O servidor seguirá sem superadmin. Defina as variáveis e "
                "reinicie para criá-lo.",
                ENV_EMAIL,
                ENV_PASSWORD,
            )
            return "missing_env"

        if "@" not in email or len(password) < MIN_PASSWORD_LENGTH:
            logger.error(
                "ERRO: superadmin inicial NÃO criado: %s inválido ou %s com "
                "menos de %d caracteres.",
                ENV_EMAIL,
                ENV_PASSWORD,
                MIN_PASSWORD_LENGTH,
            )
            return "invalid_env"

        existing = await db.users.find_one({"email": email}, {"_id": 0, "role": 1})
        if existing:
            logger.error(
                "ERRO: superadmin inicial NÃO criado: o e-mail %s já existe com "
                "perfil '%s'. A conta não será promovida automaticamente.",
                email,
                existing.get("role"),
            )
            return "email_conflict"

        result = await db.users.update_one(
            {"email": email},
            {
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "email": email,
                    "role": "superadmin",
                    "is_active": True,
                    "password": hash_password(password),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
        if getattr(result, "upserted_id", None) is None:
            # Outro processo criou o mesmo e-mail entre a checagem e o upsert.
            logger.info("Superadmin inicial já foi criado por outro processo.")
            return "exists"

        logger.info("Superadmin inicial criado: %s", email)
        return "created"
    except Exception as exc:  # nunca derrubar o servidor por causa disto
        logger.error(
            "ERRO ao verificar/criar superadmin inicial (%s). O servidor seguirá.",
            type(exc).__name__,
        )
        return "error"
