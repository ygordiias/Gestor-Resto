"""Etapa 1, item 3: SECRET_KEY obrigatória, sem padrão, mínimo 32 caracteres.

Teste unitário, sem rede e sem MongoDB. Chaves geradas na hora.
Rodar: cd backend && python -m pytest tests/test_secret_key.py
"""
import os
import secrets
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bootstrap import MIN_SECRET_KEY_LENGTH, require_secret_key  # noqa: E402

OLD_DEFAULT_LENGTH = 29  # tamanho do antigo valor padrão do código


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"SECRET_KEY": ""},
        {"SECRET_KEY": " " * 40},
        {"SECRET_KEY": "a" * (MIN_SECRET_KEY_LENGTH - 1)},
        {"SECRET_KEY": "b" * OLD_DEFAULT_LENGTH},
    ],
    ids=["ausente", "vazia", "so-espacos", "31-chars", "tamanho-do-padrao-antigo"],
)
def test_invalid_key_stops_server(env, capsys):
    with pytest.raises(SystemExit) as exc:
        require_secret_key(env)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "SECRET_KEY" in err
    assert "token_urlsafe" in err  # diz como gerar


@pytest.mark.parametrize("size", [MIN_SECRET_KEY_LENGTH, 64])
def test_valid_key_returned_unchanged(size):
    key = secrets.token_urlsafe(64)[:size]
    assert require_secret_key({"SECRET_KEY": key}) == key


def test_key_with_spaces_is_not_altered():
    key = " " + secrets.token_urlsafe(48) + " "
    assert require_secret_key({"SECRET_KEY": key}) == key


def test_message_never_contains_key(capsys, caplog):
    short = secrets.token_hex(10)  # 20 caracteres, curta
    with pytest.raises(SystemExit):
        require_secret_key({"SECRET_KEY": short})
    out = capsys.readouterr()
    assert short not in out.err and short not in out.out
    assert short not in caplog.text
    assert str(len(short)) not in out.err
