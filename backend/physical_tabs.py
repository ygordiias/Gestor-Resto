"""Faixa das comandas físicas: origem única para servidor, script e frontend.

Variáveis de ambiente (opcionais):
    PHYSICAL_TAB_MIN  primeira comanda (padrão 200)
    PHYSICAL_TAB_MAX  última comanda   (padrão 291)

O frontend lê a faixa em GET /api/tabs/config: nenhum número fica fixo nele.
Valor inválido (não inteiro, menor que 1 ou MAX < MIN) volta ao padrão.
"""
import logging
import os

DEFAULT_MIN = 200
DEFAULT_MAX = 291

logger = logging.getLogger(__name__)


def _env_int(name, default):
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r não é um número inteiro; usando %s", name, raw, default)
        return default


def tab_range():
    """(mínimo, máximo) das comandas físicas, inclusive."""
    low = _env_int("PHYSICAL_TAB_MIN", DEFAULT_MIN)
    high = _env_int("PHYSICAL_TAB_MAX", DEFAULT_MAX)
    if low < 1 or high < low:
        logger.warning("Faixa de comandas inválida (%s a %s); usando %s a %s",
                       low, high, DEFAULT_MIN, DEFAULT_MAX)
        return DEFAULT_MIN, DEFAULT_MAX
    return low, high


def in_range(number):
    low, high = tab_range()
    return isinstance(number, int) and low <= number <= high


def out_of_range_message(number):
    low, high = tab_range()
    return f"Comanda {number} fora da faixa permitida ({low} a {high})"


def new_tab_doc(number):
    """Campos gravados só na criação ($setOnInsert): nunca altera comanda existente."""
    return {"number": number, "active_order_id": None, "table_id": None}


async def ensure_tabs(collection):
    """Cria (motor/async) só as comandas da faixa que ainda não existem. Devolve quantas criou."""
    low, high = tab_range()
    created = 0
    for number in range(low, high + 1):
        result = await collection.update_one(
            {"number": number}, {"$setOnInsert": new_tab_doc(number)}, upsert=True)
        if result.upserted_id is not None:
            created += 1
    return created
