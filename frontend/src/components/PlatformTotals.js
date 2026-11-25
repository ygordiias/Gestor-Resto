import React from 'react';
import { formatCurrency } from '../lib/utils';

/**
 * Totais de pedido de plataforma (NostFood / 99 / iFood) com descontos e taxas,
 * para a conta fechar: subtotal − descontos + entrega + taxa de serviço = total.
 * Só exibição: caixa e relatórios continuam usando order.total.
 */

const num = v => Number(v || 0);

export function hasPlatformBreakdown(order) {
  return !!(order && order.external_source === 'nostfood' && order.discount_total !== undefined);
}

export default function PlatformTotals({ order }) {
  const subtotal = num(order.subtotal);
  const discount = num(order.discount_total);
  const deliveryGross = num(order.delivery_fee_gross ?? order.delivery_fee);
  const deliveryNet = num(order.delivery_fee_net ?? order.delivery_fee);
  const serviceFee = num(order.platform_service_fee);
  const total = num(order.total);
  const computed = Math.round((subtotal - discount + deliveryGross + serviceFee) * 100) / 100;
  const difference = Math.round((total - computed) * 100) / 100;
  const hasSplit = order.discount_store !== null && order.discount_store !== undefined;

  return (
    <div className="space-y-1 sm:space-y-2 border-t pt-2 text-xs sm:text-sm" data-testid="platform-totals">
      <div className="flex justify-between">
        <span>Subtotal:</span>
        <span>{formatCurrency(subtotal)}</span>
      </div>
      {discount > 0 && (
        <div>
          <div className="flex justify-between text-destructive">
            <span>Descontos:</span>
            <span>− {formatCurrency(discount)}</span>
          </div>
          {hasSplit && (
            <p className="text-muted-foreground pl-2">
              loja {formatCurrency(order.discount_store)} · plataforma {formatCurrency(order.discount_platform)}
            </p>
          )}
        </div>
      )}
      {deliveryGross > 0 && (
        <div>
          <div className="flex justify-between">
            <span>Taxa de entrega:</span>
            <span>+ {formatCurrency(deliveryGross)}</span>
          </div>
          {deliveryNet !== deliveryGross && (
            <p className="text-muted-foreground pl-2">
              cliente pagou {formatCurrency(deliveryNet)} (desconto de entrega incluído nos descontos)
            </p>
          )}
        </div>
      )}
      {serviceFee > 0 && (
        <div className="flex justify-between">
          <span>Taxa de serviço da plataforma:</span>
          <span>+ {formatCurrency(serviceFee)}</span>
        </div>
      )}
      <div className="flex justify-between font-bold text-base sm:text-lg">
        <span>Total pago pelo cliente:</span>
        <span className="text-primary">{formatCurrency(total)}</span>
      </div>
      {Math.abs(difference) >= 0.01 && (
        <p className="text-muted-foreground" data-testid="platform-totals-difference">
          Diferença de {formatCurrency(difference)} em relação à conta acima (valor informado pela plataforma).
        </p>
      )}
    </div>
  );
}
