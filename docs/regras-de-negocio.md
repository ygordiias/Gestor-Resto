# Regras de negócio

Regras como estão implementadas na `main` (commit `4bf940a`), com o arquivo e a função de onde saem. Onde o comportamento atual difere do que já foi decidido, ou parece um problema, há um **Ponto de atenção**. Esta documentação não muda nada no sistema.

## Comandas físicas (200 a 291)

Fonte: `backend/physical_tabs.py`, `server.py` (`link_physical_tab`, `create_order`, `release_physical_tab`, `refresh_table_after_order`).

- A faixa vale de **200 a 291**, inclusive. Pode ser trocada por `PHYSICAL_TAB_MIN` e `PHYSICAL_TAB_MAX`. Valor inválido (não inteiro, menor que 1 ou máximo menor que mínimo) volta para 200 a 291.
- O frontend lê a faixa em `GET /api/tabs/config`: nenhum número fica fixo na tela.
- No startup, o servidor cadastra as comandas da faixa que ainda não existem. Nunca altera nem apaga uma comanda existente nem o vínculo dela. O script `backend/scripts/criar_comandas_faltantes.py` faz o mesmo sob demanda.
- **Uma comanda, um pedido aberto.** O vínculo com a mesa é atômico: se duas pessoas tentam abrir a mesma comanda ao mesmo tempo, só uma consegue; a outra recebe 409 "Comanda já está em uso".
- Não dá para abrir comanda em mesa em limpeza, nem número fora da faixa.
- Pedido com comanda física nunca é misturado com outra comanda. Para lançar itens, a comanda precisa estar vinculada à mesa antes (409 caso contrário).
- Se a mesa tem alguma comanda física aberta, não dá para lançar item "solto" na mesa: o garçom precisa escolher a comanda (409).
- Ao fechar ou cancelar o pedido, a comanda é liberada (`active_order_id` e `table_id` voltam a vazio).
- A mesa só volta a **disponível** quando não sobra nenhum pedido aberto nela. Também não dá para liberar, reservar ou pôr em limpeza pela tela uma mesa com pedido aberto (409).

**Ponto de atenção:** o evento Socket.IO `request_cleaning` põe a mesa em limpeza sem essa checagem (a rota HTTP `POST /api/tables/{id}/request-cleaning` checa).

## Taxa de serviço (10%) só no salão

Fonte: `server.py` (`Order`, `create_order`, `create_online_order`, `create_public_order`), `financial_modules.py`.

- Pedido do salão nasce com `service_fee_percentage = 10`. `service_fee = subtotal × 10%` e `total = subtotal + service_fee`.
- Pedido online **não tem 10%**: o lançamento manual (iFood, 99Food, outro), o cardápio público e a NostFood gravam `service_fee_percentage = 0`.
- A cada item lançado, cancelado, marcado como cortesia ou com desconto, subtotal, taxa e total são recalculados no servidor (`order_billing.totals`). No fechamento, o valor cobrado é sempre o total gravado no banco, nunca o enviado pelo navegador.
- **Os 10% saem do valor cobrado**: já sem cortesias, descontos manuais e promoções. Delivery, pedido online e NostFood nunca têm 10%. Item cancelado não soma.
- O relatório semanal (`GET /api/reports/service-fees/weekly`) mostra a taxa por dia, de segunda a domingo no horário de São Paulo, só com pedidos do salão fechados, não cancelados, não cortesia e com pagamento conciliado. Ele **não** calcula lucro nem divide a gorjeta entre a equipe.
- O relatório avançado separa `service_fee` das vendas de produto e considera taxa zero no online.

**Ponto de atenção:** não há rota para tirar os 10% de uma comanda do salão (cliente que recusa a taxa).

## Fechamento da comanda

Fonte: `server.py` (`close_order`, `_validate_close_payments`).

- Só admin e caixa fecham. Pedido online não usa esta rota (409): usa "Finalizar pedido online".
- Formas aceitas: `cash` (dinheiro), `pix`, `credit`, `debit`, `voucher` e `card` (antiga, mantida para histórico). Linhas de R$ 0,00 são ignoradas.
- Validação, em centavos, **antes** de gravar qualquer coisa (422 se falhar):
  - total maior que zero exige pelo menos um pagamento;
  - o pago não pode ser menor que o total;
  - **troco só sai do dinheiro**: o que passar do total não pode ser maior que o valor pago em dinheiro.
- Pedido em cortesia/permuta não exige pagamento.
- Fechamento, pagamentos e soma no caixa aberto (`total_sales`) acontecem numa **transação**: tudo ou nada. Se o banco não aceitar transação, a rota devolve 503 e não grava nada. Duplo clique ou outra aba: só o primeiro fecha, o segundo recebe 409.
- **Com pagamento parcial, o fechamento cobra só o que falta** (`total − paid_amount`) e só esse restante soma no `total_sales`. Comanda já zerada fecha sem pagamento novo.
- **O pagamento que fecha entra no pedido igual aos parciais**: soma em `paid_amount` e vai para `partial_payments` com `kind = "final"` (forma, valor já sem o troco, troco, autor, horário e `register_id`). Pedido fechado fica com Falta pagar = 0. Vale para mesa, comanda física e NostFood "Receber na entrega" (mesmo fechamento). Cortesia/permuta fechada não é pagamento e não mexe em `paid_amount`.
- O fechamento é condicionado à `billing_version` lida: se entrou item, desconto, cortesia ou pagamento parcial depois que a tela carregou, devolve 409 e não grava nada.
- Cada pagamento grava `register_id` do caixa aberto, quem lançou e `kind` (`final` no fechamento, `partial` no pagamento parcial).
- Depois de confirmado: baixa de estoque dos itens que ainda não tiveram baixa (cortesia também), libera a comanda e a mesa e avisa as telas.

## Caixa

Fonte: `server.py` (`open_register`, `preview_cash_register`, `close_register`, `register_withdrawal`, `register_deposit`).

- **Um caixa aberto por vez.** O operador gravado é o usuário logado, não um nome digitado.
- Sangria (`withdrawal`) e reforço (`deposit`) exigem caixa aberto e motivo.
- **Dinheiro esperado na gaveta** = valor inicial + dinheiro recebido (já descontado o troco) + reforços − sangrias.
- **Prévia** (`GET /api/cash-register/preview`): só leitura. Considera os pedidos fechados desde a abertura. Cancelados e cortesias ficam fora; pedidos online vão para um bloco separado por plataforma. Pagamento inconsistente vira aviso. Devolve um `preview_token` válido por 10 minutos, preso ao caixa, ao operador e ao conteúdo da prévia.
- **Fechamento** (`POST /api/cash-register/close`) só acontece se:
  - não houver nenhuma comanda do salão aberta;
  - o operador confirmar que imprimiu e conferiu a prévia (`printed_confirmed`);
  - o token da prévia for válido, do mesmo caixa e do mesmo operador;
  - os valores recalculados forem **idênticos** aos da prévia (qualquer venda, pagamento, sangria, reforço ou pedido online novo exige imprimir de novo);
  - não houver comanda sem pagamento ou com pagamento inconsistente.
- O relatório final (`closing_report`) fica gravado no caixa: formas de pagamento, vendas do salão, online por plataforma, total de todos os canais, quantidade de fechadas, canceladas e cortesias, valor das cortesias, troco, sangrias, reforços e dinheiro esperado.
- Prévia e relatório final trazem, **separados**, o concedido nos itens das vendas: `item_promo_total` (com `item_promo_by_name`), `item_discount_total` (desconto manual) e `item_courtesy_total` (cortesia de item). A cortesia do pedido inteiro continua em `courtesy_amount`.
- A prévia mostra em `open_partial_payments` quanto já foi pago em comandas ainda abertas (só informativo: com comanda aberta o caixa não fecha). Esse valor já somou no `total_sales` do caixa na hora do pagamento e entra nas formas de pagamento da conferência quando a comanda fechar.
- Pedidos online abertos **não** impedem o fechamento do caixa.
- Para destravar um caixa com comanda inconsistente há scripts com simulação por padrão: `diagnostico_caixa.py` (só leitura), `corrigir_comandas_caixa.py` e `ajustar_excesso_pagamento.py`.

## Repasse x caixa (pedidos online)

Fonte: `server.py` (`create_online_order`, `create_public_order`, `complete_online_order`, `preview_cash_register`, `close_register`).

O dinheiro do pedido online **não entra na gaveta**: vem depois, por repasse da plataforma.

- Pedidos online ficam na mesma coleção `orders`, com `source = "online"` e `platform`/`origin` (`ifood`, `99food`, `other` ou `web` para o cardápio público).
- O caixa finaliza com `POST /api/orders/{id}/complete-online`, que:
  - recusa pedido cancelado, cortesia ou que já tenha pagamento no caixa;
  - dá baixa no estoque dos itens;
  - fecha o pedido com `settlement_status = "pending_platform"`, `settlement_gross = total` e `settlement_net = null`.
- No caixa, o online aparece separado (`online_completed` e `online_open` por plataforma) e soma só no `gross_total_all_channels`. Não entra em `total_sales` nem no dinheiro esperado.
- O relatório avançado avisa que valor online é "pedido concluído", não "repasse recebido".

**Pontos de atenção:**
- Não existe rota para registrar o repasse recebido (`settlement_net` fica sempre `null`) nem conciliação com o extrato das plataformas.
- No cardápio público o cliente escolhe Pix, cartão ou dinheiro "na entrega", mas o pedido sempre é finalizado como repasse pendente. Se o motoboy recebe em dinheiro, esse valor não passa pelo caixa. A branch `feat/integracao-nostfood` trata isso para a NostFood ("cobrar na entrega" entra pelo fechamento normal e "Não recebido" vira perda).
- `POST /api/public/pedido` usa o preço que vem do navegador (`items[].price`), sem conferir com o cadastro do produto.

## Cancelamento

Fonte: `server.py` (`cancel_order_item`, `cancel_order`, `quick_cancel_order`).

| Tipo | Rota | Quem autoriza | Regra de estoque |
|---|---|---|---|
| Item (total ou parcial) | `PATCH /api/orders/{id}/item/{item}/cancel` | E-mail e senha de admin/superadmin ativo no próprio pedido, mais motivo | Se o item ainda não teve baixa, nada a devolver. Se já teve, o operador escolhe: `restore_stock = true` devolve só a quantidade cancelada; `false` mantém a baixa (perda) |
| Comanda inteira | `PATCH /api/orders/{id}/cancel` | E-mail e senha de admin/superadmin, mais motivo | Itens sem baixa nunca terão baixa. Itens já entregues **não** são devolvidos |
| Rápido | `POST /api/orders/{id}/cancel-quick` | Perfil admin | Só se todos os itens ainda estão `pending` (nenhum entrou em preparo), então não há baixa |

- Só pedido **aberto** pode ser cancelado: comanda fechada é somente leitura.
- Unidade já paga (pagamento parcial por itens) não é cancelada, e a comanda com qualquer valor pago não é cancelada nem vira cortesia/permuta inteira: estorne o pagamento antes (409). O total nunca fica abaixo do que já foi pago.
- Cancelamento parcial divide a linha: a original fica com a quantidade restante e uma nova linha `cancelled` guarda a parte cancelada, com motivo, preço original, quem autorizou, quem operou, data e se o estoque foi devolvido.
- Cancelamento de comanda inteira grava `cancelled_by_*` (admin que autorizou), `cancelled_by_cashier_*` (quem operou) e `cancellation_reason`, e libera comanda e mesa.
- Pedido cancelado fica fora das vendas do caixa (contado em `cancelled_orders`), da taxa semanal e do relatório avançado.

**Pontos de atenção:**
- O cancelamento rápido não pede motivo nem grava quem cancelou.
- `GET /api/reports/sales`, `GET /api/reports/profit` e `GET /api/reports/sales-by-table` **contam pedidos cancelados** (estão fechados). A correção de `sales` e `profit` está na branch `feat/integracao-nostfood` (commit `f534d3b`).

## Cortesia

Fonte: `order_billing.py` (`mark_courtesy`, `unmark_courtesy`, `merge_back`), `server.py` (`mark_item_courtesy`).

- **Cortesia de item:** admin ou caixa, com motivo obrigatório, em comanda aberta. O preço vai a zero e os totais são recalculados (os 10% caem junto). O item **continua consumindo estoque**.
- **Por quantidade:** `quantity` escolhe quantas unidades. Em 3 lanches, marcar 1 divide a linha em 2 cobrados + 1 cortesia (a linha nova guarda `split_from`). Sem `quantity`, vale a linha inteira.
- Grava `courtesy_original_price` (o preço que seria cobrado), `courtesy_reason`, `courtesy_by_id/name` e `courtesy_at`.
- **Desmarcar** devolve o preço guardado (regra do PR #8; sem preço guardado, usa o cadastro) e junta a linha de volta na de origem quando as duas ficaram iguais (2 + 1 volta a 3).
- Item com desconto manual que vira cortesia: o desconto sai e a cortesia guarda o preço sem ele (o cheio, ou o da promoção).
- Unidade já paga não vira cortesia.
- Cortesia de item tem total próprio no pedido (`item_courtesy_total`), separado do desconto e da promoção. O relatório avançado não conta item em cortesia nos produtos mais vendidos.

## Desconto por item

Fonte: `order_billing.py` (`apply_discount`, `remove_discount`), `server.py` (`apply_item_discount`, `remove_item_discount`).

- `PATCH /api/orders/{id}/item/{item}/discount` com `type` (`percent` ou `value`, que é R$ por unidade), `value`, `reason` (obrigatório) e `quantity` opcional (divide a linha como na cortesia). Só comanda/mesa do salão aberta.
- **Caixa dá até 10%.** Acima disso, só admin: admin logado, ou e-mail e senha de um admin no próprio pedido (`admin_email`, `admin_password`). O item grava quem deu (`discount_by_*`), quando (`discount_at`), o % equivalente e quem autorizou (`discount_approved_by_*`).
- 100% ou mais é recusado: isso é cortesia.
- `DELETE` na mesma rota tira o desconto (volta ao preço cheio, ou ao da promoção) e junta a linha de volta. Linha com unidade paga não perde o desconto sem estorno.
- `unit_price` é sempre o preço **cobrado**; o preço cheio fica em `discount_original_price`. Total próprio no pedido: `item_discount_total`.

## Pagamento parcial

Fonte: `order_billing.py` (`items_share_cents`, `settle_change`), `server.py` (`create_partial_payment`, `reverse_partial_payment`).

- `POST /api/orders/{id}/partial-payments`: recebe **parte** da conta, por valor (`amount`) ou por itens (`items: [{item_id, quantity}]`, valor dos itens + 10%), em uma ou várias formas (`payments`). Só salão, com caixa aberto, valor maior que zero e no máximo o que falta pagar. As formas seguem a regra do fechamento (troco só do dinheiro); o troco sai da linha em dinheiro, então os pagamentos gravados somam exatamente o valor recebido.
- A comanda fica aberta com `paid_amount` ("Pago") e "Falta pagar" (`total − paid_amount`) até zerar. Cada pagamento entra em `partial_payments` do pedido e em `db.payments` (`kind = "partial"`, forma, valor, autor, horário e `register_id`) e soma no `total_sales` do caixa **na hora**, tudo numa transação.
- Por itens: a unidade paga fica em `paid_quantity` e não pode ser paga de novo, cancelada, nem receber desconto ou cortesia. Os últimos itens levam o resto exato (sem sobrar centavo do arredondamento dos 10%).
- **Estorno** (`POST .../partial-payments/{pid}/reverse`): só admin (logado ou com credenciais), motivo obrigatório, só com a comanda aberta. Os pagamentos saem de `db.payments` para `db.payment_reversals` (com motivo, autor e horário), o valor sai do `total_sales` e do `paid_amount`, e as unidades pagas voltam a ficar livres. A entrada no pedido fica marcada `reversed` (histórico).
- Mesa com várias comandas: cada comanda tem seu próprio pago e falta pagar.
- Toda mudança de cobrança (item novo, cortesia, desconto, cancelamento de item, parcial, estorno, fechamento) grava condicionada à `billing_version` do pedido: se outra pessoa mudou a comanda no meio, devolve 409 e nada é gravado.

## Promoção gerencial

Fonte: `promotions.py`, `server.py` (`/api/promotions`, `_apply_launch_promotions`, `promotions_report`).

- **Só admin** cria, edita, liga e desliga (Configurações › Promoções). Campos: nome, desconto em % ou R$ por unidade, o que pega (categorias e/ou produtos), período (início e fim, inclusive), opcionalmente dias da semana e faixa de horário (pode passar da meia-noite: 01h de quarta ainda é a faixa de terça), e canais: salão, balcão (pedido "Outro" lançado no caixa) e cardápio próprio.
- **Nunca vale para NostFood, iFood ou 99:** o preço vem da plataforma.
- Vale para o item **no lançamento**: o item guarda `promo_original_price`, `promo_price` e `promo_name`, e mantém o desconto mesmo que a promoção acabe ou seja desligada depois. Editar a promoção também não muda item já lançado.
- Horário e dia da semana são os do restaurante (America/Sao_Paulo).
- Mais de uma promoção para o mesmo item: vale a de **maior desconto** (não acumula).
- **Desconto manual não acumula com promoção:** se a promoção já dá desconto igual ou maior, o desconto é recusado com aviso (vale a promoção); se o manual for maior, ele substitui a promoção na linha, com aviso. Tirar o desconto volta ao preço da promoção.
- Ligar/desligar não apaga nada: cada criação, edição e mudança de status vai para o `history` da promoção. Status: ativa (dentro do período), agendada, encerrada ou desligada.
- Os 10% são calculados sobre o valor cobrado, já com a promoção.
- Relatórios: total próprio no pedido (`item_promo_total`), separado do desconto manual e da cortesia; `GET /api/reports/promotions?start=&end=` dá o total concedido por promoção e por dia.

## Cortesia ou permuta do pedido inteiro

Fonte: `server.py` (`mark_order_comp`).

- `PATCH /api/orders/{id}/comp` com `is_comp` e `comp_reason` (obrigatório). Admin ou caixa.
- **Cortesia** e **permuta** usam a mesma marca (`is_comp`). A diferença fica só no texto do motivo (ex.: "Permuta: fotos do evento").
- Pedido `is_comp` não entra no faturamento: fica fora de `total_sales`, das vendas do relatório, da taxa semanal e do relatório avançado. No fechamento do caixa aparece em `courtesy_orders` e `courtesy_amount`.
- Não exige pagamento no fechamento, mas o estoque é baixado normalmente.
- Comanda com pagamento parcial não vira cortesia/permuta inteira: estorne antes.

**Ponto de atenção:** a rota não confere se o pedido está aberto. Marcar como cortesia um pedido já fechado muda relatórios do passado.

## Estoque

Fonte: `server.py` (`validate_stock`, `deduct_stock`, `restore_stock`, `check_stock_alert`, `create_production`).

### Tipos de item

`stock_type`: `raw_material` (matéria-prima), `semi_finished` (semiacabado, ex.: hambúrguer porcionado) e `finished_product` (produto pronto, ex.: lata de refrigerante). O item pode ter `name` próprio ou apontar para um produto do cardápio (`product_id`, modelo antigo). Unidades: `unit`, `kg`, `liter`, `gram`.

### Quando a baixa acontece

A baixa acontece **uma vez por item** (marca `stock_deducted`), no primeiro destes eventos:

1. o item muda para `delivered` no KDS;
2. a comanda é fechada no caixa (itens que ainda não tiveram baixa, inclusive cortesia);
3. o pedido online é finalizado.

Itens cancelados antes da baixa nunca têm baixa.

### Como a baixa é calculada

- Produto **com receita** (`recipes`): baixa de cada ingrediente, quantidade da receita × quantidade vendida, somando ingredientes repetidos. Todos os saldos são conferidos antes; se faltar algum, nenhum é baixado.
- Produto **sem receita**, mas com item de estoque ligado por `product_id`: baixa do próprio item.
- Produto sem receita e sem estoque: nada acontece.

### Saldo insuficiente (estado atual na `main`)

- Ao **lançar** o pedido, `validate_stock` recusa (400) se o item de estoque ligado direto ao produto estiver zerado ou com menos que o pedido. Produtos controlados só por receita não são conferidos nesse momento.
- No **KDS**, marcar `delivered` com ingrediente faltando devolve erro 400 e o status não muda.
- No **fechamento da comanda**, a falta de saldo só gera aviso no log: a comanda fecha, mas o item fica sem baixa e sem registro visível.

**Decisão já tomada (PR #5, `fix/estoque-cmv`, ainda não integrado):** a falta de saldo **nunca bloqueia** a baixa; o estoque pode ficar negativo e a falha é registrada e mostrada na tela de Estoque. O aviso ao lançar só avisa. A conversão de unidade só vale quando a receita informa a unidade. As respostas de CMV mantêm o formato e só ganham campos novos. Fica para depois: o mesmo problema de unidade nas receitas de produção.

### Alertas

- Quando um item fica **no mínimo ou abaixo** (`min_quantity`, padrão 5), o servidor emite `stock_alert` para as telas e monta uma mensagem de WhatsApp para o administrador. O envio ainda **não está integrado**: a mensagem só vai para o log.
- `GET /api/stock/risk-alerts` compara o saldo com o consumo médio dos últimos 7 dias.

### Produção

- `POST /api/productions` baixa os ingredientes e soma a quantidade produzida no item de saída. Por fórmula (`production_recipes`: rendimento × lotes) ou informando os ingredientes direto.
- Aqui a falta de saldo **bloqueia** (400): nada é baixado.
- O custo unitário do item produzido vira o **custo médio ponderado**: (saldo antigo × custo antigo + custo dos ingredientes) ÷ novo saldo.

## CMV

Fonte: `server.py` (`_compute_recipe_cost`, `get_product_cmv`, `cmv_report`).

- **Custo do produto** = soma de (quantidade do ingrediente na receita × `unit_cost` do item de estoque).
- **Lucro** = preço de venda − custo. **Margem** = lucro ÷ preço × 100.
- `GET /api/cmv/report` lista todos os produtos com `has_recipe`.
- Na `main` não há conversão de unidade: a quantidade da receita precisa estar na **mesma unidade** do item de estoque (ex.: estoque em kg, receita em kg).
- A **ficha técnica** (`technical_sheets`, modo de montagem) é separada da **receita de custo** (`recipes`). Só a receita entra no CMV e na baixa.

**Pontos de atenção:**
- Produto sem receita aparece com custo zero e margem de 100%.
- `GET /api/reports/profit` não usa o CMV: estima custo fixo de 35% das vendas.

## Crédito de funcionários

Fonte: `financial_modules.py`.

- Consumo a prazo, fora da gaveta. Não é pagamento do caixa nem comanda do salão, **não** baixa estoque e não vai para cozinha ou bar (V1).
- Cada funcionário tem limite mensal e desconto percentual. O mês segue o horário de São Paulo.
- Consumo acima do limite é recusado. Saldo em aberto de mês anterior bloqueia novos consumos até o acerto.
- O acerto é manual, com observação obrigatória. O sistema **não** desconta do salário.
- Estorno de consumo preserva o histórico. Lançamentos são idempotentes pelo `request_id` (duplo clique não lança duas vezes).

## Pedidos online pelo cardápio público

Fonte: `server.py` (`create_public_order`, `generate_order_code`).

- Código sequencial `EM-0001`, `EM-0002`...
- Entrega exige endereço. A taxa de entrega vem de `settings.public_config.delivery_fee` (padrão R$ 5,00). Sem 10%.
- O pedido vai direto para cozinha e bar e avisa o caixa (`new_online_order`).
- O cliente acompanha pelo código (`GET /api/public/pedido/{codigo}`), que mostra itens, status e total, sem nome, telefone ou endereço.

## Notas fiscais

- `POST /api/invoices` só **registra** a nota com status `mock`: não há emissor fiscal integrado (NF-e/NFC-e).
- O histórico (`/api/invoices/history`) busca o que existe no banco e não devolve o CPF.
