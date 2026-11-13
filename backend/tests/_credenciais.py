"""Credenciais dos testes de INTEGRAÇÃO (que usam o servidor rodando).

Nenhuma senha fica no repositório. Cada perfil lê do ambiente:
    TEST_ADMIN_EMAIL    / TEST_ADMIN_PASSWORD
    TEST_WAITER_EMAIL   / TEST_WAITER_PASSWORD
    TEST_CASHIER_EMAIL  / TEST_CASHIER_PASSWORD
    TEST_BAR_EMAIL      / TEST_BAR_PASSWORD
Use sempre contas de um banco de TESTE. Se faltar alguma variável, o arquivo
de teste inteiro é pulado (skip) com a lista do que falta.
"""
import os

import pytest


def credencial(papel: str) -> dict:
    p = papel.upper()
    email = os.environ.get(f"TEST_{p}_EMAIL")
    senha = os.environ.get(f"TEST_{p}_PASSWORD")
    faltando = [n for n, v in ((f"TEST_{p}_EMAIL", email), (f"TEST_{p}_PASSWORD", senha)) if not v]
    if faltando:
        pytest.skip(f"defina {', '.join(faltando)} (conta de banco de TESTE) para rodar este teste",
                    allow_module_level=True)
    return {"email": email, "password": senha}
