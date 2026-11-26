"""Cobrança no caixa: totais, desconto por item, cortesia por quantidade,
promoção gerencial e pagamento parcial.

Só funções puras (sem banco): quem chama lê o pedido, aplica a mudança na cópia
e grava. Valores em centavos para não errar no arredondamento.

Regras:
- `unit_price` é sempre o preço COBRADO por unidade. Desconto e cortesia guardam
  o preço original no item, então todas as somas antigas (subtotal, relatórios,
  ranking) continuam certas sem mudança.
- Os 10% de serviço (só salão) saem do valor cobrado, já sem cortesia e desconto.
  Delivery, pedido online e NostFood nunca têm 10%.
- Item cancelado não soma.
- Desconto não é cortesia: cada um tem seu total no pedido
  (`item_discount_total` e `item_courtesy_total`).
- Promoção (promotions.py) é gravada no item quando ele é lançado
  (`promo_*`) e fica nele mesmo que a promoção acabe depois. Tem seu próprio
  total (`item_promo_total`), separado do desconto manual e da cortesia.
- Desconto manual não acumula com promoção: vale o maior. Os dois são medidos
  sobre o preço cheio (`promo_original_price`).
- Unidades já pagas (pagamento parcial por item) não recebem desconto,
  cortesia nem cancelamento, e o total nunca fica abaixo do que já foi pago.
"""
import copy
import uuid
from decimal import Decimal, ROUND_HALF_UP

SERVICE_FEE_DEFAULT = 10
CASHIER_MAX_DISCOUNT_PCT = 10  # acima disso só admin
DISCOUNT_FIELDS = (
    "discount_original_price", "discount_type", "discount_value", "discount_pct",
    "discount_reason", "discount_by_id", "discount_by_name", "discount_approved_by_id",
    "discount_approved_by_name", "discount_at",
)
COURTESY_AUDIT_FIELDS = ("courtesy_by_id", "courtesy_by_name", "courtesy_at")
PROMO_FIELDS = ("promo_id", "promo_name", "promo_original_price", "promo_price", "promo_type", "promo_value")


class BillingError(ValueError):
    """Erro de regra; a mensagem vai para o usuário. status_code: 400, 403 ou 409."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def cents(value) -> int:
    """Centavos com o mesmo arredondamento do fechamento (round(x * 100))."""
    return round(float(value or 0) * 100)


def money(value_cents: int) -> float:
    return round(value_cents / 100, 2)


def brl(value_cents: int) -> str:
    return f"R$ {value_cents / 100:.2f}".replace(".", ",")


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- totais
def is_salon(order: dict) -> bool:
    """Pedido do salão (mesa/comanda). Online, delivery e NostFood não são."""
    return not (
        order.get("source") == "online"
        or order.get("external_source")
        or order.get("delivery_type")
    )


def service_fee_pct(order: dict) -> float:
    if not is_salon(order):
        return 0.0
    pct = order.get("service_fee_percentage", SERVICE_FEE_DEFAULT)
    return float(SERVICE_FEE_DEFAULT if pct is None else pct)


def fee_cents(base_cents: int, pct: float) -> int:
    return _round_half_up(Decimal(base_cents) * Decimal(str(pct)) / Decimal(100))


def active_items(order: dict):
    return [i for i in order.get("items") or [] if i.get("status") != "cancelled"]


def qty(item: dict) -> int:
    return int(item.get("quantity") or 0)


def paid_qty(item: dict) -> int:
    return int(item.get("paid_quantity") or 0)


def line_cents(item: dict) -> int:
    return cents(item.get("unit_price")) * qty(item)


def line_discount_cents(item: dict) -> int:
    if item.get("is_courtesy") or item.get("discount_original_price") is None:
        return 0
    return max(0, cents(item["discount_original_price"]) - cents(item.get("unit_price"))) * qty(item)


def has_promo(item: dict) -> bool:
    return bool(item.get("promo_id")) and item.get("promo_price") is not None


def line_promo_cents(item: dict) -> int:
    """Desconto da promoção na linha. Sai quando um desconto manual maior a substitui."""
    if not has_promo(item) or item.get("discount_original_price") is not None:
        return 0
    return max(0, cents(item.get("promo_original_price")) - cents(item.get("promo_price"))) * qty(item)


def full_price_cents(item: dict) -> int:
    """Preço cheio por unidade (antes de promoção e de desconto manual)."""
    if has_promo(item):
        return cents(item.get("promo_original_price"))
    return cents(item.get("discount_original_price", item.get("unit_price")))


def base_price(item: dict) -> float:
    """Preço por unidade sem o desconto manual (com a promoção, se houver)."""
    if has_promo(item):
        return float(item["promo_price"])
    original = item.get("discount_original_price")
    return float(original if original is not None else item.get("unit_price") or 0)


def line_courtesy_cents(item: dict) -> int:
    if not item.get("is_courtesy"):
        return 0
    return cents(item.get("courtesy_original_price")) * qty(item)


def totals(order: dict) -> dict:
    """Campos de total recalculados, prontos para `$set`."""
    items = active_items(order)
    subtotal = sum(line_cents(i) for i in items)
    pct = service_fee_pct(order)
    fee = fee_cents(subtotal, pct)
    delivery = cents(order.get("delivery_fee"))
    order_discount = cents(order.get("discount"))  # desconto do pedido inteiro (NostFood)
    total = max(0, subtotal + fee + delivery - order_discount)
    return {
        "subtotal": money(subtotal),
        "service_fee": money(fee),
        "service_fee_percentage": pct,
        "total": money(total),
        "item_discount_total": money(sum(line_discount_cents(i) for i in items)),
        "item_courtesy_total": money(sum(line_courtesy_cents(i) for i in items)),
        "item_promo_total": money(sum(line_promo_cents(i) for i in items)),
    }


def paid_cents(order: dict) -> int:
    return cents(order.get("paid_amount"))


def remaining_cents(order: dict) -> int:
    return cents(order.get("total")) - paid_cents(order)


def ensure_total_covers_paid(order: dict, new_totals: dict) -> None:
    paid = paid_cents(order)
    if cents(new_totals["total"]) < paid:
        raise BillingError(
            f"O novo total ficaria menor que o já pago ({brl(paid)}). Estorne um pagamento antes.", 409)


# ------------------------------------------------------------ itens
def find_index(order: dict, item_id: str) -> int:
    for i, item in enumerate(order.get("items") or []):
        if item.get("id") == item_id:
            return i
    raise BillingError("Item não encontrado", 404)


def ensure_editable(order: dict) -> None:
    if order.get("is_closed"):
        raise BillingError("Comanda já fechada")
    if order.get("status") == "cancelled":
        raise BillingError("Comanda cancelada")


def ensure_salon_billing(order: dict) -> None:
    """Desconto e pagamento parcial só em comanda/mesa do salão."""
    if order.get("source") == "online" or order.get("external_source"):
        raise BillingError("Pedido online/NostFood não aceita esta operação no caixa", 409)
    if order.get("is_comp"):
        raise BillingError("Pedido inteiro já está em cortesia/permuta", 409)


def parse_quantity(value, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise BillingError("Quantidade inválida")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BillingError("Quantidade inválida")
    if number != float(value):
        raise BillingError("Quantidade inválida")
    return number


def take_units(order: dict, item_id: str, quantity) -> dict:
    """Separa `quantity` unidades NÃO pagas da linha e devolve a linha delas.

    Se for a linha inteira, devolve a própria linha. Senão divide: a linha
    original fica com o resto (e com as unidades já pagas) e uma linha nova,
    logo abaixo, recebe as unidades separadas.
    """
    items = order["items"]
    idx = find_index(order, item_id)
    item = items[idx]
    if item.get("status") == "cancelled":
        raise BillingError("Item cancelado")
    total = qty(item)
    free = total - paid_qty(item)
    n = parse_quantity(quantity, total)
    if n <= 0:
        raise BillingError("Quantidade deve ser maior que zero")
    if n > total:
        raise BillingError("Quantidade maior que a da linha")
    if n > free:
        raise BillingError(f"Só {free} unidade(s) desta linha ainda não foram pagas")
    if n == total:
        return item
    item["quantity"] = total - n
    new = copy.deepcopy(item)
    new["id"] = str(uuid.uuid4())
    new["quantity"] = n
    new["paid_quantity"] = 0
    new["split_from"] = item["id"]
    items.insert(idx + 1, new)
    return new


def _author(user: dict, prefix: str, now_iso: str) -> dict:
    return {f"{prefix}_by_id": user.get("id"), f"{prefix}_by_name": user.get("name"), f"{prefix}_at": now_iso}


def _clear_discount(item: dict) -> None:
    for key in DISCOUNT_FIELDS:
        item.pop(key, None)


# --------------------------------------------------------- cortesia
def mark_courtesy(order: dict, item_id: str, quantity, reason: str, user: dict, now_iso: str) -> dict:
    """Marca `quantity` unidades como cortesia (preço zero, continua baixando estoque)."""
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Informe o motivo da cortesia")
    item = order["items"][find_index(order, item_id)]
    if item.get("is_courtesy"):
        # Já é cortesia: só atualiza o motivo, sem perder o preço guardado.
        item["courtesy_reason"] = reason
        item.update(_author(user, "courtesy", now_iso))
        return item
    target = take_units(order, item_id, quantity)
    # Item com desconto manual: o desconto sai e a cortesia guarda o preço sem
    # ele (o cheio, ou o da promoção, que continua no item e no relatório).
    target["courtesy_original_price"] = base_price(target)
    _clear_discount(target)
    target["unit_price"] = 0
    target["is_courtesy"] = True
    target["courtesy_reason"] = reason
    target.update(_author(user, "courtesy", now_iso))
    return target


def unmark_courtesy(item: dict, fallback_price) -> dict:
    """Desmarca: volta o preço guardado (regra do PR #8); sem preço guardado usa o cadastro."""
    if not item.get("is_courtesy"):
        item["is_courtesy"] = False
        item["courtesy_reason"] = None
        return item
    original = item.get("courtesy_original_price")
    if original is None:
        if fallback_price is None:
            raise BillingError("Preço original do item não encontrado", 409)
        original = fallback_price
    item["unit_price"] = float(original or 0)
    item.pop("courtesy_original_price", None)
    for key in COURTESY_AUDIT_FIELDS:
        item.pop(key, None)
    item["is_courtesy"] = False
    item["courtesy_reason"] = None
    return item


_MERGE_KEYS = ("product_id", "status", "stock_deducted", "promo_id", "notes", "type")


def merge_back(order: dict, item: dict) -> dict:
    """Depois de desfazer cortesia/desconto, junta a linha de volta à linha de origem
    (ex.: 2 + 1 volta a ser 3) quando as duas ficaram iguais. Senão não mexe."""
    origin_id = item.get("split_from")
    if not origin_id or paid_qty(item):
        return item
    origin = next((i for i in order.get("items") or [] if i.get("id") == origin_id), None)
    if (origin is None or origin.get("status") == "cancelled" or origin.get("is_courtesy")
            or item.get("is_courtesy") or origin.get("discount_original_price") is not None
            or item.get("discount_original_price") is not None
            or cents(origin.get("unit_price")) != cents(item.get("unit_price"))
            or any(origin.get(k) != item.get(k) for k in _MERGE_KEYS)):
        return item
    origin["quantity"] = qty(origin) + qty(item)
    order["items"] = [i for i in order["items"] if i is not item]
    return origin


# --------------------------------------------------------- desconto
def discounted_unit_cents(original_cents: int, kind: str, value) -> int:
    """Preço por unidade depois do desconto (R$ por unidade ou %)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BillingError("Valor do desconto inválido")
    if value != value or value in (float("inf"), float("-inf")):
        raise BillingError("Valor do desconto inválido")
    if value <= 0:
        raise BillingError("O desconto deve ser maior que zero")
    if kind == "percent":
        if value >= 100:
            raise BillingError("Desconto de 100% é cortesia: use Cortesia")
        off = _round_half_up(Decimal(original_cents) * Decimal(str(value)) / Decimal(100))
    elif kind == "value":
        off = cents(value)
    else:
        raise BillingError("Tipo de desconto inválido (use 'value' ou 'percent')")
    if off <= 0:
        raise BillingError("Desconto menor que R$ 0,01")
    if off >= original_cents:
        raise BillingError("Desconto igual ou maior que o preço: use Cortesia")
    return original_cents - off


def discount_pct(original_cents: int, unit_cents: int) -> float:
    if original_cents <= 0:
        return 0.0
    return round((original_cents - unit_cents) * 100 / original_cents, 2)


def preview_discount(order: dict, item_id: str, kind: str, value) -> float:
    """% equivalente do desconto pedido, sobre o preço cheio (para decidir se precisa de admin)."""
    item = order["items"][find_index(order, item_id)]
    original = full_price_cents(item)
    return discount_pct(original, discounted_unit_cents(original, kind, value))


def apply_discount(order: dict, item_id: str, quantity, kind: str, value, reason: str,
                   user: dict, approver: dict, now_iso: str) -> tuple:
    """Aplica o desconto manual. Devolve (linha, aviso ou None).

    Não acumula com promoção: se a promoção já dá desconto igual ou maior, recusa
    (409: vale a promoção); se o manual for maior, ele substitui a promoção na
    linha e o aviso diz isso.
    """
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Informe o motivo do desconto")
    item = order["items"][find_index(order, item_id)]
    if item.get("is_courtesy"):
        raise BillingError("Item em cortesia não recebe desconto")
    if item.get("status") == "cancelled":
        raise BillingError("Item cancelado")
    original_c = full_price_cents(item)
    if original_c <= 0:
        raise BillingError("Item sem preço não recebe desconto")
    unit_c = discounted_unit_cents(original_c, kind, value)
    warning = None
    if has_promo(item):
        promo_c = cents(item.get("promo_price"))
        if promo_c <= unit_c:
            raise BillingError(
                f"O desconto não acumula com a Promoção: {item.get('promo_name')} "
                f"({discount_pct(original_c, promo_c):g}%), que já é igual ou maior. Vale a promoção.", 409)
        warning = (f"O desconto não acumula com a Promoção: {item.get('promo_name')}. "
                   "Vale o desconto manual, que é maior.")
    target = take_units(order, item_id, quantity)
    target["discount_original_price"] = money(original_c)
    target["unit_price"] = money(unit_c)
    target["discount_type"] = kind
    target["discount_value"] = float(value)
    target["discount_pct"] = discount_pct(original_c, unit_c)
    target["discount_reason"] = reason
    target.update(_author(user, "discount", now_iso))
    if approver and approver.get("id") != user.get("id"):
        target["discount_approved_by_id"] = approver.get("id")
        target["discount_approved_by_name"] = approver.get("name")
    else:
        target.pop("discount_approved_by_id", None)
        target.pop("discount_approved_by_name", None)
    return target, warning


def remove_discount(order: dict, item_id: str) -> dict:
    """Tira o desconto manual. Item lançado na promoção volta ao preço da promoção."""
    item = order["items"][find_index(order, item_id)]
    if item.get("discount_original_price") is None:
        raise BillingError("Item não tem desconto")
    if paid_qty(item):
        raise BillingError("Linha com unidades já pagas: estorne o pagamento antes de tirar o desconto", 409)
    restored = base_price(item)  # antes de limpar: usa discount_original_price
    _clear_discount(item)
    item["unit_price"] = restored
    return item


# ------------------------------------------------- pagamento parcial
def items_share_cents(order: dict, selections) -> tuple:
    """Valor de itens escolhidos (com os 10% do salão). Devolve (centavos, [{item_id, quantity}])."""
    if not isinstance(selections, list) or not selections:
        raise BillingError("Escolha ao menos um item")
    wanted = {}
    for sel in selections:
        if not isinstance(sel, dict) or not sel.get("item_id"):
            raise BillingError("Item inválido")
        n = parse_quantity(sel.get("quantity"), 0)
        if n <= 0:
            raise BillingError("Quantidade deve ser maior que zero")
        wanted[sel["item_id"]] = wanted.get(sel["item_id"], 0) + n
    base = 0
    chosen = []
    for item_id, n in wanted.items():
        item = order["items"][find_index(order, item_id)]
        if item.get("status") == "cancelled":
            raise BillingError("Item cancelado não pode ser pago")
        if item.get("is_courtesy") or cents(item.get("unit_price")) <= 0:
            raise BillingError(f"{item.get('product_name') or 'Item'} não tem valor a pagar")
        free = qty(item) - paid_qty(item)
        if n > free:
            raise BillingError(f"{item.get('product_name') or 'Item'}: só {free} unidade(s) sem pagamento")
        base += cents(item.get("unit_price")) * n
        chosen.append({"item_id": item_id, "quantity": n, "product_name": item.get("product_name")})
    return base + fee_cents(base, service_fee_pct(order)), chosen


def mark_items_paid(order: dict, chosen, sign: int = 1) -> None:
    for sel in chosen or []:
        try:
            item = order["items"][find_index(order, sel["item_id"])]
        except BillingError:
            continue  # linha removida: nada a desfazer
        item["paid_quantity"] = max(0, paid_qty(item) + sign * int(sel["quantity"]))


def settle_change(normalized: list, target_cents: int) -> tuple:
    """Tira o troco das linhas em dinheiro, para que os valores gravados somem `target`.

    `normalized` já foi validado (troco só sai de dinheiro). Devolve (linhas, troco).
    """
    lines = [dict(p) for p in normalized]
    change = sum(p["amount_cents"] for p in lines) - target_cents
    left = change
    for p in reversed(lines):
        if left <= 0:
            break
        if p["method"] == "cash":
            used = min(left, p["amount_cents"])
            p["amount_cents"] -= used
            p["change_cents"] = p.get("change_cents", 0) + used
            left -= used
    return [p for p in lines if p["amount_cents"] > 0], change
