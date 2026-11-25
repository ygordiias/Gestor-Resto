# API

Referência das rotas do backend na `main`. A especificação completa (modelos, parâmetros e respostas) está em [openapi.json](openapi.json), exportada direto do FastAPI.

Para atualizar o `openapi.json` depois de mudar rotas (não sobe servidor e não acessa banco):

```bash
python backend/scripts/exportar_openapi.py
```

## Convenções

- **Base:** todas as rotas ficam em `/api`, menos `GET /health`.
- **Autenticação:** `Authorization: Bearer <token>`. O token sai de `POST /api/auth/login`, vale 24 horas e é invalidado na hora se a conta for desativada.
- **Erros:** `{"detail": "mensagem"}`. Códigos usados: 400 (dado inválido), 401 (sem token, token inválido ou conta desativada), 403 (perfil sem permissão), 404, 409 (conflito de estado: comanda em uso, pedido já fechado, caixa com pendência), 422 (validação), 503 (banco indisponível ou sem transação).
- **Datas:** ISO 8601 em UTC. Relatórios por dia usam o fuso `America/Sao_Paulo`.
- **Dinheiro:** reais com duas casas no JSON. O caixa e os relatórios novos calculam em centavos inteiros para não errar arredondamento.

### Legenda de permissões

| Sigla | Quem passa |
|---|---|
| público | Qualquer um, sem token |
| logado | Qualquer conta ativa |
| equipe | admin, garçom, caixa, cozinha, bar |
| caixa | admin e caixa |
| mesa | admin, garçom e caixa |
| status | admin, cozinha, bar e garçom |
| admin | só admin |
| senha admin | Qualquer conta logada, mas o corpo precisa trazer e-mail e senha de um admin ou superadmin ativo |

O **superadmin passa em todas**. As regras são aplicadas no backend; o frontend só esconde telas.

## Sistema

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/health` | público | Readiness: faz ping no MongoDB; 503 se o banco não responder |
| GET | `/api/health` | público | Liveness: 200 sempre que o processo estiver vivo, sem consultar o banco |
| GET | `/api/ping` | público | `pong` com horário |
| GET | `/api/versao` | público | Sistema, versão, autor, empresa e hash do commit em execução |
| GET | `/api/` | público | Mensagem de identificação da API |

Exemplo de `GET /api/versao`:

```json
{
  "sistema": "Gestor Restô",
  "versao": "1.0.0",
  "autor": "Ygor Dias",
  "empresa": "Tecno Dias",
  "commit": "4bf940a..."
}
```

O commit vem de `RENDER_GIT_COMMIT` (o Render define em cada deploy), depois de `GIT_COMMIT`, depois de `git rev-parse HEAD`; sem nenhum deles, `desconhecido`.

## Autenticação e usuários

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| POST | `/api/auth/login` | público | `{email, password}` → `{access_token, token_type, user}`. Conta desativada recebe 403 (só quem acertou a senha) |
| POST | `/api/login` | público | Mesmo que `/api/auth/login` |
| GET | `/api/auth/me` | logado | Dados da conta logada, sem a senha |
| GET | `/api/users` | admin | Lista contas (sem senha) |
| POST | `/api/users` | admin | Cria conta. Senha com pelo menos 8 caracteres. Só superadmin cria superadmin |
| PUT | `/api/users/{id}` | admin | Altera só `name`, `email`, `role`, `password`, `is_active`. Ninguém muda o próprio perfil nem se desativa. Só superadmin mexe em superadmin |
| DELETE | `/api/users/{id}` | admin | **Desativa** a conta (não apaga), para preservar o histórico |

Não existe cadastro público.

## Cardápio

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/categories` | equipe | Lista categorias |
| POST / PUT / DELETE | `/api/categories[/{id}]` | admin | Cria, altera, apaga |
| GET | `/api/products` | equipe | Lista produtos |
| GET | `/api/products/{id}` | equipe | Um produto |
| POST / PUT / DELETE | `/api/products[/{id}]` | admin | Cria, altera, apaga |

## Mesas e comandas físicas

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/tables` | equipe | Lista mesas |
| POST | `/api/tables` | admin | Cria mesa (número único) |
| PUT | `/api/tables/{id}` | mesa | Admin altera `status`, `capacity`, `table_type`, `note`; garçom e caixa só `status`. Não libera nem limpa mesa com pedido aberto (409) |
| PUT | `/api/tables/{id}/status` | mesa | Só o status, com a mesma trava |
| POST | `/api/tables/{id}/request-cleaning` | mesa | Põe em limpeza se não houver pedido aberto |
| DELETE | `/api/tables/{id}` | admin | Apaga mesa |
| GET | `/api/tabs` | logado | Lista as comandas físicas e o vínculo atual |
| GET | `/api/tabs/config` | logado | Faixa das comandas: `{min, max}` (padrão 200 a 291) |
| POST | `/api/tabs/range` | admin | Cadastra comandas de `start` a `end` dentro da faixa (só as que faltam) |
| GET | `/api/tables/{id}/tabs` | logado | Pedidos abertos da mesa que têm comanda física |
| POST | `/api/tables/{id}/tabs` | logado | Vincula a comanda `{tab_number}` à mesa e cria o pedido vazio. 409 se a comanda já estiver em uso |

## Pedidos

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/orders` | admin | Lista com filtros `status` e `is_closed` |
| GET | `/api/orders/open` | equipe | Pedidos abertos |
| GET | `/api/orders/table/{table_id}` | equipe | Pedido aberto da mesa |
| GET | `/api/orders/{id}` | equipe | Um pedido |
| POST | `/api/orders` | logado | Lança itens. Com `tab_number`, soma na comanda já vinculada; sem, usa o pedido sem comanda da mesa. Recalcula subtotal, 10% e total |
| PUT | `/api/orders/{id}/item/{item_id}/status` | status | `{status}`. Ao virar `delivered` pela primeira vez, dá baixa no estoque |
| PATCH | `/api/orders/{id}/item/{item_id}/courtesy` | caixa | `{is_courtesy, reason}`. Zera o preço do item e recalcula |
| PATCH | `/api/orders/{id}/item/{item_id}/cancel` | senha admin | `{quantity, reason, admin_email, admin_password, restore_stock}`. Cancela total ou parcial |
| PATCH | `/api/orders/{id}/cancel` | senha admin | `{reason, admin_email, admin_password}`. Cancela a comanda inteira e libera mesa e comanda |
| POST | `/api/orders/{id}/cancel-quick` | admin | Cancela se nenhum item saiu de `pending` |
| PATCH | `/api/orders/{id}/comp` | caixa | `{is_comp, comp_reason}`. Marca o pedido como cortesia ou permuta |
| POST | `/api/orders/{id}/close` | caixa | `{payments: [{method, amount}]}`. Fecha a comanda do salão (veja [regras-de-negocio.md](regras-de-negocio.md#fechamento-da-comanda)) |
| POST | `/api/orders/online` | caixa | Lança pedido do iFood, 99Food ou outro: `{platform, external_order_number, delivery_type, items}` |
| POST | `/api/orders/{id}/complete-online` | caixa | Finaliza pedido online sem pagamento no caixa (aguardando repasse) |

Formas de pagamento aceitas: `cash`, `pix`, `credit`, `debit`, `voucher` e `card` (só para histórico antigo).

## Caixa

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/cash-register/current` | caixa | Caixa aberto (ou `null`) |
| POST | `/api/cash-register/open` | caixa | `{initial_amount}`. Um caixa aberto por vez. O operador vem do token |
| POST | `/api/cash-register/withdrawal` | caixa | Sangria `{amount, reason}` |
| POST | `/api/cash-register/deposit` | caixa | Reforço `{amount, reason}` |
| GET | `/api/cash-register/preview` | caixa | Prévia do fechamento (somente leitura) com `preview_token` válido por 10 minutos |
| POST | `/api/cash-register/close` | caixa | `{preview_token, printed_confirmed: true}`. Fecha o caixa se nada mudou desde a prévia |
| GET | `/api/cash-register/last-closed/report` | caixa | Relatório do último fechamento |
| GET | `/api/cash-register/{id}/closing-report` | caixa | Relatório de um fechamento |

## Estoque, ficha técnica, CMV e produção

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/stock` | admin | Lista (filtro `stock_type`) |
| POST | `/api/stock` | admin | Cria item: precisa de `product_id` ou `name` |
| PUT | `/api/stock/{id}` | admin | Altera |
| GET | `/api/stock/alerts` | admin | Itens no mínimo ou abaixo |
| GET | `/api/stock/risk-alerts` | admin | Risco de falta pelo consumo médio dos últimos 7 dias |
| GET | `/api/recipes` | logado | Receitas de custo |
| GET | `/api/recipes/{id}` e `/api/recipes/by-product/{product_id}` | logado | Receita com custo por ingrediente |
| POST / PUT / DELETE | `/api/recipes[/{id}]` | admin | Uma receita por produto |
| GET | `/api/products/{id}/cmv` | logado | Preço, custo, lucro e margem de um produto |
| GET | `/api/cmv/report` | admin | CMV de todos os produtos |
| GET | `/api/technical-sheets`, `/{id}`, `/by-product/{product_id}` | logado | Fichas técnicas de montagem |
| POST / PUT / DELETE | `/api/technical-sheets[/{id}]` | admin | Uma ficha por produto |
| GET | `/api/production-recipes`, `/{id}`, `/by-stock/{stock_id}` | logado | Fórmulas de produção |
| POST / PUT / DELETE | `/api/production-recipes[/{id}]` | admin | Uma fórmula por item produzido |
| POST | `/api/productions` | admin | Registra produção: por fórmula (`production_recipe_id`, `batches`) ou direta |
| GET | `/api/productions` | admin | Histórico |
| GET | `/api/productions/dashboard` | admin | Produzido, consumido, saldo e custo |

## Relatórios

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/reports/sales?period=daily\|weekly\|monthly` | admin | Total, número de pedidos, ticket médio e 10 produtos mais vendidos (sem cortesia) |
| GET | `/api/reports/profit?period=` | admin | Estimativa simplificada: custo fixo de 35% das vendas |
| GET | `/api/reports/sales-by-table?period=` | caixa | Consumo por mesa, separando cortesia |
| GET | `/api/reports/service-fees/weekly?week=AAAA-MM-DD` | admin | Taxa de serviço por dia na semana (segunda a domingo), só pedidos do salão conciliados |
| GET | `/api/reports/advanced?start=&end=&channel=&payment=&group_by=&search=` | admin | Período de até 366 dias, por dia, semana ou mês, canal salão ou online, formas de pagamento e 20 produtos mais vendidos |

## Notas

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/invoices` | caixa | Lista todas as notas (inclui CPF) |
| POST | `/api/invoices` | caixa | Registra nota `{order_id, customer_name, customer_cpf}` com status `mock` (não há emissor fiscal) |
| GET | `/api/invoices/history` | caixa | Histórico paginado com filtros, **sem** o CPF |

## Crédito de funcionários

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/employee-credit/employees` | caixa | Funcionários com limite, uso, pago, em aberto e atrasado do mês |
| POST | `/api/employee-credit/employees` | admin | Cadastra `{name, monthly_limit, discount_pct}` |
| PUT | `/api/employee-credit/employees/{id}` | admin | Altera limite, desconto e ativo |
| GET | `/api/employee-credit/employees/{id}/statement?month=AAAA-MM` | admin | Extrato do mês |
| POST | `/api/employee-credit/purchases` | caixa | Lança consumo `{employee_id, request_id, items}` (idempotente pelo `request_id`) |
| POST | `/api/employee-credit/employees/{id}/settlements` | admin | Acerto manual `{request_id, month, amount, note}` |
| POST | `/api/employee-credit/employees/{id}/void-purchase` | admin | Estorna um consumo `{request_id, purchase_id, note}` |

## Tarefas operacionais

**v2 (com foto, usada pela tela `/tasks`):**

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/operations/v2/photo-status` | equipe | Confirma que o backend aceita foto (até 6 MiB, GridFS, exige aprovação) |
| GET | `/api/operations/v2/assignees` | admin | Contas que podem receber tarefa |
| GET | `/api/operations/v2/tasks?sector=&state=` | equipe | Tarefas visíveis para o perfil |
| POST | `/api/operations/v2/tasks` | admin | Cria tarefa |
| PUT | `/api/operations/v2/tasks/{id}` | admin | Edita |
| POST | `/api/operations/v2/tasks/{id}/complete` | equipe | Conclusão sem foto (compatibilidade) |
| POST | `/api/operations/v2/tasks/{id}/complete-photo` | equipe | Envia foto (multipart) para aprovação |
| GET | `/api/operations/v2/tasks/{id}/photos/{photo_id}` | equipe | Baixa a foto |
| POST | `/api/operations/v2/tasks/{id}/review` | admin | Aprova ou reprova a foto |
| POST | `/api/operations/v2/tasks/{id}/blocker` | equipe | Registra impedimento |
| GET | `/api/operations/v2/tasks/{id}/history` | equipe | Histórico de eventos |

**v1 (legado, coleção `operations_tasks`):** `GET /api/operations/tasks` (logado), `POST`, `PUT`/`PATCH`, `DELETE /api/operations/tasks[/{id}]` (admin) e `PATCH /api/operations/tasks/{id}/complete` (logado).

## Configurações

| Método | Rota | Permissão | Descrição |
|---|---|---|---|
| GET | `/api/settings` | admin | `{restaurant, operations, fiscal}` |
| PUT | `/api/settings` | admin | Salva os blocos enviados. Nome, endereço e CNPJ também vão para a configuração pública |

## Cardápio público (cliente)

Sem autenticação. Usadas por `/cliente`.

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/public/config` | Nome, WhatsApp, taxa de entrega, pedido mínimo, horário |
| GET | `/api/public/cardapio` | Produtos disponíveis (sem o custo) e categorias |
| GET | `/api/public/cardapio/categorias` | Categorias |
| POST | `/api/public/pedido` | Cria pedido online `{customer_name, customer_phone, delivery_type, address, payment_method, change_for, items}` e devolve o código `EM-0001` |
| GET | `/api/public/pedido/{codigo}` | Status do pedido pelo código (sem dados do cliente) |

## Pendente em outras branches

- **`feat/integracao-nostfood`:** rotas em `/api/integrations/nostfood/*` (webhook, status, simulação, ligação de produtos, não recebido, observações, cancelados no KDS, perdas). Veja [integracoes/nostfood.md](integracoes/nostfood.md).
- **`fix/cors-socket` (PR #4):** `CORS_ORIGINS` obrigatório e Socket.IO com token.
- **`fix/estoque-cmv` (PR #5):** unidade na receita, falhas de baixa visíveis e CMV com indicador de incompleto.
