"""Gestor Resto - consulta escalável e não destrutiva de comandas.

Sem regra de descarte após N documentos. Usa cursor MongoDB (_id), índice nativo,
e páginas de até 100 registros; nunca retorna 1 milhão de documentos de uma vez.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re

from bson import ObjectId
from fastapi import Depends, HTTPException, Query

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _bounds(date_start, date_end):
    def parse(v):
        try:
            return datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=SAO_PAULO)
        except ValueError:
            raise HTTPException(422, "Data inválida; use AAAA-MM-DD")
    lo = parse(date_start).astimezone(timezone.utc).isoformat() if date_start else None
    hi = (parse(date_end) + timedelta(days=1)).astimezone(timezone.utc).isoformat() if date_end else None
    if lo and hi and lo >= hi:
        raise HTTPException(422, "Data inicial posterior à final")
    return lo, hi


def register_order_history_routes(api_router, db, require_role, UserRole):
    admin_only = require_role([UserRole.ADMIN])

    @api_router.get("/history/orders")
    async def search_order_history(
        text: str = Query(default="", max_length=100),
        start: str = Query(default="", max_length=10),
        end: str = Query(default="", max_length=10),
        channel: str = Query(default="all"),
        state: str = Query(default="all"),
        before: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        current_user: dict = Depends(admin_only),
    ):
        if channel not in {"all", "online", "onsite"}:
            raise HTTPException(422, "Canal inválido")
        if state not in {"all", "closed", "open", "cancelled"}:
            raise HTTPException(422, "Status inválido")
        query = {}
        if channel == "online":
            query["source"] = "online"
        elif channel == "onsite":
            query["source"] = {"$ne": "online"}
        if state == "closed":
            query["is_closed"] = True
            query["status"] = {"$ne": "cancelled"}
        elif state == "open":
            query["is_closed"] = False
        elif state == "cancelled":
            query["status"] = "cancelled"
        lo, hi = _bounds(start, end)
        if lo or hi:
            query["created_at"] = {}
            if lo:
                query["created_at"]["$gte"] = lo
            if hi:
                query["created_at"]["$lt"] = hi
        term = text.strip()
        if term:
            if re.fullmatch(r"[a-fA-F0-9-]{36}", term):
                query["id"] = term.lower()
            elif term.startswith("#") and re.fullmatch(r"#[a-fA-F0-9]{4,12}", term):
                query["id"] = {"$regex": "^" + re.escape(term[1:].lower())}
            elif term.isdigit():
                query["tab_number"] = int(term)
            else:
                raise HTTPException(422, "Busque pelo UUID, #código curto ou número da comanda física")
        if before:
            if not ObjectId.is_valid(before):
                raise HTTPException(422, "Cursor inválido")
            query["_id"] = {"$lt": ObjectId(before)}

        # Campos mínimos: evita carregar fotos/descrições/itens de todos os pedidos.
        projection = {"id": 1, "tab_number": 1, "table_number": 1,
                      "created_at": 1, "closed_at": 1, "is_closed": 1,
                      "status": 1, "source": 1, "platform": 1,
                      "total": 1, "service_fee": 1, "is_comp": 1}
        docs = await db.orders.find(query, projection).sort("_id", -1).limit(limit + 1).to_list(length=limit + 1)
        next_cursor = str(docs[limit-1]["_id"]) if len(docs) > limit else None
        items = []
        for o in docs[:limit]:
            code = f"Comanda {o['tab_number']}" if o.get("tab_number") is not None else "#" + o["id"][:8].upper()
            items.append({"id": o.get("id"), "code": code,
                          "tab_number": o.get("tab_number"), "table_number": o.get("table_number"),
                          "created_at": o.get("created_at"), "closed_at": o.get("closed_at"),
                          "is_closed": o.get("is_closed"), "status": o.get("status"),
                          "source": o.get("source", "presencial"), "platform": o.get("platform"),
                          "total": o.get("total"), "service_fee": o.get("service_fee"),
                          "is_comp": o.get("is_comp", False)})
        return {"items": items, "next_cursor": next_cursor, "page_size": limit,
                "note": "Consulta paginada, sem limite máximo de registros armazenados. Não exclui dados."}

    @api_router.get("/history/orders/overview")
    async def order_history_overview(current_user: dict = Depends(admin_only)):
        # Rápida, mas ESTIMADA: use para evolução de volume, não auditoria fiscal.
        return {
            "orders_estimated": await db.orders.estimated_document_count(),
            "note": "Contagem estimada. Nenhuma comanda é excluída automaticamente.",
        }

    @api_router.get("/history/orders/monthly-summary")
    async def monthly_history_summary(year: int = Query(ge=2020, le=2100),
                                      current_user: dict = Depends(admin_only)):
        """Compara faturamento BRUTO registrado, não repasse nem lucro.

        Compatível com pedidos cujo closed_at é ISO UTC ou datetime do Mongo.
        Faixa de datas do ano local é convertida para UTC.
        """
        low = datetime(year, 1, 1, tzinfo=SAO_PAULO).astimezone(timezone.utc)
        high = datetime(year + 1, 1, 1, tzinfo=SAO_PAULO).astimezone(timezone.utc)
        lo, hi = low.isoformat(), high.isoformat()
        pipeline = [
            {"$match": {
                "is_closed": True, "status": {"$ne": "cancelled"},
                "is_comp": {"$ne": True},
                "$or": [
                    {"closed_at": {"$gte": lo, "$lt": hi}},
                    {"closed_at": {"$gte": low, "$lt": high}},
                ],
            }},
            {"$project": {
                "month": {"$dateToString": {
                    "format": "%Y-%m", "timezone": "America/Sao_Paulo",
                    "date": {"$convert": {"input": "$closed_at", "to": "date", "onError": None, "onNull": None}},
                    "onNull": "unknown",
                }},
                "channel": {"$cond": [{"$eq": ["$source", "online"]}, "online", "onsite"]},
                "gross": {"$convert": {"input": "$total", "to": "double", "onError": 0, "onNull": 0}},
                "service_fee": {"$convert": {"input": "$service_fee", "to": "double", "onError": 0, "onNull": 0}},
            }},
            {"$group": {
                "_id": {"month": "$month", "channel": "$channel"},
                "orders": {"$sum": 1},
                "gross": {"$sum": "$gross"},
                "service_fee": {"$sum": "$service_fee"},
            }},
            {"$sort": {"_id.month": 1, "_id.channel": 1}},
        ]
        results = await db.orders.aggregate(pipeline).to_list(length=100)
        return {"year": year,
                "months": [{"month": v["_id"]["month"], "channel": v["_id"]["channel"],
                            "orders": v["orders"], "gross": round(v["gross"], 2),
                            "service_fee": round(v["service_fee"], 2)} for v in results],
                "note": "Valores BRUTOS de pedidos fechados no período. Delivery não significa repasse recebido; lucro e conciliação financeira exigem outras fontes."}

    @api_router.get("/history/orders/{order_id}")
    async def order_history_detail(order_id: str, current_user: dict = Depends(admin_only)):
        if not re.fullmatch(r"[a-fA-F0-9-]{8,100}", order_id):
            raise HTTPException(422, "Identificador inválido")
        order = await db.orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            raise HTTPException(404, "Comanda não encontrada")
        payments = await db.payments.find({"order_id": order_id}, {"_id": 0}).to_list(length=200)
        invoices = await db.invoices.find({"order_id": order_id}, {"_id": 0}).to_list(length=50)
        return {"order": order, "payments": payments, "invoices": invoices}


async def ensure_history_indexes(db):
    """Executar uma única vez durante janela de manutenção ou no bootstrap.
    Nunca cria TTL, nunca apaga registros. Monitorar o impacto do build dos índices.
    """
    await db.orders.create_index([("id", 1)], name="orders_id_lookup")
    await db.orders.create_index([("created_at", -1)], name="orders_created_at_desc")
    await db.orders.create_index([("closed_at", -1)], name="orders_closed_at_desc")
    await db.orders.create_index([("is_closed", 1), ("closed_at", -1)], name="orders_closed_range")
    await db.orders.create_index([("tab_number", 1)], name="orders_tab_lookup")
    await db.payments.create_index([("order_id", 1)], name="payments_order_lookup")
    await db.invoices.create_index([("order_id", 1)], name="invoices_order_lookup")
    await db.cash_registers.create_index([("closed_at", -1)], name="cash_register_closed_at_desc")
    await db.cash_exception_resolutions.create_index([("id", 1)], unique=True, name="cash_exception_resolution_unique")
