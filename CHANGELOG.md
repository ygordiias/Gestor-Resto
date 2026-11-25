# Changelog

Mudanças do Gestor Restô, da mais recente para a mais antiga. Montado a partir do histórico do git da `main`. Commits automáticos da plataforma de desenvolvimento usada no início (mensagens "auto-commit" e "Auto-generated changes") foram agrupados por período.

## [Não lançado]

### Adicionado
- `LICENSE` proprietário e `AUTHORS.md`: criado e desenvolvido por Ygor Dias, Tecno Dias; primeiro restaurante: EMAÚS (São Carlos/SP).
- `GET /api/versao`: sistema, versão, autor, empresa e hash do commit em execução.
- Rodapé de autoria discreto no painel interno e na tela de login.
- Campo `author` no `frontend/package.json` e constantes de autoria em `backend/sobre.py`.
- Documentação em `docs/`: arquitetura, API, OpenAPI exportado, regras de negócio, integração NostFood, preparação para o iFood, operação e segurança/LGPD.
- `backend/scripts/exportar_openapi.py`: gera `docs/openapi.json` sem subir servidor e sem banco.

## [1.0.0] - 2026-11-21

Primeira versão numerada: estado da `main` em produção no EMAÚS.

### Corrigido
- Comandas físicas de **200 a 291**, configuráveis por `PHYSICAL_TAB_MIN` e `PHYSICAL_TAB_MAX`; frontend lê a faixa do servidor (PR #6).

## 2026-11-12 - Segurança e caixa (PR #3)

### Segurança
- Fim do cadastro público; contas só por admin. Primeiro superadmin por variáveis de ambiente.
- `SECRET_KEY` obrigatória, sem valor padrão; rotas que estavam abertas passam a exigir perfil.
- Conta desativada perde o acesso na hora; proteção do superadmin; `PUT /users` só aceita campos permitidos.
- Credenciais removidas do repositório.

### Corrigido
- Fechamento de comanda validado, atômico (transação) e idempotente: troco só do dinheiro, total sempre do banco.

### Adicionado
- Scripts de diagnóstico e regularização do caixa travado (simulação por padrão).

## 2026-10-28 a 2026-11-01 - Módulos financeiro e operacional

### Adicionado
- Relatório semanal da taxa de serviço (10%).
- Crédito interno de funcionários: limite mensal, desconto, acerto manual e estorno.
- Tarefas operacionais com comprovação por foto (GridFS) e aprovação; rotas v2.
- Histórico de notas paginado e relatório avançado por período, canal e forma de pagamento.

### Corrigido
- 10% e consumo de funcionários.

## 2026-10-20 a 2026-10-27 - Caixa e pedidos online

### Adicionado
- Prévia do fechamento do caixa, com impressão e token de conferência.
- Formas de pagamento separadas no fechamento (dinheiro, Pix, crédito, débito, voucher).
- Pedidos online sinalizados no fechamento e finalizados como repasse pendente.

### Corrigido
- Botões de prévia e fechamento do caixa; atualização de pedidos online; comandas aparecendo no bar.

## 2026-10-12 a 2026-10-17 - Comandas físicas e KDS

### Adicionado
- Comandas físicas individuais (inicialmente 200 a 230), com pagamentos separados e cadastro automático.
- Busca rápida de mesas por número.
- Painel da cozinha agrupado por comanda, com cronômetro e navegação por teclado.
- Painel da chapa sincronizado com a cozinha, em tela cheia.
- Menu lateral retrátil em todos os painéis.
- Impressão térmica de pré-conta; faturamento oculto no PDV.

### Corrigido
- Não libera nem limpa mesa com comanda aberta; rolagem automática no bar.

## 2026-09-12 a 2026-10-01 - Estabilidade e cancelamento de item

### Adicionado
- Cancelamento de item (total ou parcial) com senha de admin e escolha de devolver ou não o estoque.
- Exportação de relatórios em planilha.

### Corrigido
- Tela branca e redirecionamentos em queda de rede: `ErrorBoundary`, sessão mantida em erro de rede, reconexão sem limite do Socket.IO, `/api/health` leve.
- Alerta de estoque para itens independentes; ajuste de permissões.

## 2026-07-22 a 2026-08-29 - Deploy próprio e correções

### Adicionado
- Cadastro de mesas.

### Corrigido
- Estoque que não baixava quando a comanda era fechada sem passar por "entregue" (marca `stock_deducted`).
- Dependências do backend e do frontend simplificadas para o deploy no Render; dependência privada da plataforma removida.

## 2026-01-09 a 2026-06-30 - Primeiras versões

Desenvolvimento inicial: autenticação JWT por perfil, mesas, pedidos, cozinha e bar em tempo real (Socket.IO), caixa, cardápio, estoque com alertas, ficha técnica, receitas e CMV, produção, relatórios, notas (simuladas), PWA e cardápio público do cliente com código `EM-0001`.
