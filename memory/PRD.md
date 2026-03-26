# Gestor Restô - Sistema de Gestão para Restaurante

## Descrição
Sistema completo de gestão para restaurante, moderno e profissional, comandas 100% digitais, controle total pelo administrador.

## Stack Tecnológico
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Python + MongoDB + Socket.IO
- **Auth**: JWT | **PWA**: Service Worker

## Identidade Visual
- **Nome**: Gestor Restô
- **Cores**: #1f2937 (principal), #f59e0b (accent), #111827 (fundo)
- **Fontes**: Plus Jakarta Sans (heading), DM Sans (body)

## Credenciais de Teste
- Admin: admin@digitalcodex.com / admin123
- Garçom/Caixa/Cozinha/Bar: [role]@digitalcodex.com / [role]123

## Implementado
- [x] Auth JWT com 5 perfis (admin, waiter, cashier, kitchen, bar)
- [x] Dashboard, Mesas (status/reserva/limpeza), Pedidos digitais
- [x] Kanban Cozinha/Bar com notificações sonoras + Socket.IO
- [x] Caixa com múltiplas formas de pagamento
- [x] Cardápio CRUD, Estoque com alertas, Relatórios, NF-e mock
- [x] PWA offline com sync automático
- [x] Rebranding "Gestor Restô" com tema escuro profissional
- [x] ASGI produção: `uvicorn backend.server:app`
- [x] Correção de contraste nos painéis Cozinha/Bar
- [x] **Controle completo de estoque (validação, baixa, alerta)**
- [x] **Cancelamento inteligente de pedidos**
- [x] **Alerta de risco de estoque via Socket.IO + WhatsApp (preparado)**

### Rotas Novas
- `POST /api/orders/{order_id}/cancel` — Cancela pedido (só se todos itens pending)
- `GET /api/stock/risk-alerts` — Detecta risco de falta baseado em consumo médio diário

### Funções Auxiliares
- `validate_stock(items)` — Bloqueia criação de pedido sem estoque
- `deduct_stock(product_id, qty)` — Baixa atômica com $inc
- `check_stock_alert(product_id)` — Emite alerta se qty < min_quantity
- `send_whatsapp_message(phone, msg)` — Preparado para API WhatsApp (atualmente loga)

## Backlog
### P1
- [ ] Transferência de mesa
- [ ] Juntar mesas
- [ ] Divisão de conta por pessoa

### P2
- [ ] Integração real API NF-e
- [ ] Exportação relatórios (PDF/Excel)
- [ ] Integração real API WhatsApp (Twilio/Z-API)
- [ ] Histórico de reservas

### P3
- [ ] Delivery integrado
- [ ] App mobile nativo
- [ ] Dashboard personalizado
- [ ] Programa de fidelidade

---
*Última atualização: Março 2026*
