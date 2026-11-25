# Integração NostFood (iFood / 99)

Código: `backend/nostfood_integration.py`. Testes: `backend/tests/test_nostfood_integration.py`
e `backend/tests/test_nostfood_security.py`.

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
| GET | `/kds/cancelados` | admin, garçom, caixa, cozinha, bar | Pedidos cancelados recentes para o aviso do KDS. |
| POST | `/pedidos/{order_id}/cancelamento/ciente` | admin, cozinha, bar | KDS confirma que viu o cancelamento. |
| GET | `/perdas` | admin | Perdas de estoque por cancelamento depois do preparo. |

Um teste (`test_every_route_is_listed_here`) falha se uma rota nova entrar na integração
sem ser adicionada a esta lista de rotas protegidas.

### Outras rotas sem login no Gestor (fora da integração)

Estas rotas não fazem parte da NostFood, mas qualquer um na internet pode chamá-las:
`/health`, `/api/health`, `/api/ping`, `/api/`, `/api/auth/login`, `/api/login` e as rotas
do cardápio público do cliente (`/api/public/config`, `/api/public/cardapio`,
`/api/public/cardapio/categorias`, `POST /api/public/pedido` e
`/api/public/pedido/{codigo}`). O cardápio público não expõe o custo dos produtos.
