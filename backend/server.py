"""
Gestor Restô - Sistema de Gestão para Restaurante
Backend FastAPI com Socket.IO para comunicação em tempo real
"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import socketio
import os
import logging
import json
import hashlib
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
# Falha imediatamente quando falta uma chave forte; nunca usa segredo fixo no codigo.
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY deve ter pelo menos 32 caracteres e vir do Environment do Render")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# MongoDB connection — Atlas (TLS) com validação real
mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

# Configuração para Atlas (mongodb+srv) e local
_mongo_kwargs = {
    "serverSelectionTimeoutMS": 10000,
    "connectTimeoutMS": 10000,
    "socketTimeoutMS": 20000,
}
if mongo_url.startswith("mongodb+srv://") or "mongodb.net" in mongo_url:
    _mongo_kwargs["tls"] = True
    _mongo_kwargs["tlsAllowInvalidCertificates"] = False

client = AsyncIOMotorClient(mongo_url, **_mongo_kwargs)
db = client[db_name]

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

# ==================== STARTUP: validação real do MongoDB ====================
@app.on_event("startup")
async def startup_validate_db():
    """Valida conexão com MongoDB no startup. Se falhar, para o servidor."""
    try:
        result = await client.admin.command("ping")
        if result.get("ok") != 1.0:
            raise Exception("MongoDB ping retornou status != ok")
        logger.info("MongoDB conectado com sucesso")
        # Cadastro automático das comandas físicas 200 a 230
        # Preserva comandas existentes e seus vínculos com pedidos.
        created_tabs = 0

        for tab_number in range(200, 231):
            result = await db.physical_tabs.update_one(
                {"number": tab_number},
                {
                    "$setOnInsert": {
                        "number": tab_number,
                        "active_order_id": None,
                        "table_id": None
                    }
                },
                upsert=True
            )

            if result.upserted_id is not None:
                created_tabs += 1

        logger.info(
            f"Comandas físicas 200 a 230 verificadas. "
            f"Novos cadastros: {created_tabs}"
        )

        # Cria UMA conta administrativa inicial apenas quando explicitamente
        # configurada em variaveis de ambiente. Nunca embute senha no codigo.
        # Depois do primeiro deploy, remova BOOTSTRAP_ADMIN_PASSWORD do Render.
        bootstrap_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        bootstrap_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
        if bool(bootstrap_email) != bool(bootstrap_password):
            raise RuntimeError("Defina BOOTSTRAP_ADMIN_EMAIL e BOOTSTRAP_ADMIN_PASSWORD juntos")
        if bootstrap_email:
            if len(bootstrap_password) < 12 or len(bootstrap_password.encode("utf-8")) > 72:
                raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD deve ter 12 a 72 bytes")
            existing_admin = await db.users.find_one({"email": bootstrap_email})
            if not existing_admin:
                account = {
                    "id": str(uuid.uuid4()),
                    "name": "Administrador Homologacao",
                    "email": bootstrap_email,
                    "role": "superadmin",
                    "password": pwd_context.hash(bootstrap_password),
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.users.insert_one(account)
                logger.info("Conta administrativa inicial criada")
            else:
                logger.info("Conta administrativa inicial ja existe; senha e perfil preservados")

    except Exception as e:
        logger.critical(f"FALHA na conexão com MongoDB: {e}")
        logger.critical("O servidor NÃO pode operar sem banco de dados. Verifique MONGO_URL no .env")
        raise SystemExit(1)

# ==================== HEALTH / PING ====================
@app.get("/health")
async def health_check():
    """Health check — verifica se MongoDB está respondendo."""
    try:
        result = await client.admin.command("ping")
        mongo_ok = result.get("ok") == 1.0
    except Exception:
        mongo_ok = False
    if not mongo_ok:
        raise HTTPException(status_code=503, detail="MongoDB indisponível")
    return {"status": "healthy", "database": "connected"}

@api_router.get("/health")
async def health_check_api():
    """Health check leve via /api/health (liveness probe).

    Retorna sempre 200 se o processo estiver vivo, sem depender do MongoDB.
    Isso evita falsos negativos por hiccups momentâneos do banco em probes
    de infra/uptime. Para readiness (com DB), usar GET /health (root).
    """
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@api_router.get("/ping")
async def ping():
    return {"message": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================== ENUMS ====================
class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
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
    CARD = "card"  # Histórico de pagamentos antigos
    CREDIT = "credit"
