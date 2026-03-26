# Gestor Restô - Sistema de Gestão para Restaurante

## Descrição
Sistema completo de gestão para restaurante, moderno e profissional, comandas 100% digitais, controle total pelo administrador.

## Personas de Usuário
1. **Administrador** - Acesso total ao sistema
2. **Garçom** - Gerenciamento de mesas e pedidos
3. **Caixa** - Fechamento de comandas, controle de caixa
4. **Cozinha** - Visualização e gerenciamento de pedidos de comida
5. **Bar** - Visualização e gerenciamento de pedidos de bebida

## Stack Tecnológico
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Python
- **Banco de Dados**: MongoDB
- **Tempo Real**: Socket.IO (python-socketio)
- **Autenticação**: JWT
- **PWA**: Service Worker + manifest.json

## Identidade Visual
- **Nome**: Gestor Restô
- **Cor Principal**: #1f2937 | **Accent**: #f59e0b | **Fundo**: #111827
- **Fontes**: Plus Jakarta Sans (heading), DM Sans (body)
- **Logo**: `/app/frontend/src/components/Logo.js`

## Credenciais de Teste
- Admin: admin@digitalcodex.com / admin123
- Garçom/Caixa/Cozinha/Bar: [role]@digitalcodex.com / [role]123

## Requisitos Implementados

### Core
- [x] Auth JWT com 5 perfis
- [x] Dashboard, Mesas, Pedidos, Kanban Cozinha/Bar, Caixa
- [x] Cardápio CRUD, Estoque com alertas, Relatórios, NF-e mock
- [x] Socket.IO tempo real + PWA offline
- [x] Rebranding "Gestor Restô"
- [x] ASGI produção: `uvicorn backend.server:app`
- [x] **Baixa automática de estoque ao entregar item**

### Baixa Automática de Estoque (novo)
- [x] `deduct_stock(product_id, quantity)` — função auxiliar
- [x] Só deduz quando status muda para "delivered" pela primeira vez
- [x] Validação: estoque insuficiente → HTTP 400
- [x] Produto sem estoque cadastrado → ignora silenciosamente
- [x] `last_updated` atualizado no stock
- [x] Evento Socket.IO `stock_updated` emitido em tempo real

## Backlog

### P1 (Alta Prioridade)
- [ ] Transferência de mesa
- [ ] Juntar mesas
- [ ] Divisão de conta por pessoa

### P2 (Média Prioridade)
- [ ] Integração real com API de NF-e
- [ ] Exportação de relatórios (PDF/Excel)
- [ ] Histórico de reservas

### P3 (Baixa Prioridade)
- [ ] Delivery integrado
- [ ] App mobile nativo
- [ ] Dashboard personalizado
- [ ] Programa de fidelidade

---
*Última atualização: Março 2026*
