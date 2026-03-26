"""
Gestor Restô - Sistema de Gestão para Restaurante
Backend FastAPI com Socket.IO para comunicação em tempo real
"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import socketio
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# JWT Configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'digital-codex-secret-key-2024')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Socket.IO setup
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

# Create FastAPI app
app = FastAPI(title="Gestor Restô - Sistema de Gestão para Restaurante")
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== ENUMS ====================
class UserRole(str, Enum):
    ADMIN = "admin"
    WAITER = "waiter"
    CASHIER = "cashier"
    KITCHEN = "kitchen"
    BAR = "bar"

class TableStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    CLEANING = "cleaning"

class OrderStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class OrderItemType(str, Enum):
    FOOD = "food"
    DRINK = "drink"

class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    PIX = "pix"
    VOUCHER = "voucher"

class StockUnit(str, Enum):
    UNIT = "unit"
    KG = "kg"
    LITER = "liter"
    GRAM = "gram"

# ==================== MODELS ====================
class UserBase(BaseModel):
    name: str
    email: str
    role: UserRole

class UserCreate(UserBase):
    password: str

class User(UserBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class CategoryBase(BaseModel):
    name: str
    type: OrderItemType
    description: Optional[str] = None
    icon: Optional[str] = None

class Category(CategoryBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    category_id: str
    price: float
    cost: float = 0
    image_url: Optional[str] = None
    type: OrderItemType
    is_available: bool = True
    preparation_time: int = 10  # minutes

class Product(ProductBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StockItemBase(BaseModel):
    product_id: str
    quantity: float
    unit: StockUnit
    min_quantity: float = 5
    max_quantity: float = 100

class StockItem(StockItemBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TableBase(BaseModel):
    number: int
    capacity: int
    status: TableStatus = TableStatus.AVAILABLE

class Table(TableBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_order_id: Optional[str] = None

class OrderItemBase(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    notes: Optional[str] = None
    type: OrderItemType
    status: OrderStatus = OrderStatus.PENDING

class OrderItem(OrderItemBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderBase(BaseModel):
    table_id: str
    table_number: int
    waiter_id: Optional[str] = None
    waiter_name: Optional[str] = None

class OrderCreate(BaseModel):
    table_id: str
    table_number: int
    items: List[OrderItemBase]
    waiter_id: Optional[str] = None
    waiter_name: Optional[str] = None

class Order(OrderBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    items: List[OrderItem] = []
    status: OrderStatus = OrderStatus.PENDING
    subtotal: float = 0
    service_fee: float = 0
    total: float = 0
    service_fee_percentage: float = 10
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    is_closed: bool = False

class PaymentBase(BaseModel):
    order_id: str
    amount: float
    method: PaymentMethod

class Payment(PaymentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CashRegisterBase(BaseModel):
    opened_by: str
    initial_amount: float

class CashRegister(CashRegisterBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None
    final_amount: float = 0
    total_sales: float = 0
    withdrawals: float = 0
    deposits: float = 0
    is_open: bool = True

class CashMovement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    register_id: str
    type: str  # withdrawal, deposit
    amount: float
    reason: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InvoiceBase(BaseModel):
    order_id: str
    customer_name: Optional[str] = None
    customer_cpf: Optional[str] = None

class Invoice(InvoiceBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: str = Field(default_factory=lambda: f"NF-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    status: str = "mock"  # mock, pending, issued, cancelled
    total: float = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ==================== AUTH FUNCTIONS ====================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_role(allowed_roles: List[UserRole]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in [r.value for r in allowed_roles]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# ==================== AUTH ROUTES ====================
@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    user = User(**user_data.model_dump(exclude={"password"}))
    user_dict = user.model_dump()
    user_dict["password"] = hashed_password
    user_dict["created_at"] = user_dict["created_at"].isoformat()
    
    await db.users.insert_one(user_dict)
    access_token = create_access_token(data={"sub": user.id})
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user={"id": user.id, "name": user.name, "email": user.email, "role": user.role}
    )

@api_router.post("/auth/login", response_model=Token)
async def login(login_data: UserLogin):
    user = await db.users.find_one({"email": login_data.email}, {"_id": 0})
    if not user or not verify_password(login_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": user["id"]})
    return Token(
        access_token=access_token,
        token_type="bearer",
        user={"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}
    )

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {k: v for k, v in current_user.items() if k != "password"}

# ==================== USER ROUTES ====================
@api_router.get("/users", response_model=List[dict])
async def get_users(current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    users = await db.users.find({}, {"_id": 0, "password": 0}).to_list(100)
    return users

@api_router.post("/users", response_model=dict)
async def create_user(user_data: UserCreate, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    user = User(**user_data.model_dump(exclude={"password"}))
    user_dict = user.model_dump()
    user_dict["password"] = hashed_password
    user_dict["created_at"] = user_dict["created_at"].isoformat()
    
    await db.users.insert_one(user_dict)
    return {k: v for k, v in user_dict.items() if k not in ["password", "_id"]}

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, user_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    if "password" in user_data:
        user_data["password"] = get_password_hash(user_data["password"])
    await db.users.update_one({"id": user_id}, {"$set": user_data})
    return {"message": "User updated"}

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    await db.users.delete_one({"id": user_id})
    return {"message": "User deleted"}

# ==================== CATEGORY ROUTES ====================
@api_router.get("/categories", response_model=List[dict])
async def get_categories():
    categories = await db.categories.find({}, {"_id": 0}).to_list(100)
    return categories

@api_router.post("/categories", response_model=dict)
async def create_category(category_data: CategoryBase, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    category = Category(**category_data.model_dump())
    cat_dict = category.model_dump()
    cat_dict["created_at"] = cat_dict["created_at"].isoformat()
    await db.categories.insert_one(cat_dict)
    return {k: v for k, v in cat_dict.items() if k != "_id"}

@api_router.put("/categories/{category_id}")
async def update_category(category_id: str, category_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    await db.categories.update_one({"id": category_id}, {"$set": category_data})
    return {"message": "Category updated"}

@api_router.delete("/categories/{category_id}")
async def delete_category(category_id: str, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    await db.categories.delete_one({"id": category_id})
    return {"message": "Category deleted"}

# ==================== PRODUCT ROUTES ====================
@api_router.get("/products", response_model=List[dict])
async def get_products():
    products = await db.products.find({}, {"_id": 0}).to_list(500)
    return products

@api_router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@api_router.post("/products", response_model=dict)
async def create_product(product_data: ProductBase, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    product = Product(**product_data.model_dump())
    prod_dict = product.model_dump()
    prod_dict["created_at"] = prod_dict["created_at"].isoformat()
    await db.products.insert_one(prod_dict)
    return {k: v for k, v in prod_dict.items() if k != "_id"}

@api_router.put("/products/{product_id}")
async def update_product(product_id: str, product_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    await db.products.update_one({"id": product_id}, {"$set": product_data})
    return {"message": "Product updated"}

@api_router.delete("/products/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    await db.products.delete_one({"id": product_id})
    return {"message": "Product deleted"}

# ==================== TABLE ROUTES ====================
@api_router.get("/tables", response_model=List[dict])
async def get_tables():
    tables = await db.tables.find({}, {"_id": 0}).to_list(100)
    return tables

@api_router.post("/tables", response_model=dict)
async def create_table(table_data: TableBase, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    existing = await db.tables.find_one({"number": table_data.number})
    if existing:
        raise HTTPException(status_code=400, detail="Table number already exists")
    table = Table(**table_data.model_dump())
    await db.tables.insert_one(table.model_dump())
    return table.model_dump()

@api_router.put("/tables/{table_id}")
async def update_table(table_id: str, table_data: dict):
    # Validação: não pode mudar mesa ocupada para outro status se tiver pedido aberto
    if table_data.get("status") in ["available", "reserved", "cleaning"]:
        existing_order = await db.orders.find_one({"table_id": table_id, "is_closed": False})
        if existing_order and table_data.get("status") != "cleaning":
            raise HTTPException(status_code=400, detail="Mesa possui comanda aberta")
    
    await db.tables.update_one({"id": table_id}, {"$set": table_data})
    tables = await get_tables()
    await sio.emit('tables_updated', tables)
    return {"message": "Table updated"}

@api_router.put("/tables/{table_id}/status")
async def update_table_status(table_id: str, status_data: dict):
    """Endpoint específico para atualizar status da mesa"""
    new_status = status_data.get("status")
    if new_status not in ["available", "occupied", "reserved", "cleaning"]:
        raise HTTPException(status_code=400, detail="Status inválido")
    
    await db.tables.update_one({"id": table_id}, {"$set": {"status": new_status}})
    tables = await get_tables()
    await sio.emit('tables_updated', tables)
    return {"message": f"Status atualizado para {new_status}"}

@api_router.post("/tables/{table_id}/request-cleaning")
async def request_table_cleaning(table_id: str):
    """Solicita limpeza da mesa"""
    await db.tables.update_one({"id": table_id}, {"$set": {"status": "cleaning"}})
    tables = await get_tables()
    await sio.emit('tables_updated', tables)
    return {"message": "Limpeza solicitada"}

@api_router.delete("/tables/{table_id}")
async def delete_table(table_id: str, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    await db.tables.delete_one({"id": table_id})
    return {"message": "Table deleted"}

# ==================== ORDER ROUTES ====================
@api_router.get("/orders", response_model=List[dict])
async def get_orders(status: Optional[str] = None, is_closed: Optional[bool] = None):
    query = {}
    if status:
        query["status"] = status
    if is_closed is not None:
        query["is_closed"] = is_closed
    orders = await db.orders.find(query, {"_id": 0}).to_list(500)
    return orders

@api_router.get("/orders/open")
async def get_open_orders():
    orders = await db.orders.find({"is_closed": False}, {"_id": 0}).to_list(100)
    return orders

@api_router.get("/orders/table/{table_id}")
async def get_table_order(table_id: str):
    order = await db.orders.find_one({"table_id": table_id, "is_closed": False}, {"_id": 0})
    return order

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@api_router.post("/orders", response_model=dict)
async def create_order(order_data: OrderCreate):
    # Check if table already has an open order
    existing_order = await db.orders.find_one({"table_id": order_data.table_id, "is_closed": False})
    
    if existing_order:
        # Add items to existing order
        items = [OrderItem(**item.model_dump()).model_dump() for item in order_data.items]
        for item in items:
            item["created_at"] = item["created_at"].isoformat()
        
        existing_order["items"].extend(items)
        subtotal = sum(item["unit_price"] * item["quantity"] for item in existing_order["items"])
        service_fee = subtotal * (existing_order.get("service_fee_percentage", 10) / 100)
        
        await db.orders.update_one(
            {"id": existing_order["id"]},
            {"$set": {
                "items": existing_order["items"],
                "subtotal": subtotal,
                "service_fee": service_fee,
                "total": subtotal + service_fee
            }}
        )
        updated_order = await db.orders.find_one({"id": existing_order["id"]}, {"_id": 0})
        
        # Emit events for kitchen and bar
        await emit_order_updates(items)
        return updated_order
    
    # Create new order
    order = Order(
        table_id=order_data.table_id,
        table_number=order_data.table_number,
        waiter_id=order_data.waiter_id,
        waiter_name=order_data.waiter_name,
        items=[OrderItem(**item.model_dump()) for item in order_data.items]
    )
    
    order_dict = order.model_dump()
    order_dict["created_at"] = order_dict["created_at"].isoformat()
    for item in order_dict["items"]:
        item["created_at"] = item["created_at"].isoformat()
    
    subtotal = sum(item["unit_price"] * item["quantity"] for item in order_dict["items"])
    order_dict["subtotal"] = subtotal
    order_dict["service_fee"] = subtotal * (order_dict["service_fee_percentage"] / 100)
    order_dict["total"] = order_dict["subtotal"] + order_dict["service_fee"]
    
    await db.orders.insert_one(order_dict)
    await db.tables.update_one(
        {"id": order_data.table_id},
        {"$set": {"status": TableStatus.OCCUPIED.value, "current_order_id": order.id}}
    )
    
    # Emit events
    await emit_order_updates(order_dict["items"])
    await sio.emit('tables_updated', await get_tables())
    
    return {k: v for k, v in order_dict.items() if k != "_id"}

async def emit_order_updates(items):
    food_items = [i for i in items if i["type"] == OrderItemType.FOOD.value]
    drink_items = [i for i in items if i["type"] == OrderItemType.DRINK.value]
    
    if food_items:
        kitchen_orders = await db.orders.find({"is_closed": False}, {"_id": 0}).to_list(100)
        await sio.emit('kitchen_update', kitchen_orders)
    
    if drink_items:
        bar_orders = await db.orders.find({"is_closed": False}, {"_id": 0}).to_list(100)
        await sio.emit('bar_update', bar_orders)

@api_router.put("/orders/{order_id}/item/{item_id}/status")
async def update_item_status(order_id: str, item_id: str, status_data: dict):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    target_item = None
    previous_status = None
    for item in order["items"]:
        if item["id"] == item_id:
            previous_status = item["status"]
            item["status"] = status_data["status"]
            target_item = item
            break
    
    if not target_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    new_status = status_data["status"]
    
    # Baixa automática de estoque: só quando muda para "delivered" pela primeira vez
    if new_status == "delivered" and previous_status != "delivered":
        await deduct_stock(target_item["product_id"], target_item["quantity"])
    
    await db.orders.update_one({"id": order_id}, {"$set": {"items": order["items"]}})
    
    # Emit updates
    updated_order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    await sio.emit('kitchen_update', await db.orders.find({"is_closed": False}, {"_id": 0}).to_list(100))
    await sio.emit('bar_update', await db.orders.find({"is_closed": False}, {"_id": 0}).to_list(100))
    await sio.emit('order_updated', updated_order)
    
    # Emitir atualização de estoque em tempo real
    if new_status == "delivered" and previous_status != "delivered":
        stock_list = await db.stock.find({}, {"_id": 0}).to_list(500)
        await sio.emit('stock_updated', stock_list)
    
    return {"message": "Item status updated"}

@api_router.post("/orders/{order_id}/close")
async def close_order(order_id: str, payment_data: dict):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Register payments
    for payment in payment_data.get("payments", []):
        payment_obj = Payment(order_id=order_id, amount=payment["amount"], method=payment["method"])
        pay_dict = payment_obj.model_dump()
        pay_dict["created_at"] = pay_dict["created_at"].isoformat()
        await db.payments.insert_one(pay_dict)
    
    # Close order
    closed_at = datetime.now(timezone.utc).isoformat()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"is_closed": True, "closed_at": closed_at, "status": OrderStatus.DELIVERED.value}}
    )
    
    # Update table
    await db.tables.update_one(
        {"id": order["table_id"]},
        {"$set": {"status": TableStatus.AVAILABLE.value, "current_order_id": None}}
    )
    
    # Update cash register
    register = await db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if register:
        await db.cash_registers.update_one(
            {"id": register["id"]},
            {"$inc": {"total_sales": order["total"]}}
        )
    
    # Emit updates
    await sio.emit('tables_updated', await get_tables())
    await sio.emit('order_closed', {"order_id": order_id})
    
    return {"message": "Order closed successfully"}

# ==================== STOCK ROUTES ====================

async def deduct_stock(product_id: str, quantity: int):
    """Baixa automática de estoque. Chamada quando item é marcado como delivered."""
    stock_item = await db.stock.find_one({"product_id": product_id}, {"_id": 0})
    if not stock_item:
        return  # Produto sem controle de estoque — ignora
    if stock_item["quantity"] < quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Estoque insuficiente para '{product_id}'. Disponível: {stock_item['quantity']}, Solicitado: {quantity}"
        )
    await db.stock.update_one(
        {"product_id": product_id},
        {
            "$inc": {"quantity": -quantity},
            "$set": {"last_updated": datetime.now(timezone.utc).isoformat()}
        }
    )

@api_router.get("/stock", response_model=List[dict])
async def get_stock():
    stock = await db.stock.find({}, {"_id": 0}).to_list(500)
    return stock

@api_router.post("/stock", response_model=dict)
async def create_stock_item(stock_data: StockItemBase, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    stock_item = StockItem(**stock_data.model_dump())
    stock_dict = stock_item.model_dump()
    stock_dict["last_updated"] = stock_dict["last_updated"].isoformat()
    await db.stock.insert_one(stock_dict)
    return {k: v for k, v in stock_dict.items() if k != "_id"}

@api_router.put("/stock/{stock_id}")
async def update_stock(stock_id: str, stock_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    stock_data["last_updated"] = datetime.now(timezone.utc).isoformat()
    await db.stock.update_one({"id": stock_id}, {"$set": stock_data})
    return {"message": "Stock updated"}

@api_router.get("/stock/alerts")
async def get_stock_alerts():
    pipeline = [
        {"$match": {"$expr": {"$lte": ["$quantity", "$min_quantity"]}}},
        {"$project": {"_id": 0}}
    ]
    alerts = await db.stock.aggregate(pipeline).to_list(100)
    return alerts

# ==================== CASH REGISTER ROUTES ====================
@api_router.get("/cash-register/current")
async def get_current_register():
    register = await db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    return register

@api_router.post("/cash-register/open")
async def open_register(register_data: CashRegisterBase, current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.CASHIER]))):
    existing = await db.cash_registers.find_one({"is_open": True})
    if existing:
        raise HTTPException(status_code=400, detail="A register is already open")
    
    register = CashRegister(**register_data.model_dump())
    reg_dict = register.model_dump()
    reg_dict["opened_at"] = reg_dict["opened_at"].isoformat()
    await db.cash_registers.insert_one(reg_dict)
    return {k: v for k, v in reg_dict.items() if k != "_id"}

@api_router.post("/cash-register/close")
async def close_register(close_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.CASHIER]))):
    register = await db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if not register:
        raise HTTPException(status_code=400, detail="No open register")
    
    final_amount = register["initial_amount"] + register["total_sales"] + register["deposits"] - register["withdrawals"]
    
    await db.cash_registers.update_one(
        {"id": register["id"]},
        {"$set": {
            "is_open": False,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "closed_by": close_data.get("closed_by"),
            "final_amount": final_amount
        }}
    )
    return {"message": "Register closed", "final_amount": final_amount}

@api_router.post("/cash-register/withdrawal")
async def register_withdrawal(movement_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.CASHIER]))):
    register = await db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if not register:
        raise HTTPException(status_code=400, detail="No open register")
    
    movement = CashMovement(
        register_id=register["id"],
        type="withdrawal",
        amount=movement_data["amount"],
        reason=movement_data["reason"],
        created_by=current_user["id"]
    )
    mov_dict = movement.model_dump()
    mov_dict["created_at"] = mov_dict["created_at"].isoformat()
    
    await db.cash_movements.insert_one(mov_dict)
    await db.cash_registers.update_one(
        {"id": register["id"]},
        {"$inc": {"withdrawals": movement_data["amount"]}}
    )
    return {"message": "Withdrawal registered"}

@api_router.post("/cash-register/deposit")
async def register_deposit(movement_data: dict, current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.CASHIER]))):
    register = await db.cash_registers.find_one({"is_open": True}, {"_id": 0})
    if not register:
        raise HTTPException(status_code=400, detail="No open register")
    
    movement = CashMovement(
        register_id=register["id"],
        type="deposit",
        amount=movement_data["amount"],
        reason=movement_data["reason"],
        created_by=current_user["id"]
    )
    mov_dict = movement.model_dump()
    mov_dict["created_at"] = mov_dict["created_at"].isoformat()
    
    await db.cash_movements.insert_one(mov_dict)
    await db.cash_registers.update_one(
        {"id": register["id"]},
        {"$inc": {"deposits": movement_data["amount"]}}
    )
    return {"message": "Deposit registered"}

# ==================== INVOICE ROUTES (MOCK) ====================
@api_router.get("/invoices", response_model=List[dict])
async def get_invoices():
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(500)
    return invoices

@api_router.post("/invoices")
async def create_invoice(invoice_data: InvoiceBase):
    order = await db.orders.find_one({"id": invoice_data.order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    invoice = Invoice(**invoice_data.model_dump(), total=order["total"])
    inv_dict = invoice.model_dump()
    inv_dict["created_at"] = inv_dict["created_at"].isoformat()
    await db.invoices.insert_one(inv_dict)
    return {k: v for k, v in inv_dict.items() if k != "_id"}

# ==================== REPORTS ROUTES ====================
@api_router.get("/reports/sales")
async def get_sales_report(period: str = "daily", current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    today = datetime.now(timezone.utc)
    
    if period == "daily":
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start_date = today - timedelta(days=7)
    elif period == "monthly":
        start_date = today - timedelta(days=30)
    else:
        start_date = today - timedelta(days=1)
    
    pipeline = [
        {"$match": {"is_closed": True, "closed_at": {"$gte": start_date.isoformat()}}},
        {"$group": {
            "_id": None,
            "total_sales": {"$sum": "$total"},
            "total_orders": {"$sum": 1},
            "avg_ticket": {"$avg": "$total"}
        }}
    ]
    
    result = await db.orders.aggregate(pipeline).to_list(1)
    
    # Get top products
    product_pipeline = [
        {"$match": {"is_closed": True, "closed_at": {"$gte": start_date.isoformat()}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_name",
            "quantity": {"$sum": "$items.quantity"},
            "revenue": {"$sum": {"$multiply": ["$items.unit_price", "$items.quantity"]}}
        }},
        {"$sort": {"quantity": -1}},
        {"$limit": 10}
    ]
    top_products = await db.orders.aggregate(product_pipeline).to_list(10)
    
    return {
        "period": period,
        "summary": result[0] if result else {"total_sales": 0, "total_orders": 0, "avg_ticket": 0},
        "top_products": top_products
    }

@api_router.get("/reports/profit")
async def get_profit_report(period: str = "daily", current_user: dict = Depends(require_role([UserRole.ADMIN]))):
    today = datetime.now(timezone.utc)
    
    if period == "daily":
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start_date = today - timedelta(days=7)
    else:
        start_date = today - timedelta(days=30)
    
    # Get sales
    sales_pipeline = [
        {"$match": {"is_closed": True, "closed_at": {"$gte": start_date.isoformat()}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}}}
    ]
    sales = await db.orders.aggregate(sales_pipeline).to_list(1)
    total_sales = sales[0]["total"] if sales else 0
    
    # Estimate costs (simplified - in real app would track actual costs)
    estimated_cost = total_sales * 0.35  # Assuming 35% cost
    profit = total_sales - estimated_cost
    margin = (profit / total_sales * 100) if total_sales > 0 else 0
    
    return {
        "period": period,
        "total_sales": total_sales,
        "estimated_cost": estimated_cost,
        "profit": profit,
        "margin_percentage": margin
    }

# ==================== SOCKET.IO EVENTS ====================
@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    await sio.emit('connection_established', {'sid': sid}, room=sid)

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")

@sio.event
async def join_room(sid, data):
    room = data.get('room')
    if room:
        sio.enter_room(sid, room)
        logger.info(f"Client {sid} joined room {room}")

@sio.event
async def leave_room(sid, data):
    room = data.get('room')
    if room:
        sio.leave_room(sid, room)
        logger.info(f"Client {sid} left room {room}")

@sio.event
async def item_ready(sid, data):
    """Notifica garçom que item está pronto"""
    table_number = data.get('tableNumber')
    product_name = data.get('productName')
    item_type = data.get('type', 'food')
    
    # Emite para todos os garçons conectados
    await sio.emit('waiter_notification', {
        'tableNumber': table_number,
        'productName': product_name,
        'type': item_type,
        'message': f'{product_name} pronto para Mesa {table_number}'
    })
    logger.info(f"Item ready notification: {product_name} for table {table_number}")

@sio.event
async def request_cleaning(sid, data):
    """Cliente solicita limpeza da mesa"""
    table_id = data.get('tableId')
    table_number = data.get('tableNumber')
    
    if table_id:
        await db.tables.update_one(
            {"id": table_id},
            {"$set": {"status": "cleaning"}}
        )
        tables = await get_tables()
        await sio.emit('tables_updated', tables)
        logger.info(f"Cleaning requested for table {table_number}")

# ==================== SETUP ====================
@api_router.get("/")
async def root():
    return {"message": "Gestor Restô - API de Gestão para Restaurante"}

@api_router.post("/setup/seed")
async def seed_database():
    """Seed database with initial data"""
    # Check if admin exists
    admin = await db.users.find_one({"email": "admin@digitalcodex.com"})
    if admin:
        return {"message": "Database already seeded"}
    
    # Create admin user
    admin_user = User(name="Administrador", email="admin@digitalcodex.com", role=UserRole.ADMIN)
    admin_dict = admin_user.model_dump()
    admin_dict["password"] = get_password_hash("admin123")
    admin_dict["created_at"] = admin_dict["created_at"].isoformat()
    await db.users.insert_one(admin_dict)
    
    # Create sample users
    users = [
        {"name": "João Garçom", "email": "garcom@digitalcodex.com", "role": "waiter", "password": get_password_hash("garcom123")},
        {"name": "Maria Caixa", "email": "caixa@digitalcodex.com", "role": "cashier", "password": get_password_hash("caixa123")},
        {"name": "Pedro Cozinha", "email": "cozinha@digitalcodex.com", "role": "kitchen", "password": get_password_hash("cozinha123")},
        {"name": "Ana Bar", "email": "bar@digitalcodex.com", "role": "bar", "password": get_password_hash("bar123")},
    ]
    for u in users:
        user = User(name=u["name"], email=u["email"], role=u["role"])
        user_dict = user.model_dump()
        user_dict["password"] = u["password"]
        user_dict["created_at"] = user_dict["created_at"].isoformat()
        await db.users.insert_one(user_dict)
    
    # Create categories
    categories = [
        {"name": "Hambúrgueres", "type": "food", "icon": "🍔"},
        {"name": "Pratos Principais", "type": "food", "icon": "🍽️"},
        {"name": "Petiscos", "type": "food", "icon": "🍟"},
        {"name": "Sobremesas", "type": "food", "icon": "🍰"},
        {"name": "Refrigerantes", "type": "drink", "icon": "🥤"},
        {"name": "Sucos", "type": "drink", "icon": "🧃"},
        {"name": "Cervejas", "type": "drink", "icon": "🍺"},
        {"name": "Vinhos", "type": "drink", "icon": "🍷"},
        {"name": "Coquetéis", "type": "drink", "icon": "🍹"},
    ]
    category_ids = {}
    for c in categories:
        cat = Category(name=c["name"], type=c["type"], icon=c["icon"])
        cat_dict = cat.model_dump()
        cat_dict["created_at"] = cat_dict["created_at"].isoformat()
        await db.categories.insert_one(cat_dict)
        category_ids[c["name"]] = cat.id
    
    # Create products
    products = [
        {"name": "X-Burguer Clássico", "category": "Hambúrgueres", "price": 28.90, "cost": 10, "type": "food", "image_url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=400"},
        {"name": "X-Bacon Especial", "category": "Hambúrgueres", "price": 34.90, "cost": 12, "type": "food", "image_url": "https://images.unsplash.com/photo-1553979459-d2229ba7433b?w=400"},
        {"name": "X-Salada", "category": "Hambúrgueres", "price": 26.90, "cost": 9, "type": "food", "image_url": "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=400"},
        {"name": "Filé à Parmegiana", "category": "Pratos Principais", "price": 52.90, "cost": 20, "type": "food", "image_url": "https://images.unsplash.com/photo-1632778149955-e80f8ceca2e8?w=400"},
        {"name": "Picanha Grelhada", "category": "Pratos Principais", "price": 68.90, "cost": 30, "type": "food", "image_url": "https://images.unsplash.com/photo-1594041680534-e8c8cdebd659?w=400"},
        {"name": "Frango Grelhado", "category": "Pratos Principais", "price": 38.90, "cost": 15, "type": "food", "image_url": "https://images.unsplash.com/photo-1598515214211-89d3c73ae83b?w=400"},
        {"name": "Batata Frita", "category": "Petiscos", "price": 18.90, "cost": 5, "type": "food", "image_url": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=400"},
        {"name": "Onion Rings", "category": "Petiscos", "price": 22.90, "cost": 6, "type": "food", "image_url": "https://images.unsplash.com/photo-1639024471283-03518883512d?w=400"},
        {"name": "Pudim", "category": "Sobremesas", "price": 14.90, "cost": 4, "type": "food", "image_url": "https://images.unsplash.com/photo-1624353365286-3f8d62daad51?w=400"},
        {"name": "Petit Gateau", "category": "Sobremesas", "price": 24.90, "cost": 8, "type": "food", "image_url": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=400"},
        {"name": "Coca-Cola", "category": "Refrigerantes", "price": 7.90, "cost": 2, "type": "drink", "image_url": "https://images.unsplash.com/photo-1554866585-cd94860890b7?w=400"},
        {"name": "Guaraná", "category": "Refrigerantes", "price": 7.90, "cost": 2, "type": "drink", "image_url": "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?w=400"},
        {"name": "Suco de Laranja", "category": "Sucos", "price": 9.90, "cost": 3, "type": "drink", "image_url": "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=400"},
        {"name": "Suco de Maracujá", "category": "Sucos", "price": 9.90, "cost": 3, "type": "drink", "image_url": "https://images.unsplash.com/photo-1546173159-315724a31696?w=400"},
        {"name": "Heineken", "category": "Cervejas", "price": 14.90, "cost": 6, "type": "drink", "image_url": "https://images.unsplash.com/photo-1608270586620-248524c67de9?w=400"},
        {"name": "Brahma", "category": "Cervejas", "price": 9.90, "cost": 4, "type": "drink", "image_url": "https://images.unsplash.com/photo-1535958636474-b021ee887b13?w=400"},
        {"name": "Vinho Tinto", "category": "Vinhos", "price": 89.90, "cost": 35, "type": "drink", "image_url": "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=400"},
        {"name": "Vinho Branco", "category": "Vinhos", "price": 79.90, "cost": 30, "type": "drink", "image_url": "https://images.unsplash.com/photo-1558001373-7b93ee48ffa0?w=400"},
        {"name": "Caipirinha", "category": "Coquetéis", "price": 19.90, "cost": 6, "type": "drink", "image_url": "https://images.unsplash.com/photo-1536935338788-846bb9981813?w=400"},
        {"name": "Mojito", "category": "Coquetéis", "price": 24.90, "cost": 8, "type": "drink", "image_url": "https://images.unsplash.com/photo-1551538827-9c037cb4f32a?w=400"},
    ]
    for p in products:
        prod = Product(
            name=p["name"],
            category_id=category_ids[p["category"]],
            price=p["price"],
            cost=p["cost"],
            type=p["type"],
            image_url=p.get("image_url")
        )
        prod_dict = prod.model_dump()
        prod_dict["created_at"] = prod_dict["created_at"].isoformat()
        await db.products.insert_one(prod_dict)
    
    # Create tables
    for i in range(1, 16):
        table = Table(number=i, capacity=4 if i <= 10 else 6)
        await db.tables.insert_one(table.model_dump())
    
    return {"message": "Database seeded successfully"}

# Include router and middleware
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

# Wrap FastAPI with Socket.IO for combined HTTP + WebSocket ASGI app
# This is the final app object that uvicorn will serve
app = socketio.ASGIApp(sio, other_asgi_app=app)
