import React from 'react';

/**
 * Badge de identificação de pedido online (iFood / 99Food / Outro).
 * Reusado em KitchenPage, BarPage e CashierPage.
 * Mantém o padrão visual do restante do app; sem redesign.
 */

const PLATFORM_LABEL = {
  ifood: 'IFOOD',
  '99food': '99FOOD',
  nostfood: 'NOSTFOOD',
  other: 'ONLINE',
};

const PLATFORM_COLOR = {
  ifood: 'bg-red-600 text-white',
  '99food': 'bg-yellow-500 text-black',
  nostfood: 'bg-orange-600 text-white',
  other: 'bg-slate-700 text-white',
};

export function isOnlineOrder(order) {
  return !!(order && (order.source === 'online' || order.platform));
}

// Pedido da NostFood cobrado na entrega: é dinheiro do caixa (fechamento normal).
export function isCollectOnDelivery(order) {
  return !!(order && order.external_source === 'nostfood' && order.payment_status === 'to_collect');
}

// Pedido online pago pela plataforma (repasse) ou de teste: não entra no caixa.
export function isPlatformSettled(order) {
  return isOnlineOrder(order) && (!isCollectOnDelivery(order) || !!order.is_test);
}

// Cobrar na entrega que ainda deve dinheiro ao caixa (teste nunca deve).
export function owesCash(order) {
  return isCollectOnDelivery(order) && !order.is_test && order.status !== 'cancelled';
}

export function OnlineOrderBadge({ order, size = 'md', className = '' }) {
  if (!isOnlineOrder(order)) return null;
  const platform = (order.platform || 'other').toLowerCase();
  const label = PLATFORM_LABEL[platform] || 'ONLINE';
  const color = PLATFORM_COLOR[platform] || PLATFORM_COLOR.other;
  const num = order.external_order_number ? `#${order.external_order_number}` : '';
  const isDelivery = (order.delivery_type || '').toLowerCase() === 'delivery';
  const isPickup = ['pickup', 'retirada'].includes((order.delivery_type || '').toLowerCase());
  const fulfill = isDelivery ? 'DELIVERY' : isPickup ? 'RETIRADA' : '';
  const pack = isDelivery ? '📦 EMBALAR' : isPickup ? '🛍 RETIRADA' : '';
  const base = size === 'lg' ? 'text-sm px-3 py-1.5' : 'text-xs px-2 py-1';
  return (
    <div
      className={`inline-flex flex-col gap-1 rounded font-bold tracking-wide uppercase ${color} ${base} ${className}`}
      data-testid="online-order-badge"
    >
      <span className="flex items-center gap-1.5" data-testid="online-order-label">
        <span>ONLINE</span>
        <span>•</span>
        <span>{label}{num && ` ${num}`}</span>
        {fulfill && <><span>•</span><span>{fulfill}</span></>}
      </span>
      {order.is_test && (
        <span className="text-[10px] font-extrabold bg-sky-500 text-white rounded px-1" data-testid="online-order-test">
          TESTE
        </span>
      )}
      {order.external_source === 'nostfood' && order.payment_status && (
        <span className="text-[10px] font-extrabold" data-testid="online-order-payment">
          {order.payment_status === 'to_collect' ? '💵 COBRAR NA ENTREGA' : '✔ PAGO ONLINE'}
        </span>
      )}
      {pack && (
        <span className="text-[10px] font-extrabold" data-testid="online-order-packaging">
          {pack}
        </span>
      )}
    </div>
  );
}

export function OnlineOrderInlineSummary({ order }) {
  if (!isOnlineOrder(order)) return null;
  const platform = (order.platform || 'other').toLowerCase();
  const label = PLATFORM_LABEL[platform] || 'ONLINE';
  const num = order.external_order_number ? `#${order.external_order_number}` : '';
  const isDelivery = (order.delivery_type || '').toLowerCase() === 'delivery';
  const fulfill = isDelivery ? 'Delivery' : 'Retirada';
  return (
    <span data-testid="online-order-summary" className="font-semibold">
      {label}{num && ` ${num}`} — {fulfill}
    </span>
  );
}
