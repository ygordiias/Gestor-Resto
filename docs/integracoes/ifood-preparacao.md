# Preparação para homologar com a Merchant API do iFood

Objetivo: integrar o Gestor **direto** com o iFood (sem a NostFood no meio) e passar na homologação.

> **Como ler este documento.** O que está em "O Gestor já tem" foi conferido no código. Tudo que descreve a API do iFood (rotas, prazos, códigos, regras de homologação) é **suposição** a partir de conhecimento geral da Merchant API e está marcado **[confirmar]**. Antes de implementar, confira cada item na documentação oficial em **developer.ifood.com.br** e no Portal do Parceiro. Nenhuma chamada foi feita ao iFood.

## O Gestor já tem

| Recurso | Onde | Situação |
|---|---|---|
| Pedido online na mesma coleção do salão, com `source = "online"` e `platform = "ifood"` | `server.py`, `create_online_order` | `main` |
| Pedido sem os 10% do salão | `service_fee_percentage = 0` | `main` |
| Envio para cozinha e bar em tempo real (`kitchen_update`, `bar_update`, `new_online_order`) | `emit_order_updates` | `main` |
| Status por item no KDS: `pending` → `preparing` → `ready` → `delivered` | `update_item_status` | `main` |
| Finalização sem pagamento no caixa, com repasse pendente (`settlement_status`, `settlement_gross`, `settlement_net`) | `complete_online_order` | `main` |
| Online separado no fechamento do caixa (`online_completed`, `online_open`) | `preview_cash_register`, `close_register` | `main` |
| Baixa de estoque por ficha técnica e devolução no cancelamento | `deduct_stock`, `restore_stock` | `main` |
| Relatório por canal (salão x online) | `GET /api/reports/advanced` | `main` |
| Lançamento **manual** de pedido do iFood pelo caixa | `POST /api/orders/online` | `main` |
| Webhook com HMAC, polling, deduplicação por índice único, trava por pedido | `nostfood_integration.py` | branch `feat/integracao-nostfood` |
| Ligação de produto externo → produto do Gestor, item sem ligação com alerta | idem | branch |
| Status de volta para a plataforma a partir do KDS, sem laço | `on_item_status_changed` | branch |
| Cancelamento vindo da plataforma: devolução ou perda (`stock_losses`), confirmação no KDS, cancelamento antes da criação | `cancel_external` | branch |
| Pedido de teste que nunca chama a plataforma | `/simular` | branch |
| Guarda dos valores financeiros brutos da plataforma | `external_financials` | branch |

A estrutura da integração NostFood serve de molde: um módulo isolado (`ifood_integration.py`), ligado ao `server.py` por ganchos, com `external_source = "ifood"`.

## O que falta

### 1. Autenticação

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Tipo de aplicativo | Aplicativo **centralizado** (uma loja ou rede própria) usa `client_credentials`; aplicativo **distribuído** (software vendido para várias lojas) usa autorização por código de vínculo do lojista **[confirmar]** | Nada. Decidir o tipo: o Gestor hoje atende uma loja, mas é um produto da Tecno Dias |
| Token | `POST /authentication/v1.0/oauth/token` com `clientId` e `clientSecret`; token com validade de algumas horas e renovação antes de expirar **[confirmar rota e validade]** | Nada. Guardar o token só em memória, renovar sozinho, nunca registrar no log |
| Credenciais | `clientId`, `clientSecret` e `merchantId` da loja, emitidos no Portal do Desenvolvedor | Criar variáveis `IFOOD_CLIENT_ID`, `IFOOD_CLIENT_SECRET`, `IFOOD_MERCHANT_ID` (sem valor no código) |
| Ambiente de teste | Loja de teste fornecida pelo iFood para homologação **[confirmar]** | Usar banco de teste e pedidos de teste, como o `/simular` da NostFood |

### 2. Polling de eventos a cada 30 s, com confirmação

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Buscar eventos | `GET /order/v1.0/events:polling` a cada **30 segundos**, com o header `x-polling-merchants` quando houver mais de uma loja **[confirmar]** | O polling da NostFood existe, mas a cada 90 s e buscando pedidos, não eventos |
| Confirmar (ack) | `POST /order/v1.0/events/acknowledgment` com os ids de **todos** os eventos recebidos, inclusive os que o Gestor decidiu ignorar. Evento sem ack volta no próximo polling **[confirmar]** | Nada. Precisa de fila: gravar o evento, confirmar, processar |
| Duplicados | O mesmo evento pode vir mais de uma vez **[confirmar]** | Já resolvido no molde NostFood (índice único por `event_id`) |
| Detalhes do pedido | `GET /order/v1.0/orders/{id}` depois do evento de pedido novo **[confirmar]** | Escrever o normalizador iFood → `orders` |
| Códigos de evento | `PLC` (novo), `CFM` (confirmado), `RTP` (pronto para retirada), `DSP` (despachado), `CON` (concluído), `CAN` (cancelado), além dos eventos de pedido de cancelamento **[confirmar lista completa]** | Mapear cada código para uma ação do Gestor |
| Webhook | O iFood também oferece webhook como alternativa ao polling **[confirmar se é aceito na homologação]** | O molde HMAC da NostFood pode ser reaproveitado |

### 3. Aceitar o pedido

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Confirmar | `POST /order/v1.0/orders/{id}/confirm` **[confirmar]** | Nada. Decidir: confirmar sozinho ao gravar o pedido ou com um botão no caixa |
| Prazo | Pedido não confirmado em poucos minutos é cancelado automaticamente pelo iFood **[confirmar prazo]** | Precisa de alerta sonoro e visual para pedido aguardando aceite |

### 4. Preparo, pronto e despacho

| Etapa | Suposição | Gancho no Gestor |
|---|---|---|
| Início do preparo | `POST /orders/{id}/startPreparation` **[confirmar]** | Primeiro item em `preparing` (o gancho da NostFood já faz isso) |
| Pronto para retirada | `POST /orders/{id}/readyToPickup` (para pedido que o cliente ou o entregador do iFood retira) **[confirmar]** | Todos os itens em `ready` |
| Despacho | `POST /orders/{id}/dispatch` (entrega feita pela loja) **[confirmar]** | **Falta** uma ação "Saiu para entrega" no caixa: hoje não existe esse estado |
| Conclusão | Vem do iFood como evento **[confirmar]** | Fechar como repasse pendente (`complete_online`) |

Também falta: guardar o tipo de entrega (entrega do iFood, entrega própria, retirada), o código de coleta ou de confirmação de entrega e o horário agendado, se houver **[confirmar campos]**.

### 5. Cancelamento

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Motivos | `GET /orders/{id}/cancellationReasons` devolve os códigos permitidos naquele momento **[confirmar]** | Nada. O Gestor hoje aceita motivo em texto livre |
| Loja cancela | `POST /orders/{id}/requestCancellation` com código e descrição **[confirmar]** | Criar botão de cancelamento do pedido iFood usando só os motivos do iFood |
| Cliente pede cancelamento | O iFood envia um pedido de cancelamento e a loja aceita ou recusa dentro de um prazo **[confirmar rotas e prazo]** | Nada. Precisa de alerta no caixa com aceitar/recusar |
| Cancelado pelo iFood | Evento `CAN` **[confirmar]** | Reaproveitar `cancel_external` da NostFood: devolução se não começou, perda se começou |

### 6. Status da loja

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Consultar | `GET /merchant/v1.0/merchants/{id}/status` mostra se a loja está aberta e por quê **[confirmar]** | Nada. Mostrar no caixa e no painel |
| Pausar e retomar | Interrupções: criar e remover pausa temporária **[confirmar rotas]** | Criar botão "Pausar iFood" (ex.: cozinha cheia) |
| Horário | Horário de funcionamento pela API **[confirmar se é exigido]** | `settings.public_config.hours` existe só para o cardápio próprio |
| Manter a loja aberta | O iFood pode fechar a loja que para de fazer polling **[confirmar]** | O polling precisa rodar sempre, com alerta se parar |

### 7. API financeira

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Vendas e repasses | API financeira com vendas, descontos, comissões, taxas e repasses por período **[confirmar versão e rotas]** | Só existe `settlement_gross`. `settlement_net` é sempre `null` e não há rota para registrar o repasse |
| Conciliação | Comparar o repasse recebido com os pedidos concluídos | Criar rotina diária: preencher `settlement_net`, marcar `settlement_status = "settled"` e mostrar diferenças |
| Descontos | Separar o que a loja pagou do que o iFood pagou nas promoções **[confirmar campos]** | Guardar como na NostFood (`external_financials`) e usar no líquido esperado |

### 8. Itens e cardápio

| Item | Suposição | Situação no Gestor |
|---|---|---|
| Ligação do item | O item do pedido traz um código externo (`externalCode`) cadastrado no cardápio do iFood **[confirmar]** | Cadastrar o id do produto do Gestor como código externo no iFood resolve a ligação sem depender do nome |
| Complementos e observações | Itens com opções e observação do cliente **[confirmar formato]** | O normalizador da NostFood já trata adicionais e observação |
| Catálogo pela API | Publicar cardápio e disponibilidade pela API **[confirmar se é exigido na homologação]** | Nada. `is_available` do produto poderia pausar o item no iFood |

## Itens prováveis da homologação

Lista a confirmar com o iFood antes de começar **[confirmar tudo]**:

- [ ] Polling a cada 30 s, sem parar, com ack de todos os eventos.
- [ ] Tratar evento duplicado e fora de ordem.
- [ ] Confirmar pedido dentro do prazo.
- [ ] Mostrar todos os dados do pedido para a equipe: itens, complementos, observações, forma de pagamento, troco, CPF na nota, tipo de entrega e código de coleta.
- [ ] Imprimir o pedido.
- [ ] Informar preparo, pronto e despacho conforme o tipo de entrega.
- [ ] Cancelar só com os motivos do iFood e responder pedidos de cancelamento do cliente.
- [ ] Mostrar e alterar o status da loja.
- [ ] Renovar o token sem cair.
- [ ] Não guardar nem registrar no log mais dados do cliente do que o necessário (veja [../seguranca-lgpd.md](../seguranca-lgpd.md)).

## Proposta de ordem de trabalho

1. Confirmar em developer.ifood.com.br cada item marcado **[confirmar]** e corrigir este documento.
2. Integrar a branch `feat/integracao-nostfood` na `main` (o molde e as coleções de apoio estão nela).
3. Criar `ifood_integration.py` com autenticação e polling + ack, gravando eventos com `event_id` único e TTL.
4. Normalizador do pedido iFood → `orders` com `external_source = "ifood"`, ligação por código externo e testes offline com um pedido real anonimizado.
5. Ações: confirmar, iniciar preparo, pronto, despacho, cancelamento com motivos e resposta ao pedido de cancelamento.
6. Status da loja e pausa.
7. Conciliação financeira: preencher `settlement_net` e relatório de diferenças.
8. Homologação com a loja de teste do iFood.
