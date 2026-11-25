# Gestor Restô · criado e desenvolvido por Ygor Dias · Tecno Dias.
# Copyright (c) 2026 Ygor Dias — Tecno Dias. Todos os direitos reservados.
"""Identificação do sistema: nome, versão, autoria e commit em execução.

Usado por GET /api/versao. Não lê banco nem segredo.

O hash do commit vem, nesta ordem:
  1. RENDER_GIT_COMMIT (definida pelo próprio Render em cada deploy);
  2. GIT_COMMIT (para outros ambientes);
  3. `git rev-parse HEAD` na pasta do projeto (ambiente local);
  4. "desconhecido".
"""
import os
import subprocess
from functools import lru_cache
from pathlib import Path

SISTEMA = "Gestor Restô"
VERSAO = "1.0.0"
AUTOR = "Ygor Dias"
EMPRESA = "Tecno Dias"
AUTORIA = "Ygor Dias — Tecno Dias"

_ENV_COMMIT = ("RENDER_GIT_COMMIT", "GIT_COMMIT")


@lru_cache(maxsize=1)
def commit_hash() -> str:
    for name in _ENV_COMMIT:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=2, check=False,
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return "desconhecido"


def info() -> dict:
    return {
        "sistema": SISTEMA,
        "versao": VERSAO,
        "autor": AUTOR,
        "empresa": EMPRESA,
        "commit": commit_hash(),
    }
