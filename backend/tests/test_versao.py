# Gestor Restô · criado e desenvolvido por Ygor Dias · Tecno Dias.
"""GET /api/versao: público, sem banco, com autoria e commit (OFFLINE)."""
import sobre
from _offline_app import call


def test_versao_publica_com_autoria(monkeypatch):
    sobre.commit_hash.cache_clear()
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    status, body = call("GET", "/api/versao")
    assert status == 200
    assert body == {
        "sistema": "Gestor Restô",
        "versao": sobre.VERSAO,
        "autor": "Ygor Dias",
        "empresa": "Tecno Dias",
        "commit": "abc123",
    }
    sobre.commit_hash.cache_clear()


def test_commit_sem_variavel_nem_git(monkeypatch):
    sobre.commit_hash.cache_clear()
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)

    def sem_git(*args, **kwargs):
        raise OSError("git ausente")

    monkeypatch.setattr(sobre.subprocess, "run", sem_git)
    assert sobre.commit_hash() == "desconhecido"
    sobre.commit_hash.cache_clear()


def test_autoria_constante():
    assert sobre.AUTORIA == "Ygor Dias — Tecno Dias"
