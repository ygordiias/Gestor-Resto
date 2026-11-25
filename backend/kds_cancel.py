"""Aviso de cancelado no KDS (Cozinha, Bar e Churrasqueira) para qualquer pedido.

Dois casos:
- Pedido inteiro cancelado (salão, balcão, online ou NostFood): o pedido ganha
  kds_ack_pending=True e cancel_acks={}; cada tela mostra o card inteiro cancelado
  com os seus itens até tocar em "Ciente".
- Item cancelado num pedido que continua aberto: o item ganha kds_item_cancel=True,
  kds_ack_pending=True e cancel_acks={}; o pedido ganha kds_item_cancel_pending=True
  e kds_item_cancel_at. A tela do item mostra o item cancelado até tocar em "Ciente".

O aviso sai da tela de cada estação quando ela toca em "Ciente". Cozinha (itens
"food") e bar (itens "drink") são obrigatórias: depois das duas, o aviso some
também da churrasqueira, que é só visualização.
Só funções puras: quem chama grava no banco.
"""
from typing import Iterable, List

KDS_STATIONS = ("kitchen", "bar", "grill")
# Itens que ainda aparecem no KDS: só esses geram aviso quando cancelados um a um.
KDS_VISIBLE_STATUSES = ("pending", "preparing", "ready")
_REQUIRED = (("kitchen", "food"), ("bar", "drink"))
_STATION_TYPE = {"kitchen": "food", "bar": "drink", "grill": "food"}


def required_stations(items: Iterable[dict]) -> List[str]:
    types = {i.get("type") for i in items}
    return [s for s, t in _REQUIRED if t in types]


def _effective_status(item: dict):
    return item.get("status_before_cancel") or item.get("status")


def whole_order_items(order: dict) -> List[dict]:
    """Itens do pedido inteiro cancelado (sem os cancelados antes, um a um)."""
    return [i for i in order.get("items") or []
            if not i.get("kds_item_cancel") and _effective_status(i) != "cancelled"]


def order_cancel_fields(order: dict) -> dict:
    """Campos do aviso para um pedido inteiro cancelado (entram no $set)."""
    return {"kds_ack_pending": bool(required_stations(whole_order_items(order))), "cancel_acks": {}}


def mark_item_cancelled(item: dict, previous_status, now_iso: str) -> bool:
    """Marca um item cancelado (pedido aberto) para o aviso. Devolve True se marcou.

    Só avisa se o item ainda estava no KDS (pendente, em preparo ou pronto) e é
    de cozinha ou bar.
    """
    if previous_status not in KDS_VISIBLE_STATUSES or not required_stations([item]):
        return False
    item["status_before_cancel"] = previous_status
    item["kds_item_cancel"] = True
    item["kds_ack_pending"] = True
    item["kds_cancel_at"] = now_iso
    item["cancel_acks"] = {}
    return True


def item_cancel_pending(order: dict) -> bool:
    return any(i.get("kds_item_cancel") and i.get("kds_ack_pending") for i in order.get("items") or [])


def apply_ack(order: dict, station: str, by: dict) -> dict:
    """"Ciente" de uma tela: vale para o pedido inteiro cancelado e para os itens
    cancelados da tela. Altera `order` e devolve o $set."""
    station_type = _STATION_TYPE[station]
    update = {}
    if order.get("status") == "cancelled":
        acks = order.get("cancel_acks") or {}
        acks[station] = by
        order["cancel_acks"] = acks
        update["cancel_acks"] = acks
        items = whole_order_items(order)
        update["kds_ack_pending"] = any(s not in acks for s in required_stations(items))
        order["kds_ack_pending"] = update["kds_ack_pending"]
    touched = False
    for item in order.get("items") or []:
        if not (item.get("kds_item_cancel") and item.get("kds_ack_pending")):
            continue
        if item.get("type") != station_type:
            continue
        acks = item.get("cancel_acks") or {}
        acks[station] = by
        item["cancel_acks"] = acks
        item["kds_ack_pending"] = any(s not in acks for s in required_stations([item]))
        touched = True
    if touched:
        update["items"] = order["items"]
        update["kds_item_cancel_pending"] = item_cancel_pending(order)
        order["kds_item_cancel_pending"] = update["kds_item_cancel_pending"]
    return update
