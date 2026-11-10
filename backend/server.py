    produced_name = produced_stock.get("name") or ""
    if not produced_name and produced_stock.get("product_id"):
        produced_product = await db.products.find_one({"id": produced_stock.get("product_id")}, {"_id": 0})
        produced_name = produced_product["name"] if produced_product else produced_stock.get("product_id", "")
    if not produced_name:
        produced_name = produced_id

    production = {
        "id": str(uuid.uuid4()),
        "produced_stock_item_id": produced_id,
        "produced_product_id": produced_stock.get("product_id"),
        "produced_product_name": produced_name,
        "quantity": quantity,
        "ingredients_consumed": detail,
        "total_cost": round(total_cost, 2),
        "unit_cost": new_unit_cost,
        "weighted_unit_cost": weighted,
        "notes": notes,
        "user_id": current_user.get("id"),
        "user_name": current_user.get("name", ""),
        "created_at": now_iso,
    }
    await db.productions.insert_one(production)
    production.pop("_id", None)

    # Emite atualizacao de estoque em tempo real
    stock_list = await db.stock.find({}, {"_id": 0}).to_list(500)
    await sio.emit('stock_updated', stock_list)

    logger.info(f"[PRODUCTION] {current_user.get('name','-')} produziu {quantity}x {produced_name} (custo R$ {total_cost:.2f})")
    return production

@api_router.get("/productions")
async def list_productions(current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    productions = await db.productions.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return productions

@api_router.get("/productions/dashboard")
async def production_dashboard(current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    """Resumo: produzido x vendido x estoque restante x custo total."""
    productions = await db.productions.find({}, {"_id": 0}).to_list(2000)
    # Agrega producao por stock_item_id
    produced_map = {}  # stock_item_id -> {qty, cost, name}
    for p in productions:
        sid = p.get("produced_stock_item_id")
        if not sid:
            continue
        agg = produced_map.setdefault(sid, {"qty": 0, "cost": 0, "name": p.get("produced_product_name", "")})
        agg["qty"] += float(p.get("quantity", 0) or 0)
        agg["cost"] += float(p.get("total_cost", 0) or 0)

    # Estoque atual + consumo via pedidos delivered (apenas items que tem receita usando esses stock_items)
    stock_items = await db.stock.find({}, {"_id": 0}).to_list(1000)
    stock_by_id = {s["id"]: s for s in stock_items}

    # Consumo: percorre pedidos entregues (delivered) e somatoria receitas
    recipes = await db.recipes.find({}, {"_id": 0}).to_list(1000)
    recipe_by_product = {r["product_id"]: r for r in recipes}
    consumption = {}  # stock_item_id -> qty consumida
    orders = await db.orders.find({"items.status": "delivered"}, {"_id": 0}).to_list(5000)
    for o in orders:
        for it in o.get("items", []):
            if it.get("status") != "delivered":
                continue
            recipe = recipe_by_product.get(it.get("product_id"))
            if not recipe:
                continue
            sold_qty = float(it.get("quantity", 0) or 0)
            for ing in recipe.get("ingredients", []):
                sid = ing.get("stock_item_id")
                qty = float(ing.get("quantity", 0) or 0) * sold_qty
                if sid:
                    consumption[sid] = consumption.get(sid, 0) + qty

    rows = []
    total_produced_cost = 0
    for sid, agg in produced_map.items():
        s = stock_by_id.get(sid, {})
        consumed = consumption.get(sid, 0)
        current = float(s.get("quantity", 0) or 0)
        total_produced_cost += agg["cost"]
        rows.append({
            "stock_item_id": sid,
            "name": agg["name"] or s.get("product_id", sid),
            "produced": round(agg["qty"], 2),
            "consumed": round(consumed, 2),
            "current_stock": round(current, 2),
            "total_cost": round(agg["cost"], 2),
            "unit_cost": float(s.get("unit_cost", 0) or 0),
        })

    return {
        "rows": rows,
        "total_productions": len(productions),
        "total_produced_cost": round(total_produced_cost, 2),
    }

# ==================== PRODUCTION RECIPES CRUD ====================
@api_router.get("/production-recipes")
async def list_production_recipes(current_user: dict = Depends(get_current_user)):
    recipes = await db.production_recipes.find({}, {"_id": 0}).to_list(500)
    return recipes

@api_router.get("/production-recipes/by-stock/{stock_id}")
async def get_production_recipe_by_stock(stock_id: str, current_user: dict = Depends(get_current_user)):
    recipe = await db.production_recipes.find_one({"produced_stock_item_id": stock_id}, {"_id": 0})
    if not recipe:
        raise HTTPException(status_code=404, detail="Receita de produção não encontrada")
    return recipe

@api_router.get("/production-recipes/{recipe_id}")
async def get_production_recipe(recipe_id: str, current_user: dict = Depends(get_current_user)):
    recipe = await db.production_recipes.find_one({"id": recipe_id}, {"_id": 0})
    if not recipe:
        raise HTTPException(status_code=404, detail="Receita não encontrada")
    return recipe

@api_router.post("/production-recipes")
async def create_production_recipe(data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    produced_id = data.get("produced_stock_item_id")
    if not produced_id:
        raise HTTPException(status_code=400, detail="produced_stock_item_id é obrigatório")
    if not data.get("ingredients"):
        raise HTTPException(status_code=400, detail="Adicione ao menos um ingrediente")
    existing = await db.production_recipes.find_one({"produced_stock_item_id": produced_id})
    if existing:
        raise HTTPException(status_code=400, detail="Já existe receita de produção para este item. Use PUT.")
    produced_stock = await db.stock.find_one({"id": produced_id}, {"_id": 0})
    produced_name = (produced_stock or {}).get("name", "")
    if not produced_name and produced_stock and produced_stock.get("product_id"):
        prod = await db.products.find_one({"id": produced_stock["product_id"]}, {"_id": 0})
        produced_name = prod["name"] if prod else ""
    now_iso = datetime.now(timezone.utc).isoformat()
    recipe = {
        "id": str(uuid.uuid4()),
        "produced_stock_item_id": produced_id,
        "produced_name": produced_name or produced_id,
        "yield_quantity": float(data.get("yield_quantity", 1) or 1),
        "ingredients": data.get("ingredients", []),
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.production_recipes.insert_one(recipe)
    recipe.pop("_id", None)
    return recipe

@api_router.put("/production-recipes/{recipe_id}")
async def update_production_recipe(recipe_id: str, data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    update = {
        "yield_quantity": float(data.get("yield_quantity", 1) or 1),
        "ingredients": data.get("ingredients", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.production_recipes.update_one({"id": recipe_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Receita não encontrada")
    return await db.production_recipes.find_one({"id": recipe_id}, {"_id": 0})

@api_router.delete("/production-recipes/{recipe_id}")
async def delete_production_recipe(recipe_id: str, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
