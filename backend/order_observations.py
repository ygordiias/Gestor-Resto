"""Observação nova para o KDS em QUALQUER pedido (mesa, comanda, balcão, online, NostFood).

Uma observação vale para um item ou para o pedido inteiro e aparece só nas telas
desse item (ou dos itens do pedido): cozinha e churrasqueira para comida, bar para
bebida. Cada tela confirma a sua ("Ciente"); o Ciente de uma tela não apaga o
aviso das outras.
Só funções puras: quem chama grava no banco e avisa o tempo real.
"""
import uuid
from typing import Optional

from kds_cancel import KDS_STATIONS

MAX_TEXT = 500
# Telas de cada tipo de item. A churrasqueira mostra comida (ela mesma filtra
# os itens que não são dela).
TYPE_STATIONS = {"food": ("kitchen", "grill"), "drink": ("bar",)}
# Itens que ainda aparecem no KDS.
KDS_VISIBLE_STATUSES = ("pending", "preparing", "ready")


class ObservationError(ValueError):
    """Erro de validação; a mensagem vai para o usuário."""


def stations_for(items) -> list:
    found = set()
    for item in items:
        found.update(TYPE_STATIONS.get(item.get("type"), ()))
    return [s for s in KDS_STATIONS if s in found]


def build(order: dict, body: dict, author: dict, now_iso: str) -> dict:
    """Valida e monta a observação. Levanta ObservationError com a mensagem."""
    body = body if isinstance(body, dict) else {}
    text = str(body.get("text") or "").strip()
    if not text:
        raise ObservationError("Escreva a observação")
    if len(text) > MAX_TEXT:
        raise ObservationError(f"Observação muito longa (máximo {MAX_TEXT} caracteres)")
    if order.get("is_closed") or order.get("status") == "cancelled":
        raise ObservationError("Pedido já finalizado")

    item_id: Optional[str] = body.get("item_id") or None
    items = [i for i in order.get("items") or [] if i.get("status") != "cancelled"]
    item = None
    if item_id:
        item = next((i for i in order.get("items") or [] if i.get("id") == item_id), None)
        if not item:
            raise ObservationError("Item não encontrado no pedido")
        if item.get("status") not in KDS_VISIBLE_STATUSES:
            raise ObservationError("Item já entregue ou cancelado: a cozinha e o bar não o mostram mais")
        targets = [item]
    else:
        targets = items
    stations = stations_for(targets)
    if not stations:
        raise ObservationError("Nenhum item deste pedido vai para a cozinha ou o bar")

    return {
        "id": str(uuid.uuid4()),
        "text": text,
        "item_id": item["id"] if item else None,
        "item_name": item.get("product_name") if item else None,
        "item_type": item.get("type") if item else None,
        "stations": stations,
        "author_id": author.get("id"),
        "author_name": author.get("name"),
        "created_at": now_iso,
        "acks": {},
    }


def apply_ack(observation: dict, station: str, by: dict) -> None:
    """Ciente de uma tela. Observações antigas (sem "stations") valem para todas."""
    stations = observation.get("stations")
    if stations is not None and station not in stations:
        raise ObservationError("Esta observação não é desta tela")
    observation.setdefault("acks", {})[station] = by
