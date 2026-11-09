        delivery_fee = config.get("delivery_fee", 5.0) if config else 5.0

    total = subtotal + delivery_fee

    order_dict = {
        "id": str(uuid.uuid4()),
        "order_code": order_code,
        "source": "online",
        "origin": "web",
        "table_id": None,
        "table_number": None,
        "waiter_id": None,
        "waiter_name": None,
        "items": order_items,
        "status": "pending",
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "service_fee": 0,
        "service_fee_percentage": 0,
        "total": total,
        "is_closed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
        "customer_name": order_data.customer_name,
        "customer_phone": order_data.customer_phone,
        "delivery_type": order_data.delivery_type,
        "address": order_data.address,
        "payment_method": order_data.payment_method,
        "payment_status": "pending",
        "change_for": order_data.change_for,
    }

    await db.orders.insert_one(order_dict)

    # Emitir para cozinha/bar via Socket.IO
    await emit_order_updates(order_items)
    await sio.emit('new_online_order', {
        "order_code": order_code,
        "customer_name": order_data.customer_name,
        "delivery_type": order_data.delivery_type,
        "total": total,
        "items_count": len(order_items),
    })

    return {
        "order_code": order_code,
        "order_id": order_dict["id"],
        "total": total,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "status": "pending",
        "payment_status": "pending",
    }

@api_router.get("/public/pedido/{codigo}")
async def get_public_order_status(codigo: str):
    """Consulta status do pedido pelo código."""
    order = await db.orders.find_one({"order_code": codigo}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    items_status = []
    for item in order.get("items", []):
        items_status.append({
            "name": item["product_name"],
            "quantity": item["quantity"],
            "status": item["status"],
        })

    return {
        "order_code": order["order_code"],
        "status": order["status"],
        "payment_status": order.get("payment_status", "pending"),
        "items": items_status,
        "total": order["total"],
        "delivery_type": order.get("delivery_type"),
        "created_at": order.get("created_at"),
    }
# Módulo financeiro: 10% e crédito dos funcionários
from financial_modules import register_finance_routes
register_finance_routes(api_router, db, require_role, UserRole)

# Módulo operacional: tarefas e fotografias
from operational_modules import register_operational_routes
register_operational_routes(
    api_router,
    db,
    require_role,
    UserRole
)
# Fechamento administrativo com ressalvas
from cash_admin_exception import register_admin_cash_routes

register_admin_cash_routes(
    api_router,
    db,
    require_role,
    UserRole,
    preview_cash_register,
    jwt,
    SECRET_KEY,
    ALGORITHM,
    verify_password
)

# Histórico permanente de comandas
from order_history import register_order_history_routes

register_order_history_routes(
    api_router,
    db,
    require_role,
    UserRole
)
# Registrar todas as rotas na aplicação
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shutdown handler (must be registered on FastAPI before wrapping)
@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
