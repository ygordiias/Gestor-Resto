// Cobrança no caixa: leitura dos campos que o servidor grava (order_billing.py e
// promotions.py). O servidor é quem decide preço, promoção e totais; aqui só
// mostramos. Valores em centavos para não errar no arredondamento.

export const CASHIER_MAX_DISCOUNT_PCT = 10;

const cents = (value) => Math.round(Number(value || 0) * 100);
const money = (c) => Math.round(c) / 100;

export const isCancelled = (item) => item?.status === 'cancelled';
export const hasPromo = (item) => Boolean(item?.promo_id) && item?.promo_price != null;
export const hasDiscount = (item) => item?.discount_original_price != null && !item?.is_courtesy;
export const paidQty = (item) => Number(item?.paid_quantity || 0);
export const freeQty = (item) => Number(item?.quantity || 0) - paidQty(item);

// Promoção ativa na linha (um desconto manual maior a substitui).
export const promoActive = (item) => hasPromo(item) && item.discount_original_price == null;

// Preço cheio por unidade (antes de promoção e desconto).
export const fullPrice = (item) => {
  if (hasPromo(item)) return Number(item.promo_original_price || 0);
  if (item?.discount_original_price != null) return Number(item.discount_original_price);
  if (item?.is_courtesy && item?.courtesy_original_price != null) return Number(item.courtesy_original_price);
  return Number(item?.unit_price || 0);
};

export const lineTotal = (item) => money(cents(item?.unit_price) * Number(item?.quantity || 0));

export const promoLabel = (item) => `Promoção: ${item?.promo_name || ''}`;

// Resumo da conta. Os totais vêm do servidor (campos do pedido).
export function orderSummary(order) {
  if (!order) return null;
  const total = Number(order.total || 0);
  const paid = Number(order.paid_amount || 0);
  return {
    subtotal: Number(order.subtotal || 0),
    discount: Number(order.item_discount_total || 0),
    courtesy: Number(order.item_courtesy_total || 0),
    promo: Number(order.item_promo_total || 0),
    serviceFee: Number(order.service_fee || 0),
    servicePct: order.service_fee_percentage,
    total,
    paid,
    remaining: money(Math.max(0, cents(total) - cents(paid))),
    partials: (order.partial_payments || []),
  };
}

// Prévia (só para a tela de lançamento): a promoção de maior desconto que vale
// para o produto agora. O servidor aplica de novo ao gravar.
export function bestPromoFor(promos, product, price) {
  if (!product || !promos?.length) return null;
  const priceC = cents(price);
  let best = null;
  for (const promo of promos) {
    const covers = (promo.product_ids || []).includes(product.id)
      || (product.category_id && (promo.category_ids || []).includes(product.category_id));
    if (!covers) continue;
    const off = promo.discount_type === 'percent'
      ? Math.round(priceC * Number(promo.discount_value) / 100)
      : cents(promo.discount_value);
    if (off <= 0 || off >= priceC) continue;
    const promoC = priceC - off;
    if (!best || promoC < best.priceC || (promoC === best.priceC && promo.name < best.promo.name)) {
      best = { promo, priceC: promoC };
    }
  }
  return best ? { promo: best.promo, price: money(best.priceC) } : null;
}

export const METHOD_LABELS = {
  cash: 'Dinheiro', pix: 'PIX', credit: 'Crédito', debit: 'Débito', card: 'Cartão', voucher: 'Vale',
};

export const formatTime = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return '';
  }
};

export const apiError = (e, fallback) => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return fallback;
};
