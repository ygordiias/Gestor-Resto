"""Gestor Resto - fechamento administrativo COM RESSALVAS.

Extensão para o server.py (FastAPI/Motor) que JÁ implementa fechamento normal
com prévia assinada. Não altera pedidos, pagamentos nem notas existentes.

ATENÇÃO: a checagem e o update do caixa não são uma transação multi-documento.
Antes de usar em produção, teste a concorrência com recebimentos e abertura de
novas comandas. Para garantia transacional completa, as rotas de escrita devem
cooperar com um estado de bloqueio/lock no caixa.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
import hashlib
import json
import re
import uuid

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from bson import ObjectId

METHODS = {"cash", "pix", "credit", "debit", "card", "voucher"}
MAX_SHIFT_ORDERS = 10000  # limite de segurança por expediente, NÃO é retenção
MAX_ISSUES = 500  # acima disso recusa fechamento automático com ressalvas


def _cents(value):
    try:
        v = Decimal(str(value or 0))
        if not v.is_finite() or v < 0 or v > Decimal("100000000"):
            raise ValueError("fora de faixa")
        return int((v * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, InvalidOperation):
        return None


def _money(cents):
    return round(cents / 100, 2) if cents is not None else None


def _dt_now():
    return datetime.now(timezone.utc).isoformat()


def _short(order):
    if order.get("tab_number") is not None:
        return "Comanda " + str(order["tab_number"])
    return "#" + str(order.get("id", "????????"))[:8].upper()


def _payment_issue(order, payments):
    """Lista o motivo e as quantias registradas, sem corrigir valores."""
    total = _cents(order.get("total"))
    vals = [_cents(p.get("amount")) for p in payments]
    if total is None or any(v is None for v in vals):
        reason = "Total ou pagamento inválido"
    else:
        received = sum(vals)
        cash = sum(v for v, p in zip(vals, payments) if p.get("method") == "cash")
        unknown = sorted({str(p.get("method")) for p in payments if p.get("method") not in METHODS})
        if unknown:
            reason = "Método de pagamento desconhecido: " + ", ".join(unknown)
        elif received < total:
            reason = "Pagamento abaixo do valor da comanda"
        elif received - total > cash:
            reason = "Excesso de pagamento sem dinheiro suficiente para troco"
        else:
            reason = None
    if reason is None:
        return None
    paid = sum(v for v in vals if v is not None)
    return {
        "order_id": order["id"],
        "code": _short(order),
        "tab_number": order.get("tab_number"),
        "table_number": order.get("table_number"),
        "reason": reason,
        "order_total": _money(total),
        "paid": _money(paid),
        "difference": _money(total - paid) if total is not None else None,
        "closed_at": order.get("closed_at"),
        "payments": [
            {"method": p.get("method"), "amount": p.get("amount"), "created_at": p.get("created_at")}
            for p in payments[:50]
        ],
    }


async def _shift_snapshot(db, register, until, preview):
    """Congela diagnóstico e resumo de cada pagamento do expediente em hash.

    Não carrega o histórico de 1 milhão de comandas: apenas o expediente aberto.
    """
    h = hashlib.sha256()
    issues = []
    counted = 0
    query = {
        "is_closed": True,
        "closed_at": {"$gte": register["opened_at"], "$lte": until},
    }
    cursor = db.orders.find(query, {"_id": 0}).sort([("closed_at", 1), ("id", 1)])
    async for order in cursor:
        counted += 1
        if counted > MAX_SHIFT_ORDERS:
            raise HTTPException(409, "Expediente com registros demais para a auditoria automática; contate o suporte")
        payments = await db.payments.find(
            {"order_id": order["id"]},
            {"_id": 0, "id": 1, "amount": 1, "method": 1, "created_at": 1},
        ).sort([("created_at", 1), ("id", 1)]).to_list(length=501)
        if len(payments) > 500:
            raise HTTPException(409, "Comanda com número incomum de pagamentos; conferência manual necessária")
        fingerprint = {
            "id": order["id"], "total": order.get("total"),
            "closed_at": order.get("closed_at"), "source": order.get("source"),
            "status": order.get("status"), "is_comp": order.get("is_comp"),
            "payments": payments,
        }
        h.update(json.dumps(fingerprint, sort_keys=True, default=str, ensure_ascii=False).encode())
        h.update(b"\n")
        if order.get("source") == "online" or order.get("status") == "cancelled" or order.get("is_comp"):
            continue
        issue = _payment_issue(order, payments)
        if issue:
            issues.append(issue)
            if len(issues) > MAX_ISSUES:
                raise HTTPException(409, "Pendências demais para encerrar sem conciliação prévia")

    open_query = {"is_closed": False, "source": {"$ne": "online"}}
    open_rows = await db.orders.find(
        open_query, {"_id": 0, "id": 1, "tab_number": 1, "table_number": 1,
                     "total": 1, "created_at": 1}
    ).sort("id", 1).to_list(length=MAX_ISSUES + 1)
    if len(open_rows) > MAX_ISSUES:
        raise HTTPException(409, "Comandas presenciais abertas demais para transferência")
    open_orders = [{"order_id": x["id"], "code": _short(x),
                    "table_number": x.get("table_number"), "total": x.get("total"),
                    "created_at": x.get("created_at")}
                   for x in open_rows]
    for row in open_rows:
        h.update(json.dumps(row, sort_keys=True, default=str).encode())
        h.update(b"\n")
    audit = {
        "register_id": register["id"],
        "opened_at": register["opened_at"],
        "preview_digest": hashlib.sha256(json.dumps(
            {k: v for k, v in preview.items() if k not in {"generated_at", "preview_token"}},
            sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(),
        "shift_digest": h.hexdigest(),
        "issues": issues,
        "open_orders": open_orders,
        "checked_closed_orders": counted,
    }
    audit["digest"] = hashlib.sha256(json.dumps(
        audit, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return audit


class AdministrativeClose(BaseModel):
    preview_token: str = Field(min_length=20)
    admin_email: str = Field(min_length=5, max_length=180)
    admin_password: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=15, max_length=800)
    counted_cash: Decimal = Field(ge=0, le=100000000)
    printed_confirmed: bool


class ExceptionResolution(BaseModel):
    order_id: str = Field(min_length=8, max_length=100)
    resolution: str = Field(min_length=15, max_length=800)
    reference: str = Field(default="", max_length=150)
    request_id: str = Field(min_length=12, max_length=100)
    action: Literal["resolved", "reopened"] = "resolved"


def register_admin_cash_routes(api_router, db, require_role, UserRole,
                              preview_cash_register, jwt, SECRET_KEY,
                              ALGORITHM, verify_password):
    # O diagnóstico pode ser visto por operador, mas SOMENTE um admin reautenticado fecha.
    cashier_role = require_role([UserRole.ADMIN, UserRole.CASHIER])
    admin_role = require_role([UserRole.ADMIN])

    async def _get_register():
        register = await db.cash_registers.find_one({"is_open": True}, {"_id": 0})
        if not register:
            raise HTTPException(404, "Nenhum caixa aberto")
        return register

    async def _diagnose(user):
        register = await _get_register()
        preview = await preview_cash_register(user)
        if preview.get("register_id") != register["id"]:
            raise HTTPException(409, "Caixa mudou durante a conferência; atualize")
        audit = await _shift_snapshot(db, register, preview["generated_at"], preview)
        if (len(audit["open_orders"]) != preview.get("open_orders", 0)):
            raise HTTPException(409, "Comandas alteradas durante a conferência; atualize")
        return register, preview, audit

    @api_router.get("/cash-register/admin-exception/diagnostic")
    async def admin_exception_diagnostic(current_user: dict = Depends(cashier_role)):
        register, preview, audit = await _diagnose(current_user)
        token = jwt.encode({
            "purpose": "cash_admin_exception",
            "register_id": register["id"], "operator_id": current_user["id"],
            "digest": audit["digest"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        }, SECRET_KEY, algorithm=ALGORITHM)
        return {
            "register_id": register["id"], "opened_at": register["opened_at"],
            "generated_at": preview["generated_at"],
            "preview_token": token,
            "warnings": preview.get("warnings", []),
            "issues": audit["issues"], "open_orders": audit["open_orders"],
            "payment_methods_reconciled": preview.get("payment_methods", {}),
            "total_sales_reconciled": preview.get("total_sales", 0),
            "expected_cash_partial": preview.get("expected_cash", 0),
            "initial_amount": preview.get("initial_amount", 0),
            "withdrawals": preview.get("withdrawals", 0),
            "deposits": preview.get("deposits", 0),
            "online_completed": preview.get("online_completed", {}),
            "note": "Estimativa parcial: pagamentos inconsistentes NÃO entram na soma conciliada. Confira dinheiro físico.",
        }

    @api_router.post("/cash-register/admin-exception/close")
    async def admin_exception_close(data: AdministrativeClose,
                                   current_user: dict = Depends(cashier_role)):
        if data.printed_confirmed is not True:
            raise HTTPException(400, "Confirme que a prévia foi impressa e conferida")
        if len(data.reason.strip()) < 15:
            raise HTTPException(422, "Explique a ressalva com pelo menos 15 caracteres")
        admin = await db.users.find_one({"email": data.admin_email.strip().lower()}, {"_id": 0})
        if (not admin or admin.get("role") not in {"admin", "superadmin"}
                or admin.get("is_active") is False):
            raise HTTPException(403, "Autorização administrativa inválida")
        try:
            valid = verify_password(data.admin_password, admin.get("password", ""))
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(403, "Autorização administrativa inválida")
        try:
            token = jwt.decode(data.preview_token, SECRET_KEY, algorithms=[ALGORITHM])
        except Exception:
            raise HTTPException(409, "Prévia expirada ou inválida. Atualize e imprima novamente")
        if token.get("purpose") != "cash_admin_exception" or token.get("operator_id") != current_user["id"]:
            raise HTTPException(409, "Prévia não pertence a este operador")
        register, preview, audit = await _diagnose(current_user)
        if token.get("register_id") != register["id"] or token.get("digest") != audit["digest"]:
            raise HTTPException(409, "As comandas ou pagamentos mudaram. Gere e imprima uma nova prévia")
        if not (audit["issues"] or audit["open_orders"] or preview.get("warnings")):
            raise HTTPException(409, "Caixa sem ressalvas. Utilize o fechamento normal")
        # Segurança da V1: não encerrar com pedidos ainda abertos, pois uma cobrança
        # enquanto não houver novo caixa aberto pode ficar fora dos dois períodos.
        if audit["open_orders"]:
            raise HTTPException(409, "Existem comandas presenciais abertas. Finalize-as ou implemente transferência controlada antes de encerrar")
        counted_cents = _cents(data.counted_cash)
        if counted_cents is None:
            raise HTTPException(422, "Dinheiro contado inválido")
        now = _dt_now()
        report = {
            **{k: v for k, v in preview.items() if k != "preview_token"},
            "closed_at": now,
            "opened_by": register.get("opened_by"),
            "closed_by": current_user.get("name"),
            "closed_by_id": current_user["id"],
            "closing_status": "closed_with_exceptions",
            "closed_with_exceptions": True,
            "admin_authorized_by": admin.get("name"),
            "admin_authorized_by_id": admin["id"],
            "admin_reason": data.reason.strip(),
            "counted_cash": _money(counted_cents),
            "expected_cash_reconciled_only": preview.get("expected_cash"),
            "difference_vs_partial_estimate": _money(counted_cents - (_cents(preview.get("expected_cash")) or 0)),
            "difference_is_provisional": True,
            "exceptions": audit["issues"],
            "open_orders_at_diagnostic": audit["open_orders"],
            "exceptions_revision": audit["digest"],
            "needs_reconciliation": True,
            "audit_notice": "Não foram criados pagamentos, notas ou recibos. O fechamento exige que não existam comandas presenciais em aberto.",
        }
        # Atualização atômica de UM documento: relatório e autorização são salvos juntos.
        result = await db.cash_registers.update_one(
            {"id": register["id"], "is_open": True},
            {"$set": {
                "is_open": False, "closed_at": now,
                "closed_by": current_user.get("name"),
                "closed_by_id": current_user["id"],
                "final_amount": _money(counted_cents),
                "total_sales": preview.get("total_sales", 0),
                "closing_status": "closed_with_exceptions",
                "needs_reconciliation": True,
                "closing_report": report,
            }},
        )
        if result.modified_count != 1:
            raise HTTPException(409, "Este caixa já foi fechado por outra operação")
        return {"message": "Caixa encerrado COM RESSALVAS. Pendências preservadas.", "report": report}

    @api_router.get("/cash-register/admin-exception/history")
    async def admin_exception_history(limit: int = Query(default=30, ge=1, le=100),
                                     before: str | None = Query(default=None),
                                     current_user: dict = Depends(admin_role)):
        query = {"closing_status": "closed_with_exceptions"}
        if before:
            if not ObjectId.is_valid(before):
                raise HTTPException(422, "Cursor de histórico inválido")
            query["_id"] = {"$lt": ObjectId(before)}
        cursor = db.cash_registers.find(query, {"id": 1, "closed_at": 1, "closing_report": 1}).sort("_id", -1).limit(limit + 1)
        entries = await cursor.to_list(length=limit + 1)
        next_cursor = str(entries[limit - 1]["_id"]) if len(entries) > limit else None
        return {"items": [{"register_id": x.get("id"), "closed_at": x.get("closed_at"),
                           "report": x.get("closing_report")} for x in entries[:limit]],
                "next_cursor": next_cursor}

    @api_router.post("/cash-register/admin-exception/{register_id}/resolution")
    async def append_resolution(register_id: str, data: ExceptionResolution,
                                current_user: dict = Depends(admin_role)):
        closed = await db.cash_registers.find_one({"id": register_id, "closing_status": "closed_with_exceptions"}, {"_id": 0})
        if not closed:
            raise HTTPException(404, "Fechamento com ressalvas não encontrado")
        items = closed.get("closing_report", {}).get("exceptions", [])
        if data.order_id not in {str(x.get("order_id")) for x in items}:
            raise HTTPException(422, "Comanda não pertence às ressalvas desse fechamento")
        record = {"id": data.request_id, "register_id": register_id,
                  "order_id": data.order_id, "resolution": data.resolution.strip(),
                  "reference": data.reference.strip(), "action": data.action,
                  "admin_id": current_user["id"],
                  "admin_name": current_user.get("name"), "created_at": _dt_now()}
        try:
            await db.cash_exception_resolutions.insert_one(record)
        except Exception as exc:
            if exc.__class__.__name__ == "DuplicateKeyError":
                return {"message": "Registro já enviado", "already_recorded": True}
            raise
        return {"message": "Anotação de conciliação salva. Valores originais preservados."}

    @api_router.get("/cash-register/admin-exception/{register_id}/resolutions")
    async def list_exception_resolutions(register_id: str,
                                         current_user: dict = Depends(admin_role)):
        closed = await db.cash_registers.find_one(
            {"id": register_id, "closing_status": "closed_with_exceptions"}, {"_id": 0, "id": 1})
        if not closed:
            raise HTTPException(404, "Fechamento com ressalvas não encontrado")
        rows = await db.cash_exception_resolutions.find(
            {"register_id": register_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(length=500)
        return {"items": rows, "note": "Histórico de conferências (anotações), sem alteração dos pagamentos originais"}
