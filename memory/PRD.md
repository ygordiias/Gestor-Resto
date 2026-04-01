# Gestor Restô - Sistema de Gestão para Restaurante

## Stack
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Python + Motor (async MongoDB) + Socket.IO
- **Banco**: MongoDB Atlas (TLS) | **Auth**: JWT | **PWA**: Service Worker

## Conexão MongoDB
- `.env` configurado para **Atlas como padrão**
- TLS habilitado automaticamente para `mongodb+srv://`
- Validação REAL no startup — se falhar, servidor **NÃO inicia**
- Para local: trocar MONGO_URL por `mongodb://localhost:27017`

## Credenciais
- **admin@teste.com / 123456** (auto-criado no startup)
- admin@digitalcodex.com / admin123 (via seed)
- garcom/caixa/cozinha/bar@digitalcodex.com (via seed)

## Endpoints
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | /health | Health check (MongoDB) |
| GET | /api/health | Health check (via proxy) |
| GET | /api/ping | Pong + timestamp |
| POST | /api/login | Login (alias) |
| POST | /api/register | Registro (alias) |
| POST | /api/auth/login | Login (original) |
| POST | /api/auth/register | Registro (original) |
| GET | /api/auth/me | Dados do usuário |

## Comandos para rodar

### Backend
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install --legacy-peer-deps
npm start
```

## Implementado
- [x] Auth JWT com 5 perfis
- [x] MongoDB Atlas com TLS + validação no startup
- [x] Auto-create admin@teste.com no startup
- [x] Health check + ping
- [x] Dashboard, Mesas, Pedidos, Kanban Cozinha/Bar
- [x] Caixa, Cardápio CRUD, Estoque com alertas
- [x] Baixa automática de estoque ao entregar
- [x] Cancelamento inteligente de pedidos
- [x] Alertas de risco de estoque
- [x] Socket.IO tempo real + PWA offline
- [x] Rebranding "Gestor Restô"

## Backlog
### P1
- [ ] Transferência/junção de mesa
- [ ] Divisão de conta por pessoa
### P2
- [ ] Integração real NF-e e WhatsApp
- [ ] Exportação relatórios (PDF/Excel)
### P3
- [ ] Delivery, app mobile, programa fidelidade

---
*Última atualização: Abril 2026*
