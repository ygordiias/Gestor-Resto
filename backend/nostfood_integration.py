"""Integração com a NostFood (pedidos do iFood e da 99).

Rotas em /api/integrations/nostfood. O módulo reaproveita do server.py o banco,
o Socket.IO, a baixa e a devolução de estoque (ficha técnica) e os perfis.
O server.py só registra o módulo e chama os ganchos.

Variáveis de ambiente (nenhuma chave no código):
  NOSTFOOD_ENABLED         "true" liga webhook, polling e status de volta (padrão: false)
  NOSTFOOD_API_KEY         chave da API (header X-API-Key)
  NOSTFOOD_WEBHOOK_SECRET  segredo do HMAC do webhook
  NOSTFOOD_BASE_URL        padrão https://nostfood.com/api/public
  NOSTFOOD_POLL_SECONDS    intervalo do polling de segurança (padrão 90)
  NOSTFOOD_SEND_STATUS     "true" envia em_preparo/pronto para a NostFood (padrão: false,
                           só registra no log o que teria enviado)

Coleções novas: nostfood_events (TTL de 30 dias), nostfood_product_map,
nostfood_unlinked, nostfood_tombstones, nostfood_settings e stock_losses.
Nenhuma coleção existente foi renomeada.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("nostfood")

SOURCE = "nostfood"
DEFAULT_BASE_URL = "https://nostfood.com/api/public"
HTTP_TIMEOUT_SECONDS = 8.0

# Pagos online: repasse pendente da plataforma, NÃO é dinheiro do caixa.
ONLINE_PAID_METHODS = {
    "pix_online", "cartao_credito_online", "cartao_debito_online",
    "mercadopago_online", "pago_online",
}
CANCEL_STATUSES = {"cancelado", "cancelada", "rejeitado", "rejeitada", "cancelled", "canceled", "rejected"}
# Status da NostFood -> status dos itens no Gestor ao importar.
# Pedido que já chega pronto/saindo/entregue vai direto para o histórico:
# não toca som nem aparece como novo no KDS.
PREPARING_STATUSES = {"em_preparo", "preparando"}
DONE_STATUSES = {"pronto", "saiu_entrega", "enviado", "entregue"}
DELIVERED_STATUSES = {"entregue"}
EVENTS_TTL_SECONDS = 2592000  # 30 dias
STARTED_ITEM_STATUSES = {"preparing", "ready", "delivered"}
KDS_STATIONS = ("kitchen", "bar", "grill")
CANCEL_KDS_WINDOW_HOURS = 12

try:
    from zoneinfo import ZoneInfo
    SP_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos no sistema: Brasil não tem horário de verão desde 2019
    SP_TZ = timezone(timedelta(hours=-3))

# Preenchido por register(): o módulo server (lido sempre na hora da chamada,
# para os testes poderem trocar server.db, server.sio etc.).
S = None
_state = {"indexes_ok": False, "poll_task": None, "last_poll_at": None,
          "last_poll_result": None, "last_poll_error": None}
_locks: dict = {}
_background: set = set()


# ==================== CONFIGURAÇÃO ====================
def enabled() -> bool:
    return os.environ.get("NOSTFOOD_ENABLED", "false").strip().lower() in ("1", "true", "yes", "sim")


def send_status_enabled() -> bool:
    """Só com NOSTFOOD_SEND_STATUS=true o Gestor muda o pedido na NostFood."""
    return os.environ.get("NOSTFOOD_SEND_STATUS", "false").strip().lower() in ("1", "true", "yes", "sim")


def _api_key() -> str:
    return os.environ.get("NOSTFOOD_API_KEY", "").strip()


def _webhook_secret() -> str:
    return os.environ.get("NOSTFOOD_WEBHOOK_SECRET", "").strip()


def _base_url() -> str:
    return (os.environ.get("NOSTFOOD_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")


def poll_seconds() -> int:
    try:
        return max(30, int(os.environ.get("NOSTFOOD_POLL_SECONDS", "90")))
    except ValueError:
        return 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_sp():
    return datetime.now(SP_TZ).date()


# ==================== ASSINATURA ====================
def verify_signature(raw_body: bytes, header_value: Optional[str], secret: str) -> bool:
    """X-NostFood-Signature = "sha256=" + HMAC-SHA256(corpo bruto).

    A documentação não diz se o resultado vem em hex ou em base64; aceita os
    dois, sempre com hmac.compare_digest.
    """
    if not header_value or not secret:
        return False
    provided = header_value.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[7:]
    provided = provided.strip()
    if not provided:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ok_hex = hmac.compare_digest(provided.lower().encode(), digest.hex().encode())
    ok_b64 = hmac.compare_digest(provided.encode(), base64.b64encode(digest))
    return ok_hex or ok_b64


# ==================== NORMALIZAÇÃO (inglês e português) ====================
def _pick(d, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return default


def _num(value, default=0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("R$", "").strip()
            if "," in value and "." in value:
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", ".")
        n = float(value)
        return n if n == n and n not in (float("inf"), float("-inf")) else default
    except (TypeError, ValueError):
        return default


def _qty(value) -> int:
    q = int(round(_num(value, 1)))
    return q if q > 0 else 1


def normalize_name(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def payment_status_for(method) -> str:
    m = str(method or "").strip().lower()
    if m in ONLINE_PAID_METHODS or m.endswith("_online"):
        return "pending_platform"
    return "to_collect"


def _normalize_addons(raw) -> list:
    out = []
    if not raw:
        return out
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return [{"name": str(raw), "quantity": 1, "price": 0.0}]
    for a in raw:
        if isinstance(a, str):
            if a.strip():
                out.append({"name": a.strip(), "quantity": 1, "price": 0.0})
            continue
        if not isinstance(a, dict):
            continue
        # Grupo de opções: {"nome": "Adicionais", "opcoes": [...]}
        nested = _pick(a, "opcoes", "options", "itens", "items")
        if isinstance(nested, list):
            out.extend(_normalize_addons(nested))
            continue
        name = _pick(a, "name", "nome", "descricao", "description", "titulo", "title")
        if not name:
            continue
        out.append({
            "name": str(name),
            "quantity": _qty(_pick(a, "quantity", "quantidade", "qtd", default=1)),
            "price": _num(_pick(a, "price", "preco", "preco_adicional", "valor", default=0)),
        })
    return out


def _normalize_item(raw: dict) -> dict:
    qty = _qty(_pick(raw, "quantity", "quantidade", "qtd", "qty", default=1))
    addons = []
    for key in ("customizations", "adicionais", "complementos", "extras", "addons", "opcoes"):
        addons.extend(_normalize_addons(raw.get(key)))
    price = _num(_pick(raw, "price", "preco", "unit_price", "valor_unitario", "valor", default=0))
    subtotal = _pick(raw, "subtotal", "total", "valor_total")
    if subtotal is not None and _num(subtotal, -1) >= 0:
        unit_price = round(_num(subtotal) / qty, 2)
    else:
        unit_price = round(price + sum(a["price"] * a["quantity"] for a in addons), 2)
    observation = _pick(raw, "observation", "observacao", "observacoes", "obs", "notes", "note", "comentario")
    ext_id = _pick(raw, "product_id", "produto_id", "id")
    return {
        "external_item_id": str(ext_id) if ext_id is not None else None,
        "name": str(_pick(raw, "name", "nome", "product_name", "produto", "descricao", default="Item")),
        "quantity": qty,
        "unit_price": unit_price,
        "observation": str(observation).strip() if observation else None,
        "addons": addons,
    }


def normalize_order(raw: dict) -> dict:
    cliente = raw.get("cliente") if isinstance(raw.get("cliente"), dict) else {}
    customer = raw.get("customer") if isinstance(raw.get("customer"), dict) else {}
    endereco = raw.get("endereco") if isinstance(raw.get("endereco"), dict) else {}

    ext_id = _pick(raw, "id", "pedido_id", "order_id")
    order_number = _pick(raw, "order_number", "numero", "numero_pedido", "codigo")
    street = _pick(raw, "customer_address", "endereco_cliente", default=None)
    if street is None:
        street = raw.get("endereco") if isinstance(raw.get("endereco"), str) else _pick(endereco, "rua", "logradouro", "street")
    address = {
        "street": street,
        "number": _pick(raw, "customer_number", "numero_endereco", default=_pick(endereco, "numero", "number")),
        "complement": _pick(raw, "customer_complemento", "complemento", default=_pick(endereco, "complemento")),
        "neighborhood": _pick(raw, "customer_neighborhood", "bairro", default=_pick(endereco, "bairro")),
        "city": _pick(raw, "customer_city", "cidade", default=_pick(endereco, "cidade")),
        "state": _pick(raw, "customer_state", "estado", "uf", default=_pick(endereco, "estado", "uf")),
        "cep": _pick(raw, "customer_cep", "cep", default=_pick(endereco, "cep")),
    }
    parts = [address["street"], address["number"], address["complement"], address["neighborhood"],
             address["city"], address["state"], address["cep"]]
    address_text = ", ".join(str(p) for p in parts if p) or None

    lat = _pick(raw, "latitude", "lat", default=_pick(endereco, "latitude", "lat"))
    lng = _pick(raw, "longitude", "lng", "lon", default=_pick(endereco, "longitude", "lng"))
    raw_items = _pick(raw, "items", "itens", "produtos", default=[]) or []
    items = [_normalize_item(i) for i in raw_items if isinstance(i, dict)]
    subtotal_calc = round(sum(i["unit_price"] * i["quantity"] for i in items), 2)
    delivery_fee = _num(_pick(raw, "delivery", "delivery_fee", "taxa_entrega", "frete", default=0))
    subtotal = _num(_pick(raw, "subtotal"), subtotal_calc) if _pick(raw, "subtotal") is not None else subtotal_calc
    total = _num(_pick(raw, "total", "valor_total"), subtotal + delivery_fee) if _pick(raw, "total", "valor_total") is not None else round(subtotal + delivery_fee, 2)
    method = _pick(raw, "payment_method", "forma_pagamento", "pagamento", default="")
    return {
        "external_id": str(ext_id) if ext_id is not None else (str(order_number) if order_number else None),
        "order_number": str(order_number) if order_number else (str(ext_id) if ext_id is not None else None),
        "status": str(_pick(raw, "status", default="") or "").strip().lower(),
        "customer_name": _pick(raw, "customer_name", "cliente_nome", "nome_cliente",
                               default=_pick(cliente, "nome", "name", default=_pick(customer, "name", "nome"))),
        "customer_phone": _pick(raw, "customer_phone", "cliente_telefone", "telefone",
                                default=_pick(cliente, "telefone", "phone", default=_pick(customer, "phone", "telefone"))),
        "address": address,
        "address_text": address_text,
        "latitude": _num(lat, None) if lat is not None else None,
        "longitude": _num(lng, None) if lng is not None else None,
        "items": items,
        "subtotal": round(subtotal, 2),
        "delivery_fee": round(delivery_fee, 2),
        "total": round(total, 2),
        "payment_method": str(method or "").strip().lower(),
        "origin_platform": _pick(raw, "platform", "plataforma", "origem", "origin", "canal"),
        "created_at": _pick(raw, "created_at", "data", "data_pedido"),
        "cancel_reason": _pick(raw, "motivo", "reason", "cancellation_reason", "motivo_cancelamento"),
    }


def is_nostfood(order: Optional[dict]) -> bool:
    return bool(order) and order.get("external_source") == SOURCE


def is_to_collect(order: Optional[dict]) -> bool:
    """Pedido da NostFood cobrado na entrega: entra no caixa pelo fechamento normal."""
    return is_nostfood(order) and order.get("payment_status") == "to_collect"


def settles_on_platform(order: Optional[dict]) -> bool:
    """Pedido online cujo dinheiro vem por repasse (não entra no caixa)."""
    return bool(order) and order.get("source") == "online" and not is_to_collect(order)


def excluded_from_cash(order: Optional[dict]) -> bool:
    """Fora do caixa: pedido de teste e pedido "Não recebido"."""
    return bool(order) and (bool(order.get("is_test")) or order.get("payment_status") == "not_received")


# Pedidos que ainda esperam dinheiro no caixa (bloqueiam o fechamento do caixa).
# Cancelado, de teste ou "Não recebido" nunca bloqueia.
OPEN_CASH_ORDERS_QUERY = {
    "is_closed": False,
    "is_test": {"$ne": True},
    "$or": [
        {"source": {"$ne": "online"}},
        {"external_source": SOURCE, "payment_status": "to_collect", "status": {"$ne": "cancelled"}},
    ],
}


async def pending_to_collect() -> list:
    """Pedidos a cobrar na entrega ainda abertos (lista mostrada no fechamento do caixa)."""
    rows = await S.db.orders.find(
        {"is_closed": False, "is_test": {"$ne": True}, "external_source": SOURCE,
         "payment_status": "to_collect", "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(200)
    return [{"order_id": o["id"], "order_number": o.get("external_order_number"),
             "customer_name": o.get("customer_name"), "total": o.get("total", 0),
             "payment_method": o.get("payment_method"), "created_at": o.get("created_at")}
            for o in sorted(rows, key=lambda o: o.get("created_at") or "")]


async def not_received_between(start_iso: str, end_iso: str) -> list:
    rows = await S.db.orders.find(
        {"external_source": SOURCE, "payment_status": "not_received",
         "closed_at": {"$gte": start_iso, "$lte": end_iso}}, {"_id": 0}).to_list(200)
    return [{"order_id": o["id"], "order_number": o.get("external_order_number"),
             "customer_name": o.get("customer_name"), "total": o.get("total", 0),
             "reason": (o.get("not_received") or {}).get("reason"),
             "by_name": (o.get("not_received") or {}).get("by_name")} for o in rows]


# ==================== ÍNDICES ====================
async def ensure_indexes():
    if _state["indexes_ok"]:
        return
    db = S.db
    try:
        await db.nostfood_events.create_index("event_id", unique=True, name="uniq_event_id")
        # Limpeza automática: o MongoDB apaga o evento 30 dias depois de recebido.
        await db.nostfood_events.create_index("received_at_dt", expireAfterSeconds=EVENTS_TTL_SECONDS,
                                              name="ttl_30_dias")
        # Parcial: pedidos antigos sem external_source não entram no índice.
        await db.orders.create_index(
            [("external_source", 1), ("external_id", 1)], unique=True, name="uniq_external_order",
            partialFilterExpression={"external_source": {"$type": "string"}},
        )
        await db.nostfood_product_map.create_index("nostfood_key", unique=True, name="uniq_nostfood_key")
        await db.nostfood_unlinked.create_index("nostfood_key", unique=True, name="uniq_unlinked_key")
        await db.nostfood_tombstones.create_index("external_id", unique=True, name="uniq_tombstone")
        await db.stock_losses.create_index("date", name="loss_date")
        _state["indexes_ok"] = True
    except Exception as e:  # nunca derruba o servidor
        logger.error(f"[NOSTFOOD] falha ao criar índices ({type(e).__name__}): {e}")


# ==================== DATA DE ATIVAÇÃO ====================
async def get_enabled_at() -> Optional[datetime]:
    """nostfood_enabled_at: gravada na primeira vez que a integração liga.

    Pedidos criados na NostFood antes dela são ignorados.
    """
    cached = _state.get("enabled_at")
    if cached:
        return cached
    doc = await S.db.nostfood_settings.find_one({"key": "config"}, {"_id": 0})
    value = (doc or {}).get("nostfood_enabled_at")
    if not value and enabled():
        value = _now_iso()
        await S.db.nostfood_settings.update_one(
            {"key": "config"}, {"$setOnInsert": {"key": "config", "nostfood_enabled_at": value}}, upsert=True)
        doc = await S.db.nostfood_settings.find_one({"key": "config"}, {"_id": 0})
        value = (doc or {}).get("nostfood_enabled_at") or value
        logger.info(f"[NOSTFOOD] data de ativação gravada: {value}")
    if not value:
        return None
    parsed = parse_remote_datetime(value)
    _state["enabled_at"] = parsed
    return parsed


def parse_remote_datetime(value) -> Optional[datetime]:
    """"YYYY-MM-DD HH:MM:SS" (horário de São Paulo) ou ISO com fuso."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=SP_TZ)
    return None


def _date_field_names(raw: dict) -> list:
    keys = []
    for k, v in (raw or {}).items():
        lk = str(k).lower()
        if any(t in lk for t in ("data", "date", "created", "hora", "_at", "time")) and v not in (None, ""):
            keys.append(str(k))
    return sorted(keys)


async def created_before_activation(norm: dict) -> bool:
    enabled_at = await get_enabled_at()
    created = parse_remote_datetime(norm.get("created_at"))
    return bool(enabled_at and created and created < enabled_at)


def _lock(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    return lock


def _schedule(coro):
    """Roda em segundo plano sem travar quem chamou (KDS)."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def _open_orders():
    return await S.db.orders.find({"is_closed": False}, {"_id": 0}).to_list(100)


async def _emit_kds():
    try:
        orders = await _open_orders()
        await S.sio.emit("kitchen_update", orders)
        await S.sio.emit("bar_update", orders)
    except Exception as e:
        logger.warning(f"[NOSTFOOD] falha ao avisar o KDS: {e}")


# ==================== API DA NOSTFOOD ====================
async def fetch_orders_page(params: dict) -> dict:
    import httpx
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        r = await client.get(f"{_base_url()}/pedidos.php", params=params, headers={"X-API-Key": _api_key()})
        r.raise_for_status()
        body = r.json()
    if not body.get("success", True):
        raise RuntimeError(body.get("message") or "NostFood respondeu success=false")
    return body.get("data") or {}


async def fetch_orders_for_days(days) -> list:
    out = []
    for day in days:
        offset = 0
        while True:
            data = await fetch_orders_page({
                "data_inicio": day.isoformat(), "data_fim": day.isoformat(),
                "limit": 1000, "offset": offset,
            })
            page = data.get("pedidos") or []
            out.extend(p for p in page if isinstance(p, dict))
            if not data.get("has_more") or not page:
                break
            offset += len(page)
    return out


async def fetch_remote_order(external_id, order_number) -> Optional[dict]:
    """Não existe consulta de um pedido só: busca o dia (e o anterior) e procura."""
    today = _today_sp()
    for p in await fetch_orders_for_days([today, today - timedelta(days=1)]):
        if (external_id and str(p.get("id")) == str(external_id)) or (
                order_number and str(p.get("order_number")) == str(order_number)):
            return p
    return None


async def send_status(external_id, order_number, status: str) -> dict:
    import httpx
    body = {"status": status}
    if external_id and str(external_id).isdigit():
        body["pedido_id"] = int(external_id)
    elif order_number:
        body["order_number"] = str(order_number)
    else:
        body["pedido_id"] = external_id
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        r = await client.post(f"{_base_url()}/atualizar-pedido.php", json=body,
                              headers={"X-API-Key": _api_key()})
        r.raise_for_status()
        data = r.json()
    if not data.get("success", True):
        raise RuntimeError(data.get("message") or "NostFood respondeu success=false")
    return data


# ==================== ESTOQUE ====================
async def safe_deduct(order: dict, item: dict) -> bool:
    """Baixa de estoque que nunca trava KDS nem caixa (pedido da NostFood).

    Falha: registra no log, marca o item com pendência de estoque e segue.
    """
    if item.get("stock_deducted"):
        return True
    if order.get("is_test"):
        return False  # pedido de teste nunca mexe em estoque nem em CMV
    if item.get("unlinked"):
        item["stock_pending"] = True
        item["stock_pending_reason"] = "item sem ligação com produto do Gestor"
        return False
    try:
        await S.deduct_stock(item["product_id"], item["quantity"], order_code=order.get("id", ""))
    except Exception as e:
        detail = getattr(e, "detail", None) or str(e)
        logger.warning(f"[NOSTFOOD] baixa de estoque pendente pedido={order.get('id')} "
                       f"item={item.get('product_name')}: {detail}")
        item["stock_pending"] = True
        item["stock_pending_reason"] = str(detail)[:300]
        item["stock_pending_at"] = _now_iso()
        return False
    item["stock_deducted"] = True
    item.pop("stock_pending_reason", None)
    item["stock_pending"] = False
    return True


async def _item_unit_cost(item: dict):
    if item.get("unlinked"):
        return 0.0, "sem_ligacao"
    pid = item.get("product_id")
    recipe = await S.db.recipes.find_one({"product_id": pid}, {"_id": 0})
    if recipe and recipe.get("ingredients"):
        detail = await S._compute_recipe_cost(recipe)
        return float(detail.get("total_cost", 0) or 0), "ficha_tecnica"
    product = await S.db.products.find_one({"id": pid}, {"_id": 0})
    if product and float(product.get("cost", 0) or 0) > 0:
        return float(product["cost"]), "custo_produto"
    return 0.0, "sem_custo"


# ==================== LIGAÇÃO DE PRODUTOS ====================
def _item_keys(external_item_id, name):
    keys = []
    if external_item_id:
        keys.append(f"id:{external_item_id}")
    if name:
        keys.append(f"name:{normalize_name(name)}")
    return keys


async def _find_mapping(external_item_id, name):
    for key in _item_keys(external_item_id, name):
        m = await S.db.nostfood_product_map.find_one({"nostfood_key": key}, {"_id": 0})
        if m:
            return m
    return None


async def _product_station_type(product: dict) -> str:
    ptype = product.get("type")
    if ptype in ("food", "drink"):
        return ptype
    cat = await S.db.categories.find_one({"id": product.get("category_id")}, {"_id": 0})
    return (cat or {}).get("type") if (cat or {}).get("type") in ("food", "drink") else "food"


def _compose_notes(observation, addons):
    parts = []
    if observation:
        parts.append(observation)
    if addons:
        parts.append("Adicionais: " + ", ".join(
            (f"{a['quantity']}x " if a.get("quantity", 1) > 1 else "") + a["name"] for a in addons))
    return " | ".join(parts) or None


async def _build_items(norm_items, now_iso):
    items, unlinked = [], []
    for ni in norm_items:
        mapping = await _find_mapping(ni["external_item_id"], ni["name"])
        product = None
        if mapping:
            product = await S.db.products.find_one({"id": mapping["product_id"]}, {"_id": 0})
        key = _item_keys(ni["external_item_id"], ni["name"])[0]
        item = {
            "id": str(uuid.uuid4()),
            "quantity": ni["quantity"],
            "unit_price": ni["unit_price"],
            "notes": _compose_notes(ni["observation"], ni["addons"]),
            "status": "pending",
            "is_courtesy": False,
            "courtesy_reason": None,
            "stock_deducted": False,
            "created_at": now_iso,
            "external_item_id": ni["external_item_id"],
            "external_name": ni["name"],
            "observation": ni["observation"],
            "addons": ni["addons"],
            "nostfood_key": key,
        }
        if product:
            item.update({
                "product_id": product["id"],
                "product_name": product.get("name") or ni["name"],
                "type": await _product_station_type(product),
                "unlinked": False,
            })
        else:
            # Sem ligação: entra no pedido e vai para a cozinha por padrão, com alerta.
            # product_id artificial: nunca casa com estoque/receita (baixa vira pendência).
            item.update({
                "product_id": f"nostfood-unlinked:{key}",
                "product_name": ni["name"],
                "type": "food",
                "unlinked": True,
            })
            unlinked.append(item)
        items.append(item)
    return items, unlinked


async def _register_unlinked(order: dict, unlinked_items: list):
    for it in unlinked_items:
        try:
            await S.db.nostfood_unlinked.update_one(
                {"nostfood_key": it["nostfood_key"]},
                {"$set": {"nostfood_key": it["nostfood_key"], "nostfood_id": it.get("external_item_id"),
                          "nostfood_name": it.get("external_name"), "last_seen_at": _now_iso(),
                          "last_order_id": order["id"],
                          "last_order_number": order.get("external_order_number")},
                 "$inc": {"occurrences": 1}},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"[NOSTFOOD] falha ao registrar item sem ligação: {e}")
    if unlinked_items:
        names = ", ".join(i["product_name"] for i in unlinked_items)
        logger.warning(f"[NOSTFOOD] pedido {order.get('external_order_number')} com item sem ligação: {names}")
        await S.sio.emit("nostfood_alert", {
            "type": "unlinked_item",
            "order_id": order["id"],
            "order_number": order.get("external_order_number"),
            "items": [i["product_name"] for i in unlinked_items],
            "message": f"Pedido {order.get('external_order_number')}: item sem ligação ({names})",
        })


# ==================== PEDIDOS ====================
async def _find_order(external_id, order_number=None):
    if external_id:
        o = await S.db.orders.find_one({"external_source": SOURCE, "external_id": str(external_id)}, {"_id": 0})
        if o:
            return o
    if order_number:
        return await S.db.orders.find_one(
            {"external_source": SOURCE, "external_order_number": str(order_number)}, {"_id": 0})
    return None


async def upsert_from_snapshot(raw: dict, origin: str, is_test: bool = False,
                               first_poll: bool = False) -> str:
    """Cria o pedido no Gestor se ainda não existir. Nunca duplica (webhook + polling).

    is_test=True só vem de /simular; webhook e polling nunca passam esse valor.
    """
    norm = normalize_order(raw)
    ext_id = norm["external_id"]
    if not ext_id:
        raise ValueError("pedido sem id")
    await ensure_indexes()

    if not is_test and parse_remote_datetime(norm.get("created_at")) is None:
        exists = await _find_order(ext_id, norm["order_number"])
        logger.warning(f"[NOSTFOOD] pedido {norm['order_number']} sem data de criação (via {origin}); "
                       f"campos de data recebidos: {', '.join(_date_field_names(raw)) or 'nenhum'}")
        # Sem data não dá para comparar com a ativação: no primeiro ciclo de polling
        # nunca importa (seriam pedidos antigos do dia); depois, só se ainda não existir.
        if first_poll and not exists:
            return "ignored_no_date_first_poll"

    if not is_test and await created_before_activation(norm) and not await _find_order(ext_id, norm["order_number"]):
        return "ignored_before_activation"

    if norm["status"] in CANCEL_STATUSES:
        return await cancel_external(ext_id, norm["order_number"], norm["cancel_reason"], origin)

    existing = await _find_order(ext_id, norm["order_number"])
    if existing:
        if norm["status"] and existing.get("nostfood_status") != norm["status"]:
            await S.db.orders.update_one({"id": existing["id"]}, {"$set": {"nostfood_status": norm["status"]}})
        return "exists"
    if await S.db.nostfood_tombstones.find_one({"external_id": ext_id}, {"_id": 0}):
        return "ignored_cancelled"
    if not norm["items"]:
        raise ValueError("pedido sem itens")

    async with _lock(ext_id):
        if await _find_order(ext_id, norm["order_number"]):
            return "exists"
        now_iso = _now_iso()
        items, unlinked = await _build_items(norm["items"], now_iso)
        remote_status = norm["status"]
        item_status = ("delivered" if remote_status in DONE_STATUSES
                       else "preparing" if remote_status in PREPARING_STATUSES else "pending")
        for it in items:
            it["status"] = item_status
        payment_status = payment_status_for(norm["payment_method"])
        if not norm["payment_method"]:
            logger.warning(f"[NOSTFOOD] pedido {norm['order_number']} sem forma de pagamento: tratado como cobrar na entrega")
        order = {
            "id": str(uuid.uuid4()),
            "table_id": None,
            "table_number": None,
            "waiter_id": None,
            "waiter_name": None,
            "tab_number": None,
            "items": items,
            "status": "delivered" if item_status == "delivered" else "pending",
            "subtotal": norm["subtotal"],
            "delivery_fee": norm["delivery_fee"],
            "service_fee": 0.0,
            "service_fee_percentage": 0,  # delivery: sem 10%
            "total": norm["total"],
            "created_at": now_iso,
            "closed_at": None,
            "is_closed": False,
            "is_comp": False,
            "source": "online",
            "origin": SOURCE,
            "platform": SOURCE,
            "channel": "delivery",
            "delivery_type": "delivery",
            "external_source": SOURCE,
            "external_id": ext_id,
            "external_order_number": norm["order_number"],
            "external_created_at": norm["created_at"],
            "external_origin_platform": norm["origin_platform"],
            "customer_name": norm["customer_name"],
            "customer_phone": norm["customer_phone"],
            "address": norm["address_text"],
            "customer_address": norm["address"],
            "latitude": norm["latitude"],
            "longitude": norm["longitude"],
            "payment_method": norm["payment_method"],
            "payment_status": payment_status,
            "nostfood_status": norm["status"] or None,
            # Status que a NostFood já tem não são reenviados pelo KDS.
            "nostfood_sent_statuses": ["em_preparo"] if item_status != "pending" else [],
            "nostfood_received_via": origin,
            "imported_in_progress": item_status != "pending",
            "is_test": bool(is_test),
            "observations": [],
            "kds_ack_pending": False,
        }
        try:
            await S.db.orders.insert_one(order)
        except DuplicateKeyError:
            return "exists"
        order.pop("_id", None)

    logger.info(f"[NOSTFOOD] pedido {order['external_order_number']} criado via {origin} "
                f"({len(items)} itens, {payment_status}, status {remote_status or '-'})")
    if item_status == "delivered":
        await _import_finished(order, remote_status)
    await S.emit_order_updates(items)
    if item_status != "pending":
        await _register_unlinked(order, unlinked)
        return "created_history" if item_status == "delivered" else "created"
    await S.sio.emit("new_online_order", {
        "order_id": order["id"], "platform": SOURCE,
        "external_order_number": order["external_order_number"],
        "delivery_type": "delivery", "total": order["total"], "items_count": len(items),
        "payment_status": payment_status,
    })
    await _register_unlinked(order, unlinked)
    return "created"


async def _import_finished(order: dict, remote_status: str):
    """Pedido que já chegou pronto/saindo/entregue: baixa de estoque (é venda) e histórico.

    Entregue e pago online: fecha como repasse pendente (entra nas vendas).
    Cobrar na entrega: fica aberto para o caixa receber o dinheiro.
    """
    for item in order["items"]:
        await safe_deduct(order, item)
    update = {"items": order["items"]}
    if remote_status in DELIVERED_STATUSES and not is_to_collect(order):
        update.update({
            "is_closed": True, "closed_at": _now_iso(), "status": "delivered",
            "settlement_status": "pending_platform", "settlement_gross": order.get("total", 0),
            "settlement_net": None, "settlement_platform": SOURCE,
        })
    await S.db.orders.update_one({"id": order["id"]}, {"$set": update})
    order.update(update)


async def cancel_external(external_id, order_number, reason, origin) -> str:
    """Cancelamento vindo da NostFood (order.cancelled ou status cancelado/rejeitado)."""
    reason = (str(reason).strip() if reason else "") or "Cancelado na plataforma"
    order = await _find_order(external_id, order_number)
    if not order:
        # O cancelamento pode chegar antes da criação (a ordem não é garantida).
        if external_id:
            await S.db.nostfood_tombstones.update_one(
                {"external_id": str(external_id)},
                {"$set": {"external_id": str(external_id), "order_number": order_number,
                          "reason": reason, "at": _now_iso()}},
                upsert=True,
            )
        return "tombstone"
    if order.get("status") == "cancelled":
        return "already_cancelled"
    if order.get("is_closed"):
        await S.db.orders.update_one({"id": order["id"]}, {"$set": {
            "nostfood_status": "cancelado", "nostfood_cancelled_after_close": True,
            "nostfood_cancel_reason": reason}})
        logger.warning(f"[NOSTFOOD] pedido {order.get('external_order_number')} cancelado na plataforma "
                       f"depois de finalizado no Gestor: conferir manualmente")
        await S.sio.emit("nostfood_alert", {
            "type": "cancelled_after_close", "order_id": order["id"],
            "order_number": order.get("external_order_number"),
            "message": f"Pedido {order.get('external_order_number')} cancelado na NostFood depois de finalizado no Gestor",
        })
        return "cancelled_after_close"

    now_iso = _now_iso()
    # Reserva o cancelamento primeiro (condicional): ninguém fecha nem cancela junto.
    claim = await S.db.orders.update_one(
        {"id": order["id"], "is_closed": False, "status": {"$ne": "cancelled"}},
        {"$set": {
            "status": "cancelled", "is_closed": True, "closed_at": now_iso,
            "cancelled_at": now_iso, "cancelled_by_id": None, "cancelled_by_name": SOURCE,
            "cancellation_reason": reason, "nostfood_status": "cancelado",
            "kds_ack_pending": True, "cancel_acks": {},
        }},
    )
    if getattr(claim, "modified_count", 0) != 1:
        return "already_closed"

    loss_items, restored = [], []
    for item in order.get("items", []):
        if item.get("status") == "cancelled":
            continue
        prev = item.get("status")
        item["status_before_cancel"] = prev
        if prev in STARTED_ITEM_STATUSES:
            # Cozinha já começou ou ficou pronto: vira perda (CMV), não venda.
            await safe_deduct(order, item)
            unit_cost, cost_source = await _item_unit_cost(item)
            loss_items.append({
                "item_id": item["id"], "product_id": None if item.get("unlinked") else item.get("product_id"),
                "product_name": item.get("product_name"), "quantity": item.get("quantity"),
                "status_before_cancel": prev, "unit_cost": round(unit_cost, 2),
                "total_cost": round(unit_cost * float(item.get("quantity") or 0), 2),
                "cost_source": cost_source, "stock_deducted": bool(item.get("stock_deducted")),
                "stock_pending": bool(item.get("stock_pending")),
            })
            item["lost"] = True
        elif item.get("stock_deducted"):
            # Não começou: devolve a baixa (se houve alguma).
            try:
                await S.restore_stock(item["product_id"], item["quantity"], order_code=order["id"])
                item["stock_deducted"] = False
                restored.append(item["id"])
            except Exception as e:
                logger.warning(f"[NOSTFOOD] devolução de estoque pendente item={item.get('product_name')}: {e}")
                item["stock_pending"] = True
                item["stock_pending_reason"] = f"devolução falhou: {e}"[:300]
        item["status"] = "cancelled"
        item["cancellation_reason"] = reason
        item["cancelled_at"] = now_iso
        item["cancelled_by_name"] = SOURCE

    await S.db.orders.update_one({"id": order["id"]}, {"$set": {"items": order.get("items", [])}})

    if loss_items and not order.get("is_test"):
        loss = {
            "id": str(uuid.uuid4()),
            "date": datetime.now(SP_TZ).date().isoformat(),
            "created_at": now_iso,
            "reason": reason,
            "source": SOURCE,
            "order_id": order["id"],
            "external_id": order.get("external_id"),
            "external_order_number": order.get("external_order_number"),
            "items": loss_items,
            "total_cost": round(sum(i["total_cost"] for i in loss_items), 2),
            "created_by_name": SOURCE,
        }
        await S.db.stock_losses.insert_one(loss)

    logger.info(f"[NOSTFOOD] pedido {order.get('external_order_number')} cancelado via {origin}: {reason} "
                f"(perdas={len(loss_items)}, devolvidos={len(restored)})")
    updated = await S.db.orders.find_one({"id": order["id"]}, {"_id": 0})
    await S.sio.emit("order_cancelled", {"order_id": order["id"]})
    await S.sio.emit("kds_cancelled", updated)
    await _emit_kds()
    if restored or loss_items:
        try:
            await S.sio.emit("stock_updated", await S.db.stock.find({}, {"_id": 0}).to_list(500))
        except Exception:
            pass
    return "cancelled_with_loss" if loss_items else "cancelled"


# ==================== WEBHOOK ====================
async def _is_self_echo(external_id, order_number, status) -> bool:
    if not status:
        return False
    order = await _find_order(external_id, order_number)
    return bool(order) and status in (order.get("nostfood_sent_statuses") or [])


async def handle_event(event: dict) -> str:
    etype = str(event.get("event_type") or "").strip()
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    resource = event.get("resource") if isinstance(event.get("resource"), dict) else {}
    ext_id = _pick(resource, "id") or _pick(data, "id", "pedido_id", "order_id")
    ext_id = str(ext_id) if ext_id is not None else None
    order_number = _pick(data, "order_number", "numero", "numero_pedido")
    status = str(_pick(data, "status", default="") or "").strip().lower()

    if not etype.startswith("order."):
        return "ignored_type"
    if etype == "order.updated" and await _is_self_echo(ext_id, order_number, status):
        return "ignored_self"  # mudança causada pelo próprio Gestor: evita laço
    if etype == "order.cancelled" or status in CANCEL_STATUSES:
        reason = _pick(data, "motivo", "reason", "cancellation_reason", "motivo_cancelamento")
        return await cancel_external(ext_id, order_number, reason, "webhook")

    full = data if isinstance(_pick(data, "items", "itens"), list) else None
    if full is None:
        if await _find_order(ext_id, order_number):
            if status:
                o = await _find_order(ext_id, order_number)
                await S.db.orders.update_one({"id": o["id"]}, {"$set": {"nostfood_status": status}})
            return "status_mirrored"
        full = await fetch_remote_order(ext_id, order_number)
        if full is None:
            raise LookupError("pedido não encontrado na API da NostFood (o polling tenta de novo)")
    elif ext_id and not _pick(full, "id", "pedido_id", "order_id"):
        full = {**full, "id": ext_id}
    return await upsert_from_snapshot(full, "webhook")


async def process_event(event: dict):
    event_id = event.get("event_id")
    try:
        result = await handle_event(event.get("payload") or event)
        await S.db.nostfood_events.update_one(
            {"event_id": event_id}, {"$set": {"status": "processed", "result": result, "processed_at": _now_iso()}})
    except Exception as e:
        logger.error(f"[NOSTFOOD] evento {event_id} falhou ({type(e).__name__}): {e}")
        await S.db.nostfood_events.update_one(
            {"event_id": event_id}, {"$set": {"status": "error", "error": str(e)[:500], "processed_at": _now_iso()}})


# ==================== POLLING ====================
async def _first_poll_pending() -> bool:
    doc = await S.db.nostfood_settings.find_one({"key": "config"}, {"_id": 0})
    return not (doc or {}).get("first_poll_done_at")


async def _mark_first_poll_done():
    await S.db.nostfood_settings.update_one(
        {"key": "config"}, {"$set": {"first_poll_done_at": _now_iso()}}, upsert=True)


async def poll_once() -> dict:
    await get_enabled_at()  # grava a data de ativação, se ainda não existir
    first_poll = await _first_poll_pending()
    today = _today_sp()
    days = [today]
    if datetime.now(SP_TZ).hour == 0:  # virada do dia: olha também o anterior
        days.append(today - timedelta(days=1))
    remote = await fetch_orders_for_days(days)
    summary = {"seen": len(remote), "created": 0, "cancelled": 0, "skipped": 0, "errors": 0,
               "first_poll": first_poll}
    for raw in remote:
        try:
            norm = normalize_order(raw)
            if not norm["external_id"]:
                continue
            if norm["status"] in CANCEL_STATUSES:
                r = await upsert_from_snapshot(raw, "polling", first_poll=first_poll)  # respeita a ativação
                summary["cancelled"] += r.startswith("cancelled")
                continue
            r = await upsert_from_snapshot(raw, "polling", first_poll=first_poll)
            summary["created"] += r.startswith("created")
            summary["skipped"] += r.startswith("ignored_")
        except Exception as e:
            summary["errors"] += 1
            logger.error(f"[NOSTFOOD] polling: pedido {raw.get('order_number') or raw.get('id')} falhou: {e}")
    if first_poll:
        await _mark_first_poll_done()
    return summary


async def _poll_loop():
    await asyncio.sleep(10)
    while True:
        if enabled() and _api_key():
            try:
                _state["last_poll_result"] = await poll_once()
                _state["last_poll_error"] = None
            except Exception as e:
                _state["last_poll_error"] = f"{type(e).__name__}: {e}"[:300]
                logger.error(f"[NOSTFOOD] polling falhou: {_state['last_poll_error']}")
            _state["last_poll_at"] = _now_iso()
        await asyncio.sleep(poll_seconds())


# ==================== STATUS DE VOLTA (gancho do KDS) ====================
async def _push_status(order: dict, target: str):
    if order.get("is_test"):
        return  # pedido de teste nunca chama a NostFood
    if not send_status_enabled():
        logger.info(f"[NOSTFOOD] NOSTFOOD_SEND_STATUS=false: teria enviado status {target} "
                    f"para o pedido {order.get('external_order_number')} (id {order.get('external_id')})")
        return
    try:
        await send_status(order.get("external_id"), order.get("external_order_number"), target)
        logger.info(f"[NOSTFOOD] status {target} enviado para o pedido {order.get('external_order_number')}")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"[:300]
        logger.error(f"[NOSTFOOD] falha ao enviar status {target} do pedido {order.get('external_order_number')}: {msg}")
        try:
            await S.db.orders.update_one({"id": order["id"]}, {"$push": {"nostfood_sync_errors": {
                "status": target, "error": msg, "at": _now_iso()}}})
        except Exception:
            pass


async def on_item_status_changed(order_id: str, new_status: str):
    """Chamado pelo server.py depois de salvar o status do item. Nunca levanta erro."""
    try:
        if not enabled():
            return
        order = await S.db.orders.find_one({"id": order_id}, {"_id": 0})
        if not is_nostfood(order) or order.get("is_test") or order.get("status") == "cancelled":
            return
        active = [i for i in order.get("items", []) if i.get("status") != "cancelled"]
        target = None
        if new_status == "preparing":
            target = "em_preparo"
        elif new_status == "ready" and active and all(i.get("status") in ("ready", "delivered") for i in active):
            target = "pronto"
        if not target or target in (order.get("nostfood_sent_statuses") or []):
            return
        # Anota antes de enviar: o order.updated que volta é ignorado (sem laço).
        await S.db.orders.update_one({"id": order_id}, {"$addToSet": {"nostfood_sent_statuses": target}})
        _schedule(_push_status(order, target))
    except Exception as e:
        logger.error(f"[NOSTFOOD] gancho de status falhou para {order_id}: {e}")


# ==================== ROTAS ====================
def _validate_station(body: dict) -> str:
    station = str((body or {}).get("station") or "").strip().lower()
    if station not in KDS_STATIONS:
        raise HTTPException(status_code=400, detail="Informe a tela: kitchen, bar ou grill")
    return station


def _required_cancel_stations(order: dict):
    types = {i.get("type") for i in order.get("items", [])}
    return [s for s, t in (("kitchen", "food"), ("bar", "drink")) if t in types]


def build_router(require_role, UserRole) -> APIRouter:
    router = APIRouter(prefix="/integrations/nostfood", tags=["nostfood"])
    admin = Depends(require_role([UserRole.ADMIN]))
    cash = Depends(require_role([UserRole.ADMIN, UserRole.CASHIER]))
    kds = Depends(require_role([UserRole.ADMIN, UserRole.KITCHEN, UserRole.BAR]))
    staff = Depends(require_role([UserRole.ADMIN, UserRole.WAITER, UserRole.CASHIER, UserRole.KITCHEN, UserRole.BAR]))

    @router.post("/webhook")
    async def webhook(request: Request, background_tasks: BackgroundTasks):
        if not enabled():
            raise HTTPException(status_code=503, detail="Integração NostFood desligada")
        secret = _webhook_secret()
        if not secret:
            # Nunca aceita sem verificar a assinatura.
            raise HTTPException(status_code=503, detail="NOSTFOOD_WEBHOOK_SECRET não configurado: webhook recusado")
        raw = await request.body()
        if not verify_signature(raw, request.headers.get("X-NostFood-Signature"), secret):
            raise HTTPException(status_code=401, detail="Assinatura inválida")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            raise HTTPException(status_code=400, detail="JSON inválido")
        event_id = payload.get("event_id") if isinstance(payload, dict) else None
        if not event_id or not isinstance(event_id, str):
            raise HTTPException(status_code=400, detail="event_id ausente")
        await ensure_indexes()
        if await S.db.nostfood_events.find_one({"event_id": event_id}, {"_id": 0, "event_id": 1}):
            return {"ok": True, "duplicate": True}
        doc = {
            "event_id": event_id,
            "event_type": payload.get("event_type"),
            "delivery_id": request.headers.get("X-NostFood-Delivery-Id"),
            "delivery_attempt": payload.get("delivery_attempt"),
            "received_at": _now_iso(),
            "received_at_dt": datetime.now(timezone.utc),  # campo do índice TTL (30 dias)
            "status": "received",
            "payload": payload,
        }
        try:
            await S.db.nostfood_events.insert_one(doc)
        except DuplicateKeyError:
            return {"ok": True, "duplicate": True}
        doc.pop("_id", None)
        background_tasks.add_task(process_event, doc)
        return {"ok": True}

    @router.get("/status", dependencies=[admin])
    async def integration_status():
        return {
            "enabled": enabled(), "has_api_key": bool(_api_key()), "has_webhook_secret": bool(_webhook_secret()),
            "base_url": _base_url(), "poll_seconds": poll_seconds(), "send_status": send_status_enabled(),
            "last_poll_at": _state["last_poll_at"], "last_poll_result": _state["last_poll_result"],
            "last_poll_error": _state["last_poll_error"],
        }

    @router.post("/simular")
    async def simulate(body: Optional[dict] = Body(None), current_user: dict = admin):
        """Pedido falso só no Gestor (nunca chama a NostFood)."""
        body = body or {}
        sim_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
        snapshot = {
            "id": sim_id,
            "order_number": sim_id,
            "customer_name": "Cliente Teste (simulação)",
            "customer_phone": "00000000000",
            "customer_address": "Rua da Simulação",
            "customer_number": "100",
            "customer_neighborhood": "Centro",
            "latitude": -21.0, "longitude": -47.0,
            "items": body.get("items") or [
                {"id": "sim-sansao", "name": "Sansão", "quantity": 1, "price": 32.0, "observacao": "sem picles"},
                {"id": "sim-coca-lata", "name": "Coca-Cola lata", "quantity": 2, "price": 6.0},
            ],
            "delivery": 5.0,
            "payment_method": body.get("payment_method") or "pix_online",
            "status": "confirmado",
        }
        result = await upsert_from_snapshot(snapshot, "simulacao", is_test=True)
        order = await _find_order(sim_id)
        return {"result": result, "order": order}

    @router.delete("/testes", dependencies=[admin])
    async def delete_test_orders():
        """Apaga todos os pedidos de teste (/simular) e o que eles geraram."""
        ids = [o["id"] for o in await S.db.orders.find({"is_test": True}, {"_id": 0, "id": 1}).to_list(5000)]
        removed = await S.db.orders.delete_many({"is_test": True})
        if ids:
            await S.db.stock_losses.delete_many({"order_id": {"$in": ids}})
            await S.db.payments.delete_many({"order_id": {"$in": ids}})
        await _emit_kds()
        await S.sio.emit("kds_cancelled", None)
        logger.info(f"[NOSTFOOD] {removed.deleted_count} pedido(s) de teste apagado(s)")
        return {"deleted": removed.deleted_count}

    @router.post("/pedidos/{order_id}/nao-recebido")
    async def mark_not_received(order_id: str, body: dict, current_user: dict = admin):
        """Cliente não pagou na entrega: libera o fechamento do caixa e não entra como venda."""
        reason = str((body or {}).get("reason") or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="Informe o motivo")
        order = await S.db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        if not is_to_collect(order) or order.get("is_closed") or order.get("status") == "cancelled":
            raise HTTPException(status_code=409, detail="Só vale para pedido da NostFood a cobrar na entrega, ainda aberto")
        now_iso = _now_iso()
        info = {"reason": reason, "by_id": current_user.get("id"), "by_name": current_user.get("name"), "at": now_iso}
        claim = await S.db.orders.update_one(
            {"id": order_id, "is_closed": False, "payment_status": "to_collect"},
            {"$set": {"is_closed": True, "closed_at": now_iso, "payment_status": "not_received",
                      "not_received": info}})
        if getattr(claim, "modified_count", 0) != 1:
            raise HTTPException(status_code=409, detail="Pedido já foi finalizado")
        # A comida saiu: baixa de estoque e custo como perda (CMV), não como venda.
        loss_items = []
        for item in order.get("items", []):
            if item.get("status") == "cancelled":
                continue
            await safe_deduct(order, item)
            unit_cost, cost_source = await _item_unit_cost(item)
            loss_items.append({
                "item_id": item["id"], "product_id": None if item.get("unlinked") else item.get("product_id"),
                "product_name": item.get("product_name"), "quantity": item.get("quantity"),
                "status_before_cancel": item.get("status"), "unit_cost": round(unit_cost, 2),
                "total_cost": round(unit_cost * float(item.get("quantity") or 0), 2),
                "cost_source": cost_source, "stock_deducted": bool(item.get("stock_deducted")),
                "stock_pending": bool(item.get("stock_pending")),
            })
        await S.db.orders.update_one({"id": order_id}, {"$set": {"items": order.get("items", [])}})
        if loss_items:
            await S.db.stock_losses.insert_one({
                "id": str(uuid.uuid4()), "date": datetime.now(SP_TZ).date().isoformat(),
                "created_at": now_iso, "reason": f"Não recebido: {reason}", "source": SOURCE,
                "kind": "not_received", "order_id": order_id, "external_id": order.get("external_id"),
                "external_order_number": order.get("external_order_number"), "items": loss_items,
                "total_cost": round(sum(i["total_cost"] for i in loss_items), 2),
                "created_by_name": current_user.get("name"),
            })
        logger.warning(f"[NOSTFOOD] pedido {order.get('external_order_number')} marcado como NÃO RECEBIDO "
                       f"por {current_user.get('name')}: {reason}")
        await S.sio.emit("order_closed", {"order_id": order_id})
        await _emit_kds()
        return await S.db.orders.find_one({"id": order_id}, {"_id": 0})

    @router.get("/produtos-sem-ligacao", dependencies=[admin])
    async def unlinked_products():
        return await S.db.nostfood_unlinked.find({}, {"_id": 0}).sort("last_seen_at", -1).to_list(500)

    @router.get("/ligacoes", dependencies=[admin])
    async def product_links():
        return await S.db.nostfood_product_map.find({}, {"_id": 0}).to_list(1000)

    @router.post("/ligar-produto")
    async def link_product(body: dict, current_user: dict = admin):
        product_id = str(body.get("product_id") or "").strip()
        nf_id = body.get("nostfood_id")
        nf_id = str(nf_id).strip() if nf_id not in (None, "") else None
        nf_name = str(body.get("nostfood_name") or "").strip() or None
        if not product_id or not (nf_id or nf_name):
            raise HTTPException(status_code=400, detail="Informe product_id e o id ou o nome na NostFood")
        product = await S.db.products.find_one({"id": product_id}, {"_id": 0})
        if not product:
            raise HTTPException(status_code=404, detail="Produto do Gestor não encontrado")
        await ensure_indexes()
        keys = _item_keys(nf_id, nf_name)
        for key in keys:
            await S.db.nostfood_product_map.update_one({"nostfood_key": key}, {"$set": {
                "nostfood_key": key, "nostfood_id": nf_id, "nostfood_name": nf_name,
                "product_id": product_id, "product_name": product.get("name"),
                "linked_by_id": current_user.get("id"), "linked_by_name": current_user.get("name"),
                "linked_at": _now_iso()}}, upsert=True)
            await S.db.nostfood_unlinked.delete_one({"nostfood_key": key})

        # Pedidos ainda abertos passam a seguir a regra normal (estação e estoque).
        station_type = await _product_station_type(product)
        updated_orders = 0
        cursor = S.db.orders.find({"external_source": SOURCE, "is_closed": False}, {"_id": 0})
        for order in await cursor.to_list(500):
            changed = False
            for item in order.get("items", []):
                if not item.get("unlinked"):
                    continue
                same_id = nf_id is not None and item.get("external_item_id") == nf_id
                same_name = nf_name is not None and normalize_name(item.get("external_name")) == normalize_name(nf_name)
                if same_id or same_name or item.get("nostfood_key") in keys:
                    item.update({"product_id": product_id, "product_name": product.get("name"),
                                 "type": station_type, "unlinked": False,
                                 "stock_pending": False})
                    item.pop("stock_pending_reason", None)
                    changed = True
            if changed:
                await S.db.orders.update_one({"id": order["id"]}, {"$set": {"items": order["items"]}})
                updated_orders += 1
        if updated_orders:
            await _emit_kds()
        return {"message": "Produto ligado", "keys": keys, "open_orders_updated": updated_orders}

    @router.post("/pedidos/{order_id}/observacao")
    async def add_observation(order_id: str, body: dict, current_user: dict = cash):
        text = str((body or {}).get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Escreva a observação")
        if len(text) > 500:
            raise HTTPException(status_code=400, detail="Observação muito longa (máximo 500 caracteres)")
        order = await S.db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        if order.get("is_closed"):
            raise HTTPException(status_code=400, detail="Pedido já finalizado")
        obs = {"id": str(uuid.uuid4()), "text": text, "author_id": current_user.get("id"),
               "author_name": current_user.get("name"), "created_at": _now_iso(), "acks": {}}
        await S.db.orders.update_one({"id": order_id}, {"$push": {"observations": obs}})
        await S.sio.emit("order_observation", {"order_id": order_id, "observation": obs})
        await _emit_kds()
        return obs

    @router.post("/pedidos/{order_id}/observacao/{obs_id}/ciente")
    async def ack_observation(order_id: str, obs_id: str, body: dict, current_user: dict = kds):
        station = _validate_station(body)
        order = await S.db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Pedido não encontrado")
        observations = order.get("observations") or []
        obs = next((o for o in observations if o.get("id") == obs_id), None)
        if not obs:
            raise HTTPException(status_code=404, detail="Observação não encontrada")
        obs.setdefault("acks", {})[station] = {"by_id": current_user.get("id"),
                                               "by_name": current_user.get("name"), "at": _now_iso()}
        await S.db.orders.update_one({"id": order_id}, {"$set": {"observations": observations}})
        await _emit_kds()
        return obs

    @router.get("/kds/cancelados", dependencies=[staff])
    async def kds_cancelled():
        since = (datetime.now(timezone.utc) - timedelta(hours=CANCEL_KDS_WINDOW_HOURS)).isoformat()
        return await S.db.orders.find(
            {"kds_ack_pending": True, "status": "cancelled", "cancelled_at": {"$gte": since}},
            {"_id": 0}).to_list(100)

    @router.post("/pedidos/{order_id}/cancelamento/ciente")
    async def ack_cancel(order_id: str, body: dict, current_user: dict = kds):
        station = _validate_station(body)
        order = await S.db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order or order.get("status") != "cancelled":
            raise HTTPException(status_code=404, detail="Pedido cancelado não encontrado")
        acks = order.get("cancel_acks") or {}
        acks[station] = {"by_id": current_user.get("id"), "by_name": current_user.get("name"), "at": _now_iso()}
        pending = any(s not in acks for s in _required_cancel_stations(order))
        await S.db.orders.update_one({"id": order_id}, {"$set": {"cancel_acks": acks, "kds_ack_pending": pending}})
        updated = await S.db.orders.find_one({"id": order_id}, {"_id": 0})
        await S.sio.emit("kds_cancelled", updated)
        return updated

    @router.get("/perdas", dependencies=[admin])
    async def list_losses(data_inicio: Optional[str] = Query(None), data_fim: Optional[str] = Query(None)):
        query = {}
        for label, value in (("data_inicio", data_inicio), ("data_fim", data_fim)):
            if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise HTTPException(status_code=400, detail=f"{label} deve ser YYYY-MM-DD")
        if data_inicio or data_fim:
            query["date"] = {}
            if data_inicio:
                query["date"]["$gte"] = data_inicio
            if data_fim:
                query["date"]["$lte"] = data_fim
        losses = await S.db.stock_losses.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return {"data_inicio": data_inicio, "data_fim": data_fim, "count": len(losses),
                "total_cost": round(sum(float(x.get("total_cost", 0) or 0) for x in losses), 2),
                "losses": losses}

    return router


def register(api_router: APIRouter, app, server_module):
    """Registra as rotas e o ciclo de vida (índices e polling)."""
    global S
    S = server_module
    api_router.include_router(build_router(server_module.require_role, server_module.UserRole))

    async def _startup():
        if not enabled():
            logger.info("[NOSTFOOD] integração desligada (NOSTFOOD_ENABLED=false)")
            return
        await ensure_indexes()
        await get_enabled_at()
        if not _api_key():
            logger.warning("[NOSTFOOD] NOSTFOOD_API_KEY ausente: polling e status de volta não funcionam")
        _state["poll_task"] = asyncio.create_task(_poll_loop())
        logger.info(f"[NOSTFOOD] integração ligada; polling a cada {poll_seconds()} s")

    async def _shutdown():
        task = _state.get("poll_task")
        if task:
            task.cancel()

    app.add_event_handler("startup", _startup)
    app.add_event_handler("shutdown", _shutdown)
