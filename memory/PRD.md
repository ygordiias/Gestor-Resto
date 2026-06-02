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

---
*Última atualização: Abril 2026*
