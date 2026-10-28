"""EMAÚS: relatório de gorjetas e crédito interno de funcionários.

Extensão isolada para o backend FastAPI existente. Registros de crédito NÃO são
pagamentos do caixa nem comandas presenciais. Não faz desconto salarial automático.
V1: NÃO envia pedidos à cozinha/bar nem realiza baixa de estoque; estes fluxos
precisam de integração transacional específica antes de serem habilitados.
"""
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
import re
import uuid

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def cents(value, *, max_value=100000):
    try:
        v = Decimal(str(value))
        if not v.is_finite() or v < 0 or v > Decimal(max_value):
            raise ValueError
        return int((v * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(status_code=422, detail="Valor monetário inválido")


def money(value_cents):
    return round(int(value_cents) / 100, 2)


def month_now():
    return datetime.now(LOCAL_TZ).strftime("%Y-%m")


def local_iso():
    return datetime.now(timezone.utc).isoformat()


def validate_month(value):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value or ""):
        raise HTTPException(status_code=422, detail="Mês deve ser AAAA-MM")
    return value


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    monthly_limit: float = Field(ge=0, le=100000)
    discount_pct: float = Field(default=0, ge=0, le=100)


class EmployeeUpdate(BaseModel):
    monthly_limit: float = Field(ge=0, le=100000)
    discount_pct: float = Field(default=0, ge=0, le=100)
    active: bool = True


class EmployeeItem(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=30)


class EmployeePurchase(BaseModel):
    employee_id: str
    request_id: str = Field(min_length=12, max_length=100)
    items: list[EmployeeItem] = Field(min_length=1, max_length=20)


class EmployeeSettlement(BaseModel):
    request_id: str = Field(min_length=12, max_length=100)
    month: str
    amount: float = Field(gt=0, le=100000)
    note: str = Field(min_length=4, max_length=250)


class EmployeeVoid(BaseModel):
    request_id: str = Field(min_length=12, max_length=100)
    purchase_id: str
    note: str = Field(min_length=4, max_length=250)


def register_finance_routes(api_router, db, require_role, UserRole):
    admin_only = require_role([UserRole.ADMIN])
    cashier_or_admin = require_role([UserRole.ADMIN, UserRole.CASHIER])

    async def _accounts():
        await db.employee_credit_accounts.create_index(
            [("employee_id", ASCENDING), ("month", ASCENDING)], unique=True
        )

    async def _employee(employee_id):
        emp = await db.employee_credit_employees.find_one({"id": employee_id}, {"_id": 0})
        if not emp:
            raise HTTPException(status_code=404, detail="Funcionário não encontrado")
        return emp

    async def _monthly_account(emp, month):
        await _accounts()
        account = await db.employee_credit_accounts.find_one(
            {"employee_id": emp["id"], "month": month}, {"_id": 0}
        )
        if account:
            return account
        record = {
            "employee_id": emp["id"], "month": month,
            "limit_cents": emp["monthly_limit_cents"],
            "charged_cents": 0, "paid_cents": 0, "transactions": [],
            "created_at": local_iso(),
        }
        try:
            await db.employee_credit_accounts.update_one(
                {"employee_id": emp["id"], "month": month},
                {"$setOnInsert": record}, upsert=True
            )
        except DuplicateKeyError:
            pass  # outra requisição criou a conta simultaneamente
        return await db.employee_credit_accounts.find_one(
            {"employee_id": emp["id"], "month": month}, {"_id": 0}
        )

    async def _overdue(emp_id, month):
        values = await db.employee_credit_accounts.find(
            {"employee_id": emp_id, "month": {"$lt": month}},
            {"_id": 0, "charged_cents": 1, "paid_cents": 1}
        ).to_list(length=None)
        return sum(max(0, x.get("charged_cents", 0) - x.get("paid_cents", 0)) for x in values)

    def _summary(account):
        charged = account.get("charged_cents", 0)
        paid = account.get("paid_cents", 0)
        limit = account.get("limit_cents", 0)
        return {
            "month": account["month"],
            "limit": money(limit),
            "used": money(charged),
            "paid": money(paid),
            "outstanding": money(max(0, charged - paid)),
            "available": money(max(0, limit - charged)),
        }

    @api_router.get("/reports/service-fees/weekly")
    async def weekly_service_fees(
        week: str | None = Query(default=None),
        current_user: dict = Depends(admin_only),
    ):
        """Somente pedidos presenciais fechados e com pagamento conciliado.

        Semana local de São Paulo de segunda 00:00 a segunda seguinte 00:00.
        Não equivale a lucro líquido nem define distribuição das gorjetas.
        """
        try:
            chosen = date.fromisoformat(week) if week else datetime.now(LOCAL_TZ).date()
        except ValueError:
            raise HTTPException(status_code=422, detail="Data da semana inválida (AAAA-MM-DD)")
        monday = chosen - timedelta(days=chosen.weekday())
        next_monday = monday + timedelta(days=7)
        start_utc = datetime.combine(monday, datetime.min.time(), LOCAL_TZ).astimezone(timezone.utc).isoformat()
        end_utc = datetime.combine(next_monday, datetime.min.time(), LOCAL_TZ).astimezone(timezone.utc).isoformat()
        orders = await db.orders.find({
            "is_closed": True,
            "closed_at": {"$gte": start_utc, "$lt": end_utc},
            "source": {"$ne": "online"},
            "is_comp": {"$ne": True},
            "status": {"$ne": "cancelled"},
        }, {"_id": 0}).to_list(length=None)
        ids = [o["id"] for o in orders]
        all_payments = await db.payments.find(
            {"order_id": {"$in": ids}}, {"_id": 0}
        ).to_list(length=None) if ids else []
        by_order = {}
        for p in all_payments:
            by_order.setdefault(p.get("order_id"), []).append(p)
        days = {str(monday + timedelta(days=i)): {"products_cents": 0, "fee_cents": 0, "count": 0} for i in range(7)}
        skipped = []
        for order in orders:
            paid_rows = by_order.get(order["id"], [])
            total = cents(order.get("total", 0))
            received = sum(cents(p.get("amount")) for p in paid_rows)
            cash_received = sum(cents(p.get("amount")) for p in paid_rows if p.get("method") == "cash")
            change = received - total
            if total > 0 and (not paid_rows or received < total or change > cash_received or
                                  any(p.get("method") not in {"cash", "pix", "credit", "debit", "card", "voucher"} for p in paid_rows)):
                skipped.append(order.get("tab_number") or order["id"])
                continue
            try:
                day = datetime.fromisoformat(order["closed_at"].replace("Z", "+00:00")).astimezone(LOCAL_TZ).date().isoformat()
            except (ValueError, TypeError):
                skipped.append(order.get("tab_number") or order["id"])
                continue
            if day not in days:
                continue
            fee = min(cents(order.get("service_fee", 0)), total)
            days[day]["fee_cents"] += fee
            days[day]["products_cents"] += total - fee
            days[day]["count"] += 1
        rows = [
            {"date": day, "orders": data["count"], "product_sales": money(data["products_cents"]),
             "service_fee": money(data["fee_cents"]), "gross_total": money(data["products_cents"] + data["fee_cents"])}
            for day, data in days.items()
        ]
        return {
            "week_start": monday.isoformat(), "week_end_inclusive": (next_monday-timedelta(days=1)).isoformat(),
            "timezone": "America/Sao_Paulo", "rows": rows,
            "summary": {
                "orders": sum(x["orders"] for x in rows),
                "product_sales": money(sum(x["products_cents"] for x in days.values())),
                "service_fee": money(sum(x["fee_cents"] for x in days.values())),
                "gross_total": money(sum(x["products_cents"] + x["fee_cents"] for x in days.values())),
            },
            "excluded_unreconciled": skipped,
            "note": "Taxa de serviço destacada, não constitui cálculo de lucro líquido."
        }

    @api_router.get("/employee-credit/employees")
    async def list_employees(current_user: dict = Depends(cashier_or_admin)):
        month = month_now()
        emps = await db.employee_credit_employees.find({}, {"_id": 0}).sort("name", 1).to_list(length=None)
        accounts = await db.employee_credit_accounts.find({}, {"_id": 0}).to_list(length=None)
        grouped = {}
        for a in accounts:
            grouped.setdefault(a["employee_id"], []).append(a)
        result = []
        for emp in emps:
            docs = grouped.get(emp["id"], [])
            current = next((x for x in docs if x["month"] == month), None)
            charged = current.get("charged_cents", 0) if current else 0
            paid = current.get("paid_cents", 0) if current else 0
            overdue = sum(max(0, x.get("charged_cents", 0) - x.get("paid_cents", 0)) for x in docs if x["month"] < month)
            result.append({
                "id": emp["id"], "name": emp["name"], "active": emp.get("active", True),
                "discount_pct": emp.get("discount_pct", 0), "month": month,
                "limit": money(current["limit_cents"] if current else emp["monthly_limit_cents"]),
                "used": money(charged), "paid": money(paid),
                "outstanding": money(max(0, charged - paid)),
                "overdue": money(overdue),
                "available": money(max(0, (current["limit_cents"] if current else emp["monthly_limit_cents"]) - charged)) if not overdue else 0,
            })
        return {"month": month, "employees": result}

    @api_router.post("/employee-credit/employees")
    async def create_employee(data: EmployeeCreate, current_user: dict = Depends(admin_only)):
        name = data.name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=422, detail="Informe o nome completo")
        emp = {"id": str(uuid.uuid4()), "name": name, "active": True,
               "monthly_limit_cents": cents(data.monthly_limit), "discount_pct": data.discount_pct,
               "created_at": local_iso(), "created_by": current_user["id"]}
        await db.employee_credit_employees.insert_one(emp)
        emp.pop("_id", None)
        return {"id": emp["id"], "name": emp["name"]}

    @api_router.put("/employee-credit/employees/{employee_id}")
    async def update_employee(employee_id: str, data: EmployeeUpdate, current_user: dict = Depends(admin_only)):
        emp = await _employee(employee_id)
        month = month_now()
        target_limit = cents(data.monthly_limit)
        account = await _monthly_account(emp, month)
        if target_limit < account["charged_cents"]:
            raise HTTPException(status_code=409, detail="Novo limite menor que o consumo já registrado neste mês")
        update = await db.employee_credit_accounts.update_one(
            {"employee_id": employee_id, "month": month, "charged_cents": {"$lte": target_limit}},
            {"$set": {"limit_cents": target_limit}}
        )
        if update.matched_count == 0:
            raise HTTPException(status_code=409, detail="Limite mudou durante a edição; tente novamente")
        await db.employee_credit_employees.update_one(
            {"id": employee_id},
            {"$set": {"monthly_limit_cents": target_limit,
                      "discount_pct": data.discount_pct, "active": data.active}}
        )
        return {"message": "Cadastro atualizado"}

    @api_router.get("/employee-credit/employees/{employee_id}/statement")
    async def employee_statement(employee_id: str, month: str = Query(default=None), current_user: dict = Depends(admin_only)):
        emp = await _employee(employee_id)
        month = validate_month(month or month_now())
        account = await db.employee_credit_accounts.find_one(
            {"employee_id": employee_id, "month": month}, {"_id": 0}
        )
        if not account:
            account = {"month": month, "limit_cents": emp["monthly_limit_cents"], "charged_cents": 0, "paid_cents": 0, "transactions": []}
        return {"employee": emp["name"], **_summary(account), "transactions": account["transactions"]}

    @api_router.post("/employee-credit/purchases")
    async def employee_purchase(data: EmployeePurchase, current_user: dict = Depends(cashier_or_admin)):
        employee = await _employee(data.employee_id)
        if not employee.get("active", True):
            raise HTTPException(status_code=409, detail="Crédito deste funcionário está bloqueado")
        month = month_now()
        account = await _monthly_account(employee, month)
        for tx in account.get("transactions", []):
            if tx.get("id") == data.request_id:
                return {"message": "Consumo já registrado", "transaction": tx, "already_recorded": True}
        overdue = await _overdue(employee["id"], month)
        if overdue > 0:
            raise HTTPException(status_code=409, detail="Há saldo pendente de mês anterior. Acerto necessário antes de novos consumos")
        aggregated = {}
        for item in data.items:
            aggregated[item.product_id] = aggregated.get(item.product_id, 0) + item.quantity
        if any(qty > 30 for qty in aggregated.values()):
            raise HTTPException(status_code=422, detail="Quantidade máxima por produto: 30")
        products = await db.products.find({"id": {"$in": list(aggregated)}}, {"_id": 0}).to_list(length=None)
        by_id = {p["id"]: p for p in products}
        details = []
        total_cents = 0
        discount = Decimal(str(employee.get("discount_pct", 0)))
        for pid, qty in aggregated.items():
            product = by_id.get(pid)
            if not product or product.get("is_available") is False:
                raise HTTPException(status_code=422, detail="Produto não encontrado ou indisponível")
            unit_cents = cents(product["price"])
            line_cents = int((Decimal(unit_cents * qty) * (Decimal("100") - discount) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            details.append({"product_id": pid, "product_name": product["name"], "quantity": qty,
                            "unit_price": money(unit_cents), "line_total": money(line_cents)})
            total_cents += line_cents
        if total_cents <= 0:
            raise HTTPException(status_code=422, detail="Consumo precisa ter valor positivo")
        tx = {"id": data.request_id, "type": "purchase", "at": local_iso(),
              "items": details, "amount": money(total_cents), "discount_pct": employee.get("discount_pct", 0),
              "created_by": current_user.get("name", "Operador"),
              "stock_sync": "not_integrated"}
        limit_cents = account["limit_cents"]
        if total_cents > limit_cents:
            raise HTTPException(status_code=409, detail="Consumo acima do limite mensal")
        updated = await db.employee_credit_accounts.update_one(
            {"employee_id": employee["id"], "month": month,
             "limit_cents": limit_cents,
             "charged_cents": {"$lte": limit_cents - total_cents},
             "transactions.id": {"$ne": data.request_id}},
            {"$inc": {"charged_cents": total_cents}, "$push": {"transactions": tx}}
        )
        if updated.modified_count != 1:
            fresh = await db.employee_credit_accounts.find_one({"employee_id": employee["id"], "month": month}, {"_id": 0})
            if fresh:
                prev = next((t for t in fresh.get("transactions", []) if t.get("id") == data.request_id), None)
                if prev:
                    return {"message": "Consumo já registrado", "transaction": prev, "already_recorded": True}
            raise HTTPException(status_code=409, detail="Limite insuficiente ou conta alterada. Atualize e tente novamente")
        return {"message": "Consumo lançado a prazo (fora da gaveta)", "transaction": tx,
                "available": money(limit_cents - account["charged_cents"] - total_cents)}

    @api_router.post("/employee-credit/employees/{employee_id}/settlements")
    async def settle_employee(employee_id: str, data: EmployeeSettlement, current_user: dict = Depends(admin_only)):
        await _employee(employee_id)
        month = validate_month(data.month)
        amount_cents = cents(data.amount)
        if amount_cents <= 0:
            raise HTTPException(status_code=422, detail="Acerto deve ser maior que zero")
        if len(data.note.strip()) < 4:
            raise HTTPException(status_code=422, detail="Informe comprovante ou observação do acerto")
        tx = {"id": data.request_id, "type": "settlement", "at": local_iso(),
              "amount": money(amount_cents), "note": data.note.strip(),
              "created_by": current_user.get("name", "Administrador"),
              "method": "external_manual_settlement"}
        result = await db.employee_credit_accounts.update_one(
            {"employee_id": employee_id, "month": month,
             "transactions.id": {"$ne": data.request_id},
             "$expr": {"$gte": [{"$subtract": ["$charged_cents", "$paid_cents"]}, amount_cents]}},
            {"$inc": {"paid_cents": amount_cents}, "$push": {"transactions": tx}}
        )
        if result.modified_count != 1:
            current = await db.employee_credit_accounts.find_one({"employee_id": employee_id, "month": month}, {"_id": 0})
            if current and any(x.get("id") == data.request_id for x in current.get("transactions", [])):
                return {"message": "Acerto já registrado", "already_recorded": True}
            raise HTTPException(status_code=409, detail="Saldo insuficiente ou mês sem lançamentos")
        return {"message": "Acerto manual registrado. Nenhum desconto salarial foi efetuado."}

    @api_router.post("/employee-credit/employees/{employee_id}/void-purchase")
    async def void_employee_purchase(employee_id: str, data: EmployeeVoid, current_user: dict = Depends(admin_only)):
        await _employee(employee_id)
        account_list = await db.employee_credit_accounts.find({"employee_id": employee_id, "transactions.id": data.purchase_id}, {"_id": 0}).to_list(length=2)
        if not account_list:
            raise HTTPException(status_code=404, detail="Consumo não encontrado")
        account = account_list[0]
        original = next((t for t in account.get("transactions", []) if t.get("id") == data.purchase_id and t.get("type") == "purchase"), None)
        if not original:
            raise HTTPException(status_code=422, detail="Lançamento não é um consumo")
        existing_void = next((t for t in account.get("transactions", []) if t.get("type") == "void" and t.get("purchase_id") == data.purchase_id), None)
        if existing_void:
            return {"message": "Consumo já estornado", "already_recorded": True}
        amount_cents = cents(original["amount"])
        tx = {"id": data.request_id, "type": "void", "purchase_id": data.purchase_id,
              "amount": money(amount_cents), "note": data.note.strip(), "at": local_iso(),
              "created_by": current_user.get("name", "Administrador")}
        result = await db.employee_credit_accounts.update_one(
            {"employee_id": employee_id, "month": account["month"],
             "transactions.id": {"$ne": data.request_id},
             "voided_purchase_ids": {"$ne": data.purchase_id},
             "$expr": {"$gte": [{"$subtract": ["$charged_cents", "$paid_cents"]}, amount_cents]}},
            {"$inc": {"charged_cents": -amount_cents},
             "$push": {"transactions": tx, "voided_purchase_ids": data.purchase_id}}
        )
        if result.modified_count != 1:
            raise HTTPException(status_code=409, detail="Consumo já estornado ou houve acerto. Confira o extrato")
        return {"message": "Consumo estornado no crédito, com histórico preservado."}
