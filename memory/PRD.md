# Gestor Restô - Sistema de Gestão para Restaurante

## Stack
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Python + Motor (async MongoDB) + Socket.IO
- **Banco**: MongoDB Atlas (TLS) | **Auth**: JWT | **PWA**: Service Worker

## Credenciais
- admin@teste.com / 123456 (auto-criado no startup)
- admin@digitalcodex.com / admin123 (via seed)

## URLs
- Admin: `/login`, `/dashboard`, `/kitchen`, `/bar`, `/cashier`...
- Cliente: `/cliente`, `/cliente/carrinho`, `/cliente/checkout`, `/cliente/confirmacao/:codigo`, `/cliente/acompanhar/:codigo`

## Implementado

### Sistema Admin (interno)
- [x] Auth JWT com 5 perfis
- [x] Dashboard, Mesas, Pedidos, Kanban Cozinha/Bar
- [x] Caixa, Cardápio CRUD, Estoque com alertas, Relatórios, NF-e mock
- [x] Socket.IO tempo real + PWA offline
- [x] Baixa automática de estoque + cancelamento inteligente
- [x] MongoDB Atlas ready com TLS

### Frontend Cliente (público) — NOVO
- [x] Cardápio digital com fotos, categorias e busca
- [x] Carrinho com +/- quantidade e limpar
- [x] Checkout: nome, telefone, endereço, tipo entrega, pagamento
- [x] Pagamento offline: PIX, Cartão, Dinheiro (com troco)
- [x] Confirmação com botão WhatsApp dinâmico
- [x] Acompanhamento em tempo real (Socket.IO)
- [x] Tema Emaús (gospel + rústico + moderno)
- [x] "Made in TecnoDias" no footer
- [x] Código de pedido: EM-0001, EM-0002...

### Rotas Públicas (backend)
- [x] `GET /api/public/config` — Config pública (WhatsApp, taxas)
- [x] `GET /api/public/cardapio` — Produtos + categorias
- [x] `GET /api/public/cardapio/categorias` — Categorias
- [x] `POST /api/public/pedido` — Criar pedido online
- [x] `GET /api/public/pedido/{codigo}` — Consultar status

### Modelo do Pedido Online
```json
{
  "source": "online",
  "origin": "web",
  "order_code": "EM-0001",
  "customer_name": "...",
  "customer_phone": "...",
  "delivery_type": "delivery|retirada",
  "address": "...",
  "payment_method": "pix|card|cash",
  "payment_status": "pending|paid|failed",
  "change_for": 100,
  "items": [{"product_id": "...", "name": "...", "price": 28.9, "quantity": 2}]
}
```

### Fichas Técnicas (módulo completo — Fev/2026)
- [x] Backend CRUD `/api/technical-sheets` (list, get, create, update, delete)
- [x] Endpoint smart: `GET /api/technical-sheets/by-product/{product_id}` (404 → criar nova)
- [x] Página lista `/technical-sheets` com busca e cards
- [x] Formulário `/technical-sheets/new` e `/technical-sheets/:id/edit`
- [x] Upload de imagem em base64 (até 2MB) + URL externa
- [x] Pré-preenchimento via query param `?product_id=...`
- [x] Botão **"Ficha Técnica"** em cada card do Cardápio (abre existente ou cria nova)
- [x] Visualização `/technical-sheets/:id` com print-area otimizada A4
- [x] Impressão via `window.print()`: logo, foto, nome, ingredientes (tabela), passos (lista), observações, data, rodapé
- [x] Permissão: visualização para todos os logados; criação/edição para admin/superadmin
- [x] Testes Pytest: `/app/backend/tests/test_technical_sheets.py` (10/10 verde)

### Modelo Ficha Técnica
```json
{
  "id": "uuid",
  "product_id": "uuid",
  "product_name": "...",
  "image_url": "https://... ou data:image/...",
  "ingredients": [{"name": "Pão", "quantity": "1 un"}],
  "assembly_steps": ["Montar...", "Servir..."],
  "notes": "...",
  "created_at": "iso8601",
  "updated_at": "iso8601"
}
```

### Integração
- Pedidos online → mesma collection `orders` → aparece na Cozinha/Bar/Caixa
- Usa `validate_stock()` existente antes de criar pedido
- Emite `new_online_order` via Socket.IO
- WhatsApp dinâmico via `/api/public/config`

## Arquivos Novos (nenhum existente foi alterado, exceto App.js +2 linhas)
```
/src/cliente/
├── ClienteApp.js
├── emaus-theme.css
├── pages/ (Cardapio, Carrinho, Checkout, Confirmacao, Acompanhar)
└── components/ (ProdutoCard, CategoriaNav, CarrinhoFlutuante, FooterTecnoDias)
```

## Backlog
### P1
- [ ] Pagamento online (Mercado Pago — aguardando CNPJ)
- [ ] Transferência/junção de mesa
- [ ] Divisão de conta por pessoa
### P2
- [ ] Integração real NF-e e WhatsApp API
- [ ] Exportação relatórios (PDF/Excel)
### P3
- [ ] Delivery, app mobile, programa fidelidade

## CMV / Receitas (Fev/2026)
- [x] Campo `unit_cost` em `stock`
- [x] Collection `recipes` + CRUD `/api/recipes`
- [x] `GET /api/products/{id}/cmv` + `GET /api/cmv/report`
- [x] StockPage: input `unit_cost` + badge no card
- [x] MenuPage: botão "Receita" + dialog em tempo real + CMV/Lucro/Margem em cada card
- [x] Página `/cmv` (CMVReportPage): stats + tabela + ordenação por lucro/margem
- [x] Sidebar item "CMV" (admin/superadmin)
- [x] Baixa automática por receita ao mudar item para `delivered` (fallback legado quando produto não tem receita)

## Produção (Jun/2026)
- [x] Collection nova: `productions`
- [x] `POST /api/productions` (admin/superadmin) — valida saldo, baixa ingredientes, soma quantidade ao item produzido, recalcula custo médio ponderado, audita usuário
- [x] `GET /api/productions` lista histórico
- [x] `GET /api/productions/dashboard` retorna {rows[produzido/consumido/estoque/custo], total_productions, total_produced_cost}
- [x] Página `/production` (ProductionPage): cards de stats + tabela Resumo (Produzido × Consumido × Estoque atual) + tabela Histórico + Dialog Nova Produção com cálculo em tempo real
- [x] Sidebar item "Produção" (admin + superadmin)
- [x] Integração total com CMV: consumo via pedidos `delivered` é deduzido em tempo real
- [x] Superadmin: pequenas correções em TablesPage.js e Layout.js para também incluir role superadmin nos blocos que estavam restritos a `'waiter' || 'admin'`

## Cancelamento de item individual (Fev/2026 - STEP 2)
- [x] `PATCH /api/orders/{order_id}/item/{item_id}/cancel` (surgical endpoint)
- [x] Cancelamento total OU parcial (split de linha preservando histórico completo)
- [x] Autorização obrigatória: admin_email + admin_password (mesmo padrão do cancelamento total). Cashier apenas nao autoriza.
- [x] Se `stock_deducted=False`: apenas marca cancelado — nunca sera deduzido.
- [x] Se `stock_deducted=True`: usuario escolhe "Devolver ao estoque?" (SIM/NAO). SIM chama nova função `restore_stock()` (espelho de `deduct_stock`, suporta receita e legado). NAO mantém baixa.
- [x] Recálculo automático de `subtotal`, `service_fee` (10%), `total` ignorando itens cancelados.
- [x] Auditoria por item: quantidade cancelada, preço original, motivo, cashier, admin autorizador, timestamp, se estoque foi devolvido.
- [x] UI do Caixa: botão X por item + dialog com quantidade, motivo, credenciais admin, radio de estoque (se aplicável). Item cancelado mostrado com badge CANCELADO e strike-through. Comanda fechada é read-only.
- [x] Preserva integridade: `full-order cancellation`, cortesia por item, `stock_deducted` idempotencia, workflow Cozinha/Bar, fechamento e relatorios existentes.
- [x] Realtime: emite `order_updated` e (quando aplicavel) `stock_updated`.
- [x] 8 testes pytest em `/app/backend/tests/test_item_cancellation.py` (8/8 passing).

## Estabilidade (Fev/2026 - STEP 1)
- [x] `GET /api/health` transformado em liveness leve (`{"status":"ok"}` sem depender de MongoDB); `GET /health` root mantém readiness com DB check
- [x] `ErrorBoundary` global (`/app/frontend/src/components/ErrorBoundary.js`) envolvendo o `<App>` — previne tela branca em erros React
- [x] Interceptor axios (`/app/frontend/src/lib/api.js`) não redireciona mais em falhas de rede/timeout; 401 só desloga fora do `/login` e fora de `/auth/login`
- [x] `AuthContext.js` mantém sessão local em erro de rede (só desloga em 401/403)
- [x] Socket.IO com `reconnectionAttempts: Infinity`, `reconnectionDelayMax: 5000`, logs de reconexão
- [x] Service Worker bump `v2 → v3` para invalidar caches antigos
- [x] Testes pytest em `/app/backend/tests/test_health.py` (3/3 passing)
- Nota SPA: refresh direto em qualquer rota (`/kitchen`, `/tables/xyz`, `/cliente/*`) já retorna 200 no ambiente atual — fallback é feito pela camada de ingress da plataforma Emergent, não precisa de config no repositório.

---
*Última atualização: Fevereiro 2026*
