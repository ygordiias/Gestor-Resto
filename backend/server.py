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
