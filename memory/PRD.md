# Digital Codex - Sistema de Gestão para Restaurante

## Descrição
Sistema completo de gestão para restaurante com conceito bíblico sutil, comandas 100% digitais, controle total pelo administrador.

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

## Credenciais de Teste
- Admin: admin@digitalcodex.com / admin123
- Garçom: garcom@digitalcodex.com / garcom123
- Caixa: caixa@digitalcodex.com / caixa123
- Cozinha: cozinha@digitalcodex.com / cozinha123
- Bar: bar@digitalcodex.com / bar123

## Requisitos Implementados ✅

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

### Funcionalidades de Mesa
- [x] Status: Disponível, Ocupada, Reservada, Aguardando Limpeza
- [x] Reserva de mesa (garçom/caixa)
- [x] Cancelamento de reserva
- [x] Solicitar limpeza (tablet do cliente)
- [x] Marcar mesa como disponível após limpeza

### Notificações em Tempo Real
- [x] Beep sonoro para novos pedidos (cozinha/bar)
- [x] Toast de notificação
- [x] Notificação para garçom quando item está pronto
- [x] Badge de notificações no header

### Suporte Offline (PWA)
- [x] Service Worker registrado
- [x] manifest.json para instalação
- [x] Cache de produtos/categorias/mesas no localStorage
- [x] Criação de pedidos offline (salvos localmente)
- [x] Sincronização automática quando voltar online
- [x] Fallback para dados em cache quando API indisponível

### Deploy / Produção
- [x] Configuração ASGI corrigida: `uvicorn backend.server:app --host 0.0.0.0 --port $PORT`
- [x] Socket.IO wrapping com `other_asgi_app=` explícito
- [x] Shutdown handler registrado antes do wrapping
- [x] uvicorn 0.25.0 no requirements.txt

## Arquitetura de Arquivos

```
/app/
├── backend/
│   ├── server.py          # FastAPI + Socket.IO (ASGI)
│   ├── requirements.txt   # Dependências Python
│   └── .env               # Variáveis de ambiente
├── frontend/
│   ├── public/
│   │   ├── index.html     # HTML com meta tags PWA
│   │   ├── manifest.json  # Manifest PWA
│   │   └── sw.js          # Service Worker
│   └── src/
│       ├── lib/
│       │   ├── api.js     # API com suporte offline
│       │   ├── socket.js  # Socket.IO com notificações
│       │   └── utils.js   # Utilitários
│       ├── contexts/
│       │   └── AuthContext.js
│       ├── components/
│       │   ├── Layout.js  # Layout com notificações
│       │   └── ui/        # Shadcn components
│       └── pages/
│           ├── LoginPage.js
│           ├── DashboardPage.js
│           ├── TablesPage.js
│           ├── OrderPage.js
│           ├── KitchenPage.js
│           ├── BarPage.js
│           ├── CashierPage.js
│           ├── MenuPage.js
│           ├── StockPage.js
│           ├── ReportsPage.js
│           ├── UsersPage.js
│           ├── InvoicesPage.js
│           └── SettingsPage.js
└── memory/
    └── PRD.md
```

## Backlog

### P0 (Crítico) - Nenhum pendente ✅

### P1 (Alta Prioridade)
- [ ] Transferência de mesa
- [ ] Juntar mesas
- [ ] Divisão de conta detalhada por pessoa

### P2 (Média Prioridade)
- [ ] Integração real com API de NF-e
- [ ] Exportação de relatórios (PDF/Excel)
- [ ] Histórico de reservas
- [ ] Impressão de comanda (opcional)

### P3 (Baixa Prioridade)
- [ ] Delivery integrado
- [ ] App mobile nativo
- [ ] Dashboard personalizado
- [ ] Programa de fidelidade

## Próximas Tarefas
1. Implementar transferência/junção de mesas
2. Adicionar divisão de conta por pessoa
3. Integrar API de NF-e real
4. Implementar exportação de relatórios

---
*Última atualização: Fevereiro 2026*
