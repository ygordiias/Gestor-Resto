# Gestor Restô - Sistema de Gestão para Restaurante

## Descrição
Sistema completo de gestão para restaurante, moderno e profissional, comandas 100% digitais, controle total pelo administrador.

## Personas de Usuário
1. **Administrador** - Acesso total ao sistema (dashboard, relatórios, configurações, usuários)
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
- **Cor Principal**: #1f2937 (cinza escuro)
- **Cor Secundária/Accent**: #f59e0b (laranja/dourado)
- **Cor de Fundo**: #111827
- **Texto**: branco
- **Fonte Heading**: Plus Jakarta Sans (bold)
- **Fonte Body**: DM Sans
- **Logo**: Componente reutilizável em `/app/frontend/src/components/Logo.js`

## Credenciais de Teste
- Admin: admin@digitalcodex.com / admin123
- Garçom: garcom@digitalcodex.com / garcom123
- Caixa: caixa@digitalcodex.com / caixa123
- Cozinha: cozinha@digitalcodex.com / cozinha123
- Bar: bar@digitalcodex.com / bar123

## Requisitos Implementados

### Core
- [x] Autenticação JWT com 5 perfis de usuário
- [x] Dashboard administrativo com gráficos
- [x] Painel de mesas com status visual colorido (15 mesas)
- [x] Sistema de pedidos/comandas digitais
- [x] Painel Kanban para Cozinha (apenas comidas)
- [x] Painel Kanban para Bar (apenas bebidas)
- [x] Separação automática de itens por tipo (comida/bebida)
- [x] Caixa com múltiplas formas de pagamento
- [x] Cardápio CRUD completo com fotos e margem de lucro
- [x] Controle de estoque com alertas de mínimo
- [x] Relatórios de vendas (diário, semanal, mensal)
- [x] Gestão de usuários
- [x] Módulo NF-e (MOCK preparado)
- [x] Comunicação em tempo real via Socket.IO
- [x] Design responsivo para tablets e celulares
- [x] Configuração ASGI para produção (uvicorn + Socket.IO)
- [x] Rebranding completo: "Gestor Restô" com identidade visual moderna

### Funcionalidades de Mesa
- [x] Status: Disponível, Ocupada, Reservada, Aguardando Limpeza
- [x] Reserva de mesa / Cancelamento de reserva
- [x] Solicitar limpeza / Marcar como disponível

### Notificações em Tempo Real
- [x] Beep sonoro + Toast para novos pedidos (cozinha/bar)
- [x] Notificação para garçom quando item está pronto

### Suporte Offline (PWA)
- [x] Service Worker + manifest.json
- [x] Cache offline + sincronização automática

### Deploy / Produção
- [x] `uvicorn backend.server:app --host 0.0.0.0 --port $PORT`

## Arquitetura de Arquivos

```
/app/
├── backend/
│   ├── server.py
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── public/ (index.html, manifest.json, sw.js)
│   └── src/
│       ├── components/ (Layout.js, Logo.js, ui/)
│       ├── contexts/ (AuthContext.js)
│       ├── lib/ (api.js, socket.js, utils.js)
│       └── pages/ (Login, Dashboard, Tables, Order, Kitchen, Bar, Cashier, Menu, Stock, Reports, Users, Invoices, Settings)
└── memory/ (PRD.md)
```

## Backlog

### P1 (Alta Prioridade)
- [ ] Transferência de mesa
- [ ] Juntar mesas
- [ ] Divisão de conta detalhada por pessoa

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
