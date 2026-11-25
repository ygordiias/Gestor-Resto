#!/usr/bin/env python3
# Gestor Restô · criado e desenvolvido por Ygor Dias · Tecno Dias.
"""Exporta o OpenAPI do FastAPI para docs/openapi.json SEM subir servidor.

Não conecta em banco: MONGO_URL aponta para um endereço inexistente só
durante o import (o driver só conecta quando usado e o startup não roda).
SECRET_KEY é gerada na hora e descartada, e CORS_ORIGINS recebe um valor
só para a exportação. Nenhum segredo é lido ou gravado.

Uso (a partir da raiz do repositório):
    python backend/scripts/exportar_openapi.py
    python backend/scripts/exportar_openapi.py --saida outro/caminho.json
"""
import argparse
import json
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RAIZ = BACKEND.parent


def carregar_app():
    os.environ["MONGO_URL"] = "mongodb://127.0.0.1:1"
    os.environ["DB_NAME"] = "exportar_openapi"
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
    # Obrigatória para o server.py subir; só vale durante a exportação.
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"
    sys.path.insert(0, str(BACKEND))
    import server  # noqa: E402

    # server.app é o ASGIApp do Socket.IO; o FastAPI fica em other_asgi_app.
    return server.app.other_asgi_app


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--saida", default=str(RAIZ / "docs" / "openapi.json"))
    args = parser.parse_args()

    spec = carregar_app().openapi()
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI {spec.get('openapi')} com {len(spec.get('paths', {}))} caminhos gravado em {saida}")


if __name__ == "__main__":
    main()
