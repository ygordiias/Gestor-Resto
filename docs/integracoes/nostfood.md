# Integração NostFood (pedidos do iFood e da 99)

> Branch `feat/integracao-nostfood`. Arquivo principal: `backend/nostfood_integration.py`. Testes: `backend/tests/test_nostfood_integration.py` e `backend/tests/test_nostfood_security.py`. Exemplo real anonimizado: `backend/tests/fixtures/nostfood_pedidos_reais.json`.

A NostFood junta os pedidos do iFood e da 99Food (e os pedidos feitos direto nela) e os entrega ao Gestor. O Gestor não fala direto com o iFood nem com a 99 nesta integração. Para a homologação direta com o iFood, veja [ifood-preparacao.md](ifood-preparacao.md).

## Que dados saem e entram

### Saídas: do Gestor para a NostFood

Toda chamada HTTP para a NostFood passa por uma única função, `nostfood_request()`, com
uma lista fixa (allowlist) de rotas e campos (`OUTBOUND_ALLOWLIST`). Qualquer outra rota,
parâmetro ou campo é recusado antes de sair (`OutboundBlocked`) e registrado no log como
`[NOSTFOOD][SAÍDA BLOQUEADA]`. Nenhum outro trecho do backend faz chamada HTTP.

| Método | Rota (`NOSTFOOD_BASE_URL` + …) | Cabeçalho | Campos enviados | Quando sai |
|---|---|---|---|---|
| GET | `pedidos.php` | `X-API-Key` | query: `data_inicio`, `data_fim` (AAAA-MM-DD), `limit`, `offset` (inteiros ≥ 0). Sem corpo. | Polling a cada `NOSTFOOD_POLL_SECONDS` (mínimo 30 s) e quando um webhook chega sem o pedido completo. |
| POST | `atualizar-pedido.php` | `X-API-Key` | JSON com exatamente 2 campos: `status` (`em_preparo` ou `pronto`) e **um** identificador: `pedido_id` (inteiro) ou, sem id numérico, `order_number` (texto). | Só com `NOSTFOOD_SEND_STATUS=true`, quando o KDS inicia o preparo ou quando todos os itens ficam prontos. Pedido de teste nunca envia. |

Travas da função de saída:

- `NOSTFOOD_SEND_STATUS` diferente de `true`: o POST é recusado dentro da própria função de saída, e não só por quem a chama.
- `NOSTFOOD_BASE_URL` precisa começar com `https://`, porque a chave vai no cabeçalho.
- Redirecionamentos não são seguidos, para que a chave não vá para outro endereço.
- Nunca saem dados de cliente, valores, itens, cardápio, estoque, usuários nem nada do Gestor.
  Não existem chamadas para criar produto, usuário ou pedido na NostFood.

### Entradas: rotas em `/api/integrations/nostfood`

O superadmin passa em todas as rotas com login (regra geral do `require_role`).
Sem token, a resposta é 403 `Not authenticated` (padrão do FastAPI 0.110). Com token
inválido, a resposta é 401. Nos dois casos o corpo tem só `detail`.

| Método | Rota | Quem pode | O que faz |
|---|---|---|---|
| POST | `/webhook` | **Sem login**: só com HMAC válido (`X-NostFood-Signature`, `NOSTFOOD_WEBHOOK_SECRET`) | Recebe eventos de pedido. Corpo de até 256 KB (413 acima disso). Responde só `{"ok": true}` ou um erro com `detail`, sem nenhum dado do Gestor. Outros métodos: 405. |
| GET | `/status` | admin | Estado da integração (ligada, tem chave, último polling). Nunca mostra a chave nem o segredo. |
| POST | `/simular` | admin | Cria pedido de teste só no Gestor. Não chama a NostFood. |
| DELETE | `/testes` | admin | Apaga os pedidos de teste. |
| POST | `/pedidos/{order_id}/nao-recebido` | admin | Marca "Não recebido" num pedido a cobrar na entrega. |
| GET | `/produtos-sem-ligacao` | admin | Itens da NostFood sem produto do Gestor. |
| GET | `/ligacoes` | admin | Ligações item da NostFood → produto do Gestor. |
| POST | `/ligar-produto` | admin | Cria ou refaz uma ligação. |
| POST | `/pedidos/{order_id}/observacao` | admin, caixa | Nova observação no pedido (aparece no KDS). |
| POST | `/pedidos/{order_id}/observacao/{obs_id}/ciente` | admin, cozinha, bar | KDS confirma que viu a observação. |
| GET | `/kds/cancelados` | admin, garçom, caixa, cozinha, bar | Pedidos cancelados recentes para o aviso do KDS. Admin e caixa recebem o pedido completo. Cozinha, bar e garçom recebem só o que o KDS usa: código, mesa, primeiro nome do cliente, itens (nome, quantidade, tipo, status), motivo, horário e autor do cancelamento. Não recebem telefone, endereço, troco, pagamento nem valores. |
| POST | `/pedidos/{order_id}/cancelamento/ciente` | admin, cozinha, bar | KDS confirma que viu o cancelamento. Cozinha e bar recebem a mesma visão reduzida do `/kds/cancelados`. |
| GET | `/perdas` | admin | Perdas de estoque por cancelamento depois do preparo. |

Um teste (`test_every_route_is_listed_here`) falha se uma rota nova entrar na integração
sem ser adicionada a esta lista de rotas protegidas.

### Outras rotas sem login no Gestor (fora da integração)

Estas rotas não fazem parte da NostFood, mas qualquer um na internet pode chamá-las:
`/health`, `/api/health`, `/api/ping`, `/api/`, `/api/auth/login`, `/api/login` e as rotas
do cardápio público do cliente (`/api/public/config`, `/api/public/cardapio`,
`/api/public/cardapio/categorias`, `POST /api/public/pedido` e
`/api/public/pedido/{codigo}`). O cardápio público não expõe o custo dos produtos.

## Como os pedidos chegam

```mermaid
sequenceDiagram
    participant NF as NostFood
    participant G as Gestor (/api/integrations/nostfood)
    participant DB as MongoDB
    participant KDS as Cozinha/Bar

    NF->>G: POST /webhook (X-NostFood-Signature)
    G->>G: confere HMAC-SHA256 do corpo
    G->>DB: grava evento (event_id único, TTL 30 dias)
    G-->>NF: 200 {ok: true}
    G->>NF: GET pedidos.php (se o evento não trouxer o pedido)
    G->>DB: cria o pedido (nunca duplica)
    G-->>KDS: kitchen_update / bar_update / new_online_order
    loop a cada 90 s
        G->>NF: GET pedidos.php?data_inicio=hoje&data_fim=hoje
        G->>DB: cria o que faltou, espelha status e cancelamentos
    end
    KDS->>G: item em preparo / pronto
    G->>NF: POST atualizar-pedido.php (só com NOSTFOOD_SEND_STATUS=true)
```

- **Webhook** `POST /api/integrations/nostfood/webhook`: recusa se a integração estiver desligada ou sem segredo (503) e se a assinatura não bater (401). Assinatura: `X-NostFood-Signature: sha256=<HMAC-SHA256 do corpo bruto>`. Como a documentação da NostFood não diz se vem em hex ou base64, as duas formas são aceitas. Corpo acima de 256 KB: 413. Evento repetido (mesmo `event_id`) responde só `{"ok": true}`, igual a um evento novo, sem processar de novo. O processamento roda em segundo plano depois da resposta.
- **Polling de segurança:** a cada `NOSTFOOD_POLL_SECONDS` (padrão 90, mínimo 30), busca os pedidos do dia no horário de São Paulo e, na virada da meia-noite, também os do dia anterior. Pagina por `limit=1000` e `offset` enquanto `has_more` for verdadeiro.
- **Sem duplicar:** índice único em `orders` por (`external_source`, `external_id`), trava por pedido e checagem dupla. Webhook e polling podem trazer o mesmo pedido sem problema.
- **Data de ativação:** na primeira vez que liga, grava `nostfood_enabled_at`. Pedidos criados na NostFood antes disso são ignorados. Pedido sem data de criação nunca é importado no primeiro polling.

As chamadas para a NostFood estão na tabela de saídas acima.
Não existe consulta de um pedido só: para achar um pedido, o Gestor busca o dia (e o anterior) e procura pelo `id` ou `order_number`.

## Formato real do pedido (`pedidos.php`)

No formato real, `items` **não é uma lista**: é um objeto. Os itens ficam em `items.itens_detalhados` e os valores em `items.totais`. Os campos `subtotal`, `delivery` e `total` do topo vêm como texto e são usados só como reserva.

Pedido da 99Food (dados do cliente, ids e horários trocados; estrutura e valores reais):

```json
{
  "id": 900001,
  "order_number": "99-5764700000000000001",
  "customer_name": "Cliente Fixture",
  "customer_phone": "16900000000",
  "customer_address": "Rua Fictícia",
  "customer_number": "1",
  "customer_neighborhood": "Bairro Teste",
  "customer_city": "Cidade Teste",
  "customer_state": "SP",
  "customer_cep": "00000-000",
  "customer_complemento": "",
  "items": {
    "totais": {
      "subtotal_bruto": 122.32, "subtotal": 122.32,
      "desconto_itens": 46.01, "desconto_entrega": 6.88, "desconto": 52.89,
      "entrega_bruta": 6.88, "entrega_liquida": 0, "delivery": 6.88,
      "taxa_servico": 4.2, "acrescimo": 4.2,
      "total_liquido": 80.51, "total": 80.51
    },
    "other_fees": {"service_price": 4.2, "coupon_discount": 28.89, "total_tip_money": 0, "small_order_price": 0},
    "other_fees_raw": {"service_price": 420, "coupon_discount": 2889, "total_tip_money": 0, "small_order_price": 0},
    "sponsorship_values": {"total_discount": 52.89, "shop_subside_price": 26.83, "platform_subside_price": 26.06},
    "promotions_raw": [
      {"promo_type": 2, "promo_discount": 2201, "shop_subside_price": 2201},
      {"promo_type": 11, "promo_discount": 2400, "shop_subside_price": 0},
      {"promo_type": 3, "promo_discount": 688, "shop_subside_price": 482}
    ],
    "food99_order_id": "5764700000000000001",
    "itens_detalhados": [
      {"nome": "Combo Amós", "preco": 49.5, "adicionais": [], "observacao": "", "produto_id": "", "quantidade": 1},
      {"nome": "Salomão - O Principe do Sabor", "preco": 36.41, "adicionais": [], "observacao": "", "produto_id": "", "quantidade": 2}
    ],
    "payment_raw": {"pay_type": 1, "pay_method": 1, "pay_channel": 212},
    "delivered_by": "MERCHANT", "delivery_type": 2, "handover_code": "0000", "locator": "FIXTURE"
  },
  "subtotal": "122.32",
  "delivery": "6.88",
  "total": "80.51",
  "status": "saiu_entrega",
  "payment_method": "pago_online",
  "created_at": "2026-11-24 12:00:00",
  "hora_aprovado": "2026-11-24 12:00:00",
  "hora_confirmado": "2026-11-24 12:00:00",
  "hora_preparado": null, "hora_pronto": null, "hora_enviado": null
}
```

Pedido feito direto na NostFood é mais simples: `items.totais` tem só `total`, `entrega` (em vez de `delivery`) e `subtotal`, e não há bloco de plataforma.

### Itens (`items.itens_detalhados`)

| Campo NostFood | No Gestor (`orders.items[]`) |
|---|---|
| `nome` | `external_name`; vira `product_name` se não houver ligação |
| `quantidade` | `quantity` (mínimo 1) |
| `preco` (+ adicionais) | `unit_price`. Se o item trouxer `subtotal`/`total`, usa total ÷ quantidade |
| `produto_id` | `external_item_id`. No formato real vem **vazio**: a ligação com o produto do Gestor cai no **nome** |
| `observacao` | `observation` e o começo de `notes` |
| `adicionais` (lista ou grupos com `opcoes`) | `addons` e "Adicionais: ..." em `notes` |

### Valores (`items.totais`)

O Gestor lê **primeiro** `items.totais` e, se faltar, o topo do pedido:

| No Gestor (`orders`) | Origem |
|---|---|
| `subtotal` | `totais.subtotal` → `subtotal` do topo → soma dos itens |
| `delivery_fee` | `totais.delivery` ou `totais.entrega` → `delivery`, `delivery_fee`, `taxa_entrega` ou `frete` do topo |
| `total` | `totais.total` → `total` do topo → subtotal + entrega |
| `service_fee`, `service_fee_percentage` | **sempre 0**: delivery não tem os 10% do salão |

Valores em texto são aceitos com vírgula ou ponto e com "R$".

### Descontos da loja e da plataforma, taxa de serviço

Os blocos financeiros `totais`, `other_fees`, `sponsorship_values` e `promotions_raw` são guardados **como vieram** em `orders.external_financials`. Deles saem os campos de exibição do pedido, que o caixa mostra para a conta fechar (subtotal − descontos + entrega + taxa de serviço = total):

| Campo em `orders` | Origem |
|---|---|
| `discount_total` | `sponsorship_values.total_discount` → soma de `promotions_raw[].promo_discount` (centavos) → `totais.desconto` |
| `discount_store` | `sponsorship_values.shop_subside_price` → soma de `promotions_raw[].shop_subside_price` |
| `discount_platform` | `sponsorship_values.platform_subside_price` → `discount_total − discount_store` |
| `platform_service_fee` | `totais.taxa_servico` |
| `delivery_fee_gross`, `delivery_fee_net` | `totais.entrega_bruta`, `totais.entrega_liquida` (sem eles, `delivery_fee`) |

São **só exibição e registro**: não entram no caixa, no repasse nem nos relatórios, que continuam usando `total`. A API da NostFood não manda a comissão nem o valor do repasse.

Leitura do exemplo acima (interpretação a confirmar com a NostFood):

| Campo | Valor | Significado provável |
|---|---|---|
| `totais.subtotal_bruto` | 122,32 | Itens a preço cheio (49,50 + 2 × 36,41) |
| `totais.desconto_itens` | 46,01 | Desconto nos itens |
| `totais.desconto_entrega` | 6,88 | Entrega grátis para o cliente (`entrega_liquida` = 0) |
| `totais.desconto` = `sponsorship_values.total_discount` | 52,89 | Desconto total que o cliente recebeu |
| `sponsorship_values.shop_subside_price` | 26,83 | Parte do desconto **paga pela loja** (soma dos `shop_subside_price` de `promotions_raw`: 22,01 + 0 + 4,82) |
| `sponsorship_values.platform_subside_price` | 26,06 | Parte do desconto **paga pela plataforma** |
| `totais.taxa_servico` = `acrescimo` = `other_fees.service_price` | 4,20 | Taxa de serviço da plataforma cobrada do cliente. **Não** é a taxa de 10% do salão |
| `other_fees.coupon_discount` | 28,89 | Cupom aplicado (parte do desconto total) |
| `totais.total` = `total_liquido` | 80,51 | O que o cliente pagou: 122,32 + 6,88 − 52,89 + 4,20 |
| `*_raw` | centavos | Mesmos valores em centavos inteiros |

O `total` do pedido no Gestor é o **pago pelo cliente** (80,51), não o que a loja vai receber. A parte do desconto paga pela loja e a comissão da plataforma ainda não são descontadas em lugar nenhum.

### Plataforma de origem

O pedido no Gestor fica sempre com `platform = "nostfood"` (caixa e relatórios agrupam por NostFood). A plataforma real vai em `external_origin_platform`:

- algum campo com `food99` ou `99food` (ex.: `items.food99_order_id`) → `99food`;
- algum campo com `ifood` (ex.: `items.ifood_order_id`) → `ifood`;
- senão, `platform`/`plataforma`/`origem`/`canal` declarado;
- senão, `order_number` começando com `99-` → `99food`;
- senão, `null` (pedido direto na NostFood).

O id do pedido na plataforma (`food99_order_id` ou `ifood_order_id`) fica em `external_platform_order_id`.

### Código curto do pedido

O código que o app da plataforma mostra (ex.: `252001` na 99) fica em `external_display_code`: vem de `items.order_index` (ou `display_id`/`short_id`/`codigo`); em pedido direto na NostFood, é o próprio `order_number` quando curto e sem hífen. Telas, impressão, avisos do KDS e a busca do caixa mostram `99 #252001`, `iFood #…` ou `NostFood #…`. Sem código curto, mostram `#<order_number>`. O id longo (`99-5764…`) fica só para a API.

### Outros campos

| Campo NostFood | No Gestor |
|---|---|
| `id` | `external_id` (texto) |
| `order_number` | `external_order_number` |
| `status` | `nostfood_status` |
| `customer_name`, `customer_phone` | `customer_name`, `customer_phone` |
| `customer_address`, `customer_number`, `customer_complemento`, `customer_neighborhood`, `customer_city`, `customer_state`, `customer_cep` | `customer_address` (objeto) e `address` (texto) |
| `latitude`, `longitude` | `latitude`, `longitude` |
| `payment_method` | `payment_method` e `payment_status` |
| `created_at` (`AAAA-MM-DD HH:MM:SS`, horário de São Paulo) | `external_created_at` |

O código também aceita os nomes alternativos em português (`itens`, `cliente.nome`, `endereco.rua`, `forma_pagamento`, `taxa_entrega`...), para o caso de a NostFood mudar o formato.

## Regras no Gestor

### Status

| Status na NostFood | Ao importar |
|---|---|
| novo, confirmado ou outro | Itens `pending`: aparece como novo no KDS, com som |
| `em_preparo`, `preparando` | Itens `preparing` |
| `pronto`, `saiu_entrega`, `enviado`, `entregue` | Itens `delivered`, vai direto para o histórico (sem som), com baixa de estoque |
| `cancelado`, `rejeitado` (e variações em inglês) | Cancelamento |

**Status de volta para a NostFood:** quando a cozinha põe algum item em preparo, o Gestor envia `em_preparo`; quando todos os itens ficam prontos, envia `pronto`. Só envia com `NOSTFOOD_SEND_STATUS=true`; desligado (padrão), só escreve no log o que teria enviado. O status enviado é anotado antes, e o `order.updated` que volta da NostFood é ignorado (sem laço). Falha no envio fica em `nostfood_sync_errors` do pedido.

**Status vindo da NostFood para um pedido que já existe** (webhook ou polling): o Gestor sempre guarda `nostfood_status`. Se lá ficou `pronto`, `saiu_entrega`, `enviado` ou `entregue` (e não é eco de um status que o próprio Gestor enviou), os itens ainda abertos são dados como entregues, com baixa de estoque, e o pedido sai do KDS. Se for `entregue` e pago online, o pedido fecha como repasse pendente. Cobrar na entrega continua aberto até o caixa receber. Pedido de teste, cancelado ou já fechado não muda.

### Pagamento: repasse ou cobrar na entrega

- `pix_online`, `cartao_credito_online`, `cartao_debito_online`, `mercadopago_online`, `pago_online` ou qualquer método terminado em `_online` → `payment_status = "pending_platform"`: repasse da plataforma, **fora da gaveta**.
- Qualquer outro método, ou nenhum → `payment_status = "to_collect"` (cobrar na entrega): o pedido fica aberto e entra no caixa pelo **fechamento normal**, e bloqueia o fechamento do caixa enquanto estiver aberto.
- Pedido entregue e pago online é fechado como repasse pendente (`settlement_status = "pending_platform"`).
- **Não recebido:** se o cliente não pagou na entrega, um admin marca `POST /pedidos/{id}/nao-recebido` com motivo. O pedido fecha fora das vendas e do caixa, e o custo vira **perda** em `stock_losses`.

### Produtos sem ligação

- A ligação NostFood → produto do Gestor fica em `nostfood_product_map`, por id (`id:...`) ou por nome normalizado (`name:...`, sem acento, sem diferença de maiúsculas e espaços).
- Item sem ligação **entra no pedido** e vai para a cozinha com alerta (`nostfood_alert`), mas não baixa estoque (fica com `stock_pending`). Fica listado em `nostfood_unlinked`.
- Ao ligar o produto (`POST /ligar-produto`), os pedidos ainda abertos são corrigidos (estação e estoque).
- **Refazer uma ligação errada:** ligar de novo o mesmo item a outro produto troca o produto nos pedidos abertos. Itens que já tiveram baixa de estoque ficam como estão, e a resposta diz quantos (`kept_stock_deducted`). O caixa mostra `Produto (NostFood: nome)` quando os nomes diferem.

### Estoque

A baixa usa a mesma ficha técnica do salão, mas **nunca trava** o KDS nem o caixa: se falhar, o item fica com `stock_pending` e o motivo, e a operação segue. Pedido de teste nunca mexe em estoque.

### Cancelamento vindo da plataforma

- Item que **ainda não começou**: devolve a baixa, se houve.
- Item em preparo, pronto ou entregue: vira **perda** (baixa de estoque e custo em `stock_losses`), não venda.
- O KDS mostra o cancelado até cada tela (cozinha, bar) confirmar que viu, por até 12 horas.
- Cancelamento que chega **antes** do pedido grava uma "lápide" (`nostfood_tombstones`) e o pedido não é criado depois.
- Cancelamento depois de o pedido ser finalizado no Gestor só marca e alerta (`cancelled_after_close`) para conferência manual.

### Pedidos de teste

`POST /simular` cria um pedido falso só no Gestor (`is_test = true`), que nunca chama a NostFood, não mexe em estoque e não entra no caixa. `DELETE /testes` apaga todos os pedidos de teste e o que eles geraram. Webhook e polling nunca criam pedido de teste.

## Tempo real (Socket.IO)

A integração só envia eventos pelas funções por sala do `server.py`. Nenhum evento vai para "todo mundo conectado".

| Evento | Função | Quem recebe |
|---|---|---|
| `kitchen_update`, `bar_update`, `new_online_order` | `emit_orders` | Admin, superadmin e caixa: pedido completo. Cozinha, bar e garçom: só o primeiro nome do cliente, sem telefone, endereço (`address`, `customer_address`, `latitude`, `longitude`) e troco. |
| `order_cancelled`, `order_closed`, `order_observation`, `kds_cancelled` | `emit_staff` | Todos os usuários logados. Levam só ids e a observação. `kds_cancelled` leva só `{order_id}`: cada tela busca o aviso em `/kds/cancelados`, já filtrado pelo perfil. |
| `nostfood_alert`, `stock_updated` | `emit_admins` | Só admin e superadmin. |

O teste `test_nenhum_evento_para_cozinha_ou_bar_leva_telefone_ou_endereco` (`backend/tests/test_socket_dados_pessoais.py`) passa pelos fluxos da NostFood e do salão e confere cada evento que chega a cozinha, bar ou garçom.

## Variáveis de ambiente

| Variável | Padrão | Para quê |
|---|---|---|
| `NOSTFOOD_ENABLED` | `false` | Liga webhook, polling e status de volta |
| `NOSTFOOD_API_KEY` | (vazia) | Chave da API (`X-API-Key`). Sem ela não há polling nem envio de status |
| `NOSTFOOD_WEBHOOK_SECRET` | (vazia) | Segredo do HMAC. Sem ele o webhook é recusado |
| `NOSTFOOD_BASE_URL` | `https://nostfood.com/api/public` | Base da API |
| `NOSTFOOD_POLL_SECONDS` | `90` | Intervalo do polling (mínimo 30) |
| `NOSTFOOD_SEND_STATUS` | `false` | Envia `em_preparo` e `pronto` para a NostFood |

## Coleções novas

`nostfood_events` (eventos do webhook, apagados automaticamente após 30 dias), `nostfood_product_map`, `nostfood_unlinked`, `nostfood_tombstones`, `nostfood_settings` e `stock_losses`. Nenhuma coleção existente foi renomeada. Em `orders`, os pedidos da NostFood ganham `external_*`, `nostfood_*`, `payment_status`, `is_test`, `observations` e os campos de confirmação do KDS.

## Em aberto

- Usar `external_financials` no repasse: valor líquido esperado (total − parte da loja nos descontos − comissão).
- A comissão da plataforma não vem na API.
- Confirmar com a NostFood o significado de `promo_type`, `delivered_by`, `delivery_type` e `payment_raw`.
- Confirmar se a assinatura do webhook vem em hex ou base64.
