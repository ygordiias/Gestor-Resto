# Digital Codex - Sistema de Gestão para Restaurante

## Descrição
Sistema completo de gestão para restaurante com conceito bíblico sutil, comandas 100% digitais, controle total pelo administrador.

## Personas de Usuário
1. **Administrador** - Acesso total ao sistema (dashboard, relatórios, configurações, usuários)
2. **Garçom** - Gerenciamento de mesas e pedidos
3. **Caixa** - Fechamento de comandas, controle de caixa
4. **Cozinha** - Visualização e gerenciamento de pedidos de comida
5. **Bar** - Visualização e gerenciamento de pedidos de bebida

## Requisitos Core (Implementados)
- [x] Autenticação JWT com 5 perfis de usuário
- [x] Dashboard administrativo com gráficos
- [x] Painel de mesas com status visual colorido (15 mesas)
- [x] Sistema de pedidos/comandas digitais
- [x] Painel Kanban para Cozinha (apenas comidas)
- [x] Painel Kanban para Bar (apenas bebidas)
- [x] Separação automática de itens por tipo (comida/bebida)
- [x] Caixa com múltiplas formas de pagamento (dinheiro, cartão, PIX, vale)
- [x] Abertura/fechamento de caixa com sangria e reforço
- [x] Cardápio CRUD completo com fotos e margem de lucro
- [x] Controle de estoque com alertas de mínimo
- [x] Relatórios de vendas (diário, semanal, mensal)
- [x] Gestão de usuários
- [x] Módulo NF-e (MOCK preparado para integração)
- [x] Comunicação em tempo real via Socket.IO
- [x] Tema bíblico (tons dourados/marrons)
- [x] Design responsivo para tablets e celulares

## Stack Tecnológico
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Python
- **Banco de Dados**: MongoDB
- **Tempo Real**: Socket.IO
- **Autenticação**: JWT

## Credenciais de Teste
- Admin: admin@digitalcodex.com / admin123
- Garçom: garcom@digitalcodex.com / garcom123
- Caixa: caixa@digitalcodex.com / caixa123
- Cozinha: cozinha@digitalcodex.com / cozinha123
- Bar: bar@digitalcodex.com / bar123

## O Que Foi Implementado (Janeiro 2025)
1. Sistema de autenticação completo
2. Dashboard com estatísticas e gráficos
3. 15 mesas com status visual
4. 20 produtos em 9 categorias
5. Painéis Kanban para cozinha e bar
6. Sistema de caixa completo
7. Relatórios financeiros
8. Gestão de estoque
9. CRUD de produtos e categorias
10. Gestão de usuários
11. Módulo NF-e (mock)
12. Configurações do sistema

## Backlog Prioritizado
### P0 (Crítico)
- Nenhum item pendente

### P1 (Alta Prioridade)
- [ ] Transferência de mesa
- [ ] Juntar mesas
- [ ] Divisão de conta detalhada

### P2 (Média Prioridade)
- [ ] Integração real com API de NF-e (Focus NFe/Webmania)
- [ ] Exportação de relatórios (PDF/Excel)
- [ ] Reservas de mesa
- [ ] Modo offline com sincronização

### P3 (Baixa Prioridade)
- [ ] Delivery integrado
- [ ] App mobile nativo
- [ ] Dashboard personalizado
- [ ] Notificações push

## Próximas Tarefas
1. Implementar transferência/junção de mesas
2. Adicionar divisão de conta por pessoa
3. Integrar API de NF-e real
4. Implementar exportação de relatórios
