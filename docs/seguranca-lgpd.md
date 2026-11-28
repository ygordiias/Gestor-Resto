# Segurança e LGPD

Inventário dos dados pessoais que o Gestor guarda, quem acessa, por quanto tempo e como apagar. Estado da `main` (commit `4bf940a`), levantado lendo o código.

> Este documento descreve o sistema. Não é parecer jurídico. Os papéis de controlador e operador e os prazos legais de guarda precisam ser confirmados com o jurídico e o contador **[confirmar]**.

## Dados pessoais guardados

| Titular | Dado | Onde (coleção.campo) | Origem | Para quê |
|---|---|---|---|---|
| Cliente do cardápio online | Nome, telefone, endereço, forma de pagamento, troco | `orders.customer_name`, `customer_phone`, `address`, `payment_method`, `change_for` | `POST /api/public/pedido` | Preparar e entregar o pedido |
| Cliente da NostFood (iFood, 99) **[branch]** | Nome, telefone, endereço completo, CEP, latitude e longitude | `orders.customer_name`, `customer_phone`, `address`, `customer_address`, `latitude`, `longitude` | Integração NostFood | Entregar o pedido |
| Cliente da NostFood **[branch]** | Pedido bruto completo como veio da NostFood | `nostfood_events.payload` | Webhook | Auditoria e reprocessamento. Apagado sozinho após 30 dias |
| Cliente que pede nota | Nome e **CPF** | `invoices.customer_name`, `customer_cpf` | Caixa | Registro da nota (emissão ainda simulada) |
| Funcionário com conta | Nome, e-mail, senha (só o hash bcrypt), perfil, datas de criação e desativação | `users` | Admin | Acesso ao sistema e autoria das ações |
| Funcionário com conta | Autoria de ações: quem lançou, fechou, cancelou, autorizou, abriu o caixa | `orders.*_by_*`, `payments.created_by_id`, `cash_registers.opened_by*`, `closed_by*`, `cash_movements.created_by`, `productions.user_*` | Uso do sistema | Auditoria |
| Funcionário com crédito | Nome, limite mensal, desconto, consumos, acertos e saldo devedor | `employee_credit_employees`, `employee_credit_accounts` | Admin e caixa | Consumo interno a prazo |
| Funcionário | Fotos de comprovação de tarefas (podem mostrar pessoas) e observações | GridFS (`fs.files`, `fs.chunks`), `operational_tasks.events` | Tela de tarefas | Comprovar a execução |
| Restaurante | CNPJ, endereço, WhatsApp | `settings` | Admin | Configuração |

### Fora do banco

- **Navegador** (`localStorage`): o token JWT e os dados da conta logada (`token`, `user`), além de cache de produtos, categorias e mesas e da fila de pedidos offline. Em aparelho compartilhado, quem abrir o navegador entra com a sessão até ela expirar (24 h) ou até alguém sair.
- **Logs do servidor (Render):** nome de quem cancelou e de quem autorizou, motivo do cancelamento, e-mail do superadmin inicial quando criado, mensagens de estoque baixo. Senha, hash, token e endereço do banco **não** são registrados.
- **Código-fonte:** o número de WhatsApp do administrador está fixo em `server.py` (`ADMIN_PHONE` e o valor padrão de `public_config.whatsapp`).

## Quem acessa

| Dado | Perfis com acesso pela API |
|---|---|
| Pedidos com dados do cliente | equipe inteira (`GET /api/orders/open`, `/api/orders/{id}`), admin (`GET /api/orders`) |
| CPF das notas | ninguém pela API: `GET /api/invoices` e `POST /api/invoices` devolvem o CPF mascarado (`***.456.***-**`) e o histórico paginado não devolve o CPF. O banco guarda o CPF completo |
| Contas de usuário | admin e superadmin (sem senha) |
| Crédito de funcionários | caixa vê lista e saldos; admin vê extratos e faz acertos |
| Fotos das tarefas | equipe, com regra por setor e responsável |
| Status do pedido público | qualquer um com o código `EM-0000`. Mostra itens, status e total, **sem** nome, telefone ou endereço |

### Pontos de exposição conhecidos

| Ponto | Risco | Situação |
|---|---|---|
| Socket.IO **sem autenticação** e com broadcast | Os eventos `kitchen_update` e `bar_update` levam **todos os pedidos abertos**, com nome, telefone e endereço de clientes online, para qualquer cliente que conectar no Socket.IO | Corrigido na branch `fix/cors-socket` (PR #4, aberta) |
| CORS liberado para qualquer origem (`*`) | Qualquer site pode chamar a API a partir do navegador de um usuário logado | Corrigido no PR #4 (`CORS_ORIGINS`) |
| Chave do emissor fiscal | `settings.fiscal.taxApiKey` fica em texto puro no banco. A API nunca devolve o valor (`GET /api/settings` só informa `taxApiKeyConfigured`) | Cifrar no banco: em aberto |
| Código do pedido público sequencial | `EM-0001`, `EM-0002`... é fácil de adivinhar; expõe itens e total, não dados pessoais | Em aberto |
| Backups manuais (`mongodump`) | Contêm todos os dados acima | Guardar fora do repositório, com acesso restrito |

### Controles que já existem

- Senhas com bcrypt. Mínimo de 8 caracteres (12 para o superadmin inicial).
- `SECRET_KEY` obrigatória (mínimo 32 caracteres), sem valor padrão.
- Conta desativada perde o acesso na hora, mesmo com token válido.
- Sem cadastro público. Só superadmin mexe em superadmin. Ninguém muda o próprio perfil nem se desativa.
- Cancelamento exige e-mail e senha de um admin, com motivo, e grava quem autorizou e quem operou.
- TLS com validação de certificado no MongoDB Atlas.
- Nenhuma credencial no repositório (removidas no PR #3).

## Retenção

**Hoje não há exclusão automática** de dados pessoais na `main`. Tudo fica guardado até alguém apagar.

| Dado | Retenção atual | Sugestão **[confirmar com jurídico e contador]** |
|---|---|---|
| Pedidos e pagamentos | Indefinida | Manter os valores pelo prazo fiscal; **anonimizar** nome, telefone e endereço do cliente depois de alguns meses (ex.: 6 meses) |
| CPF em notas | Indefinida | Manter pelo prazo fiscal exigido |
| Eventos da NostFood **[branch]** | 30 dias (índice TTL) | Manter |
| Usuários desativados | Indefinida (nunca são apagados, para preservar a autoria) | Manter nome e e-mail enquanto houver registros ligados; avaliar anonimizar o e-mail |
| Crédito de funcionários | Indefinida | Manter até o acerto e pelo prazo trabalhista aplicável |
| Fotos das tarefas | Indefinida | Apagar após 90 dias da aprovação |
| Backups manuais | Conforme quem guardou | Prazo definido e apagar os antigos |

## Como apagar ou anonimizar

Não existe rota para isso. O procedimento é manual, feito por quem tem acesso ao banco, sempre nesta ordem:

1. Registrar o pedido do titular (quem pediu, quando, o quê).
2. Fazer backup (veja [operacao.md](operacao.md#backup)).
3. **Testar os comandos em um banco de teste** restaurado do backup.
4. Aplicar na produção e registrar o que foi feito.

Para pedidos, **anonimize** em vez de apagar: o pedido sustenta o caixa, os relatórios e a baixa de estoque. Apagar o documento quebra o fechamento do caixa e os relatórios.

Exemplos para o `mongosh` (conferir antes com `find`/`countDocuments` usando o mesmo filtro):

```javascript
// Cliente de pedidos online, pelo telefone
const filtro = { customer_phone: "<telefone do titular>" };
db.orders.countDocuments(filtro);
db.orders.updateMany(filtro, {
  $set: { customer_name: "Anonimizado", customer_phone: null, address: null },
  $unset: { customer_address: "", latitude: "", longitude: "", change_for: "" }
});

// Eventos brutos da NostFood com esse telefone [branch]
db.nostfood_events.deleteMany({ "payload.data.customer_phone": "<telefone do titular>" });

// CPF em notas (só depois de confirmar o prazo fiscal)
db.invoices.updateMany({ customer_cpf: "<cpf>" }, { $set: { customer_cpf: null, customer_name: "Anonimizado" } });
```

Para **funcionários**, desative a conta (`DELETE /api/users/{id}`); o nome continua nos registros de autoria. Para apagar fotos de tarefas, remova pelo id da foto no GridFS (`fs.files` e `fs.chunks`) e o `photo_id` correspondente em `operational_tasks.events`.

## Próximos passos sugeridos

1. Integrar o PR #4 (Socket.IO autenticado e CORS restrito): é o maior risco de vazamento hoje.
2. Definir os prazos de retenção com o jurídico e o contador.
3. Criar uma rotina de anonimização automática dos pedidos antigos.
4. Tirar o WhatsApp do administrador do código (variável de ambiente ou `settings`).
5. Guardar a chave do emissor fiscal fora do banco (variável de ambiente).
6. Trocar o código do pedido público por um código não sequencial.
