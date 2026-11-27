"""Promoção gerencial: desconto por regra, criado só por admin.

Só funções puras (sem banco). As rotas ficam no server.py.

Regras:
- A promoção pega categorias e/ou produtos escolhidos, num período (datas de
  início e fim, inclusive), opcionalmente só em alguns dias da semana e numa
  faixa de horário, e só nos canais marcados (salão, balcão, cardápio próprio).
- Nunca vale para NostFood/iFood/99: o preço deles vem da plataforma.
- Vale para o item no momento em que ele é LANÇADO. O item guarda o preço
  cheio, o preço com desconto e o nome da promoção (campos `promo_*`) e fica
  assim mesmo que a promoção acabe ou seja desligada depois.
- Mais de uma promoção para o mesmo item: vale a de maior desconto (não acumula).
- Ligar/desligar não apaga nada; cada mudança fica no `history` da promoção.
- Horário e dia da semana são os do restaurante (America/Sao_Paulo).
"""
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # Windows sem tzdata: o Brasil não tem horário de verão desde 2019
    LOCAL_TZ = timezone(timedelta(hours=-3))

CHANNELS = ("salao", "balcao", "cardapio")
CHANNEL_LABELS = {"salao": "Salão", "balcao": "Balcão", "cardapio": "Cardápio próprio"}
PLATFORM_ONLY = ("ifood", "99food", "99", "nostfood")  # preço vem da plataforma
WEEKDAY_LABELS = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb", 7: "dom"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PromotionError(ValueError):
    """Erro de validação; a mensagem vai para o usuário."""


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ)


def _cents(value) -> int:
    return round(float(value or 0) * 100)


# ------------------------------------------------------------ validação
def _parse_date(value, label):
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise PromotionError(f"{label} inválida (use AAAA-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise PromotionError(f"{label} inválida")


def _id_list(value, label):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise PromotionError(f"{label} inválidos")
    return sorted(set(v.strip() for v in value))


def normalize(data: dict) -> dict:
    """Valida o formulário e devolve só os campos aceitos."""
    if not isinstance(data, dict):
        raise PromotionError("Dados inválidos")
    name = (data.get("name") or "").strip() if isinstance(data.get("name"), str) else ""
    if not name:
        raise PromotionError("Informe o nome da promoção")
    if len(name) > 80:
        raise PromotionError("Nome muito longo (máximo 80 caracteres)")

    kind = data.get("discount_type")
    if kind not in ("percent", "value"):
        raise PromotionError("Tipo de desconto inválido (use 'percent' ou 'value')")
    value = data.get("discount_value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value \
            or value in (float("inf"), float("-inf")):
        raise PromotionError("Valor do desconto inválido")
    if value <= 0:
        raise PromotionError("O desconto deve ser maior que zero")
    if kind == "percent" and value >= 100:
        raise PromotionError("Desconto de 100% ou mais não é promoção")
    if kind == "value" and _cents(value) <= 0:
        raise PromotionError("Desconto menor que R$ 0,01")

    category_ids = _id_list(data.get("category_ids"), "Categorias")
    product_ids = _id_list(data.get("product_ids"), "Produtos")
    if not category_ids and not product_ids:
        raise PromotionError("Escolha ao menos uma categoria ou um produto")

    start = _parse_date(data.get("start_date"), "Data de início")
    end = _parse_date(data.get("end_date"), "Data de fim")
    if end < start:
        raise PromotionError("A data de fim é antes da data de início")

    weekdays = data.get("weekdays") or []
    if not isinstance(weekdays, list) or any(
            isinstance(d, bool) or not isinstance(d, int) or d not in WEEKDAY_LABELS for d in weekdays):
        raise PromotionError("Dias da semana inválidos (1 = segunda ... 7 = domingo)")
    weekdays = sorted(set(weekdays))

    start_time = data.get("start_time") or None
    end_time = data.get("end_time") or None
    if (start_time is None) != (end_time is None):
        raise PromotionError("Informe o horário de início e o de fim (ou nenhum dos dois)")
    if start_time is not None:
        if not (isinstance(start_time, str) and _TIME_RE.match(start_time)
                and isinstance(end_time, str) and _TIME_RE.match(end_time)):
            raise PromotionError("Horário inválido (use HH:MM)")
        if start_time == end_time:
            raise PromotionError("O horário de início e o de fim são iguais")

    channels = data.get("channels")
    if not isinstance(channels, list) or not channels or any(c not in CHANNELS for c in channels):
        raise PromotionError("Escolha os canais: salão, balcão e/ou cardápio próprio")

    return {
        "name": name,
        "discount_type": kind,
        "discount_value": float(value),
        "category_ids": category_ids,
        "product_ids": product_ids,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "weekdays": weekdays,
        "start_time": start_time,
        "end_time": end_time,
        "channels": [c for c in CHANNELS if c in channels],
    }


# ------------------------------------------------------------ vigência
def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _window_day(promo: dict, moment: datetime) -> date:
    """Dia a que o horário pertence. Faixa que passa da meia-noite (ex.: 22h-02h):
    01h de quarta ainda é a faixa de terça."""
    day = moment.date()
    if promo.get("start_time") and promo.get("end_time"):
        start, end = _hm(promo["start_time"]), _hm(promo["end_time"])
        if start > end and moment.time() < end:
            return day - timedelta(days=1)
    return day


def applies_at(promo: dict, moment: datetime) -> bool:
    """A promoção vale neste instante (horário do restaurante)?"""
    if not promo.get("is_active"):
        return False
    moment = moment.astimezone(LOCAL_TZ)
    day = _window_day(promo, moment)
    if not (promo["start_date"] <= day.isoformat() <= promo["end_date"]):
        return False
    if promo.get("weekdays") and day.isoweekday() not in promo["weekdays"]:
        return False
    if promo.get("start_time") and promo.get("end_time"):
        start, end, now = _hm(promo["start_time"]), _hm(promo["end_time"]), moment.time()
        inside = (start <= now < end) if start < end else (now >= start or now < end)
        if not inside:
            return False
    return True


def status(promo: dict, moment: datetime) -> str:
    """desligada | encerrada | agendada | ativa (ativa = dentro do período;
    o horário/dia da semana pode ainda não ter chegado)."""
    today = moment.astimezone(LOCAL_TZ).date().isoformat()
    if not promo.get("is_active"):
        return "desligada"
    if promo["end_date"] < today:
        return "encerrada"
    if promo["start_date"] > today:
        return "agendada"
    return "ativa"


def describe_schedule(promo: dict) -> str:
    days = ", ".join(WEEKDAY_LABELS[d] for d in promo.get("weekdays") or []) or "todos os dias"
    hours = (f" das {promo['start_time']} às {promo['end_time']}"
             if promo.get("start_time") and promo.get("end_time") else "")
    return f"{days}{hours}"


# ------------------------------------------------------------ canal e preço
def order_channel(order: dict):
    """Canal do pedido para promoção, ou None quando a promoção nunca vale."""
    if order.get("external_source"):
        return None  # NostFood (iFood/99)
    platform = (order.get("platform") or "").lower()
    if platform in PLATFORM_ONLY:
        return None
    if order.get("source") == "online":
        if order.get("origin") == "web":
            return "cardapio"
        return "balcao" if platform == "other" else None
    return "salao"


def covers(promo: dict, product: dict) -> bool:
    return (product.get("id") in (promo.get("product_ids") or [])
            or (product.get("category_id") and product.get("category_id") in (promo.get("category_ids") or [])))


def promo_price_cents(promo: dict, price_cents: int):
    """Preço por unidade com a promoção, ou None se não dá desconto válido."""
    if price_cents <= 0:
        return None
    if promo["discount_type"] == "percent":
        off = int((Decimal(price_cents) * Decimal(str(promo["discount_value"])) / Decimal(100))
                  .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        off = _cents(promo["discount_value"])
    if off <= 0 or off >= price_cents:
        return None  # sem desconto, ou zeraria o item (isso é cortesia)
    return price_cents - off


def best_for(promos, product: dict, price_cents: int, channel: str, moment: datetime):
    """A promoção de MAIOR desconto que vale para o produto agora. (promo, preço) ou None."""
    if not channel or not product:
        return None
    best = None
    for promo in promos:
        if channel not in (promo.get("channels") or []) or not covers(promo, product):
            continue
        if not applies_at(promo, moment):
            continue
        price = promo_price_cents(promo, price_cents)
        if price is None:
            continue
        if best is None or price < best[1] or (price == best[1] and promo["name"] < best[0]["name"]):
            best = (promo, price)
    return best


def apply_to_item(item: dict, promo: dict, price_cents: int) -> dict:
    """Grava a promoção no item lançado (preço cheio, preço com desconto e nome)."""
    original = float(item.get("unit_price") or 0)
    item["promo_id"] = promo["id"]
    item["promo_name"] = promo["name"]
    item["promo_type"] = promo["discount_type"]
    item["promo_value"] = promo["discount_value"]
    item["promo_original_price"] = original
    item["promo_price"] = round(price_cents / 100, 2)
    item["unit_price"] = item["promo_price"]
    return item
