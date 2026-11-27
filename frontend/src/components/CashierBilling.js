// Caixa: cortesia por quantidade, desconto por item, pagamento parcial e estorno.
// O servidor valida tudo (order_billing.py); aqui só coletamos e mostramos.
import React, { useEffect, useMemo, useState } from 'react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from './ui/dialog';
import { ordersAPI } from '../lib/api';
import { formatCurrency } from '../lib/utils';
import {
  CASHIER_MAX_DISCOUNT_PCT, METHOD_LABELS, apiError, formatTime, freeQty, fullPrice, hasDiscount,
  hasPromo, isCancelled, orderSummary, paidQty, promoActive, promoLabel,
} from '../lib/billing';
import { itemDisplayName } from './OnlineOrderBadge';
import { toast } from 'sonner';
import { Plus, X } from 'lucide-react';

const cents = (v) => Math.round(Number(v || 0) * 100);

// Desconto e pagamento parcial só em comanda/mesa do salão (mesma regra do servidor).
export const isSalonBilling = (order) =>
  Boolean(order) && !(order.source === 'online' || order.external_source) && !order.is_comp;

// ---------------------------------------------------------------- selos do item
export function ItemBillingInfo({ item }) {
  if (!item || isCancelled(item)) return null;
  const original = fullPrice(item);
  const showOriginal = (item.is_courtesy || hasDiscount(item) || promoActive(item))
    && cents(original) !== cents(item.unit_price);
  return (
    <span className="flex flex-wrap items-center gap-1 mt-0.5">
      {showOriginal && (
        <span className="text-[10px] text-muted-foreground line-through" data-testid={`item-original-${item.id}`}>
          {formatCurrency(original)}/un
        </span>
      )}
      {item.is_courtesy && (
        <Badge className="text-[10px] bg-purple-600 hover:bg-purple-600" title={courtesyTitle(item)}
          data-testid={`item-courtesy-badge-${item.id}`}>
          CORTESIA{item.courtesy_reason ? ` · ${item.courtesy_reason}` : ''}
        </Badge>
      )}
      {hasDiscount(item) && (
        <Badge className="text-[10px] bg-amber-600 hover:bg-amber-600" title={discountTitle(item)}
          data-testid={`item-discount-badge-${item.id}`}>
          DESCONTO {Number(item.discount_pct || 0).toLocaleString('pt-BR')}%
          {item.discount_reason ? ` · ${item.discount_reason}` : ''}
        </Badge>
      )}
      {hasPromo(item) && (
        <Badge className={promoActive(item) ? 'text-[10px] bg-emerald-600 hover:bg-emerald-600' : 'text-[10px]'}
          variant={promoActive(item) ? 'default' : 'outline'} data-testid={`item-promo-badge-${item.id}`}>
          {promoLabel(item)}{promoActive(item) ? '' : ' (substituída pelo desconto)'}
        </Badge>
      )}
      {paidQty(item) > 0 && (
        <Badge variant="outline" className="text-[10px] border-green-600 text-green-700">
          PAGO {paidQty(item)}/{item.quantity}
        </Badge>
      )}
    </span>
  );
}

const courtesyTitle = (item) =>
  [item.courtesy_by_name && `por ${item.courtesy_by_name}`, formatTime(item.courtesy_at)].filter(Boolean).join(' · ');

const discountTitle = (item) => [
  item.discount_by_name && `por ${item.discount_by_name}`,
  item.discount_approved_by_name && `autorizado por ${item.discount_approved_by_name}`,
  formatTime(item.discount_at),
].filter(Boolean).join(' · ');

// ------------------------------------------------------------ ações do item
export function ItemBillingActions({ order, item, onCourtesy, onDiscount, onChanged, disabled }) {
  const [busy, setBusy] = useState(false);
  if (!item || isCancelled(item) || order?.is_closed) return null;

  const run = async (fn, ok) => {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      await onChanged?.();
    } catch (e) {
      toast.error(apiError(e, 'Não foi possível alterar o item'));
    } finally {
      setBusy(false);
    }
  };

  const lock = disabled || busy;
  return (
    <span className="flex flex-wrap gap-1 mt-1">
      {item.is_courtesy ? (
        <Button type="button" size="sm" variant="outline" className="h-6 px-2 text-[10px]" disabled={lock}
          onClick={() => run(() => ordersAPI.courtesy(order.id, item.id, { is_courtesy: false }),
            'Cortesia desfeita: o item voltou ao preço')}
          data-testid={`undo-courtesy-btn-${item.id}`}>
          Desfazer cortesia
        </Button>
      ) : (
        <Button type="button" size="sm" variant="outline" disabled={lock || freeQty(item) <= 0}
          className="h-6 px-2 text-[10px] border-purple-500/40 text-purple-700"
          onClick={() => onCourtesy(item)} data-testid={`courtesy-btn-${item.id}`}>
          Cortesia
        </Button>
      )}
      {isSalonBilling(order) && !item.is_courtesy && Number(item.unit_price) > 0 && (
        hasDiscount(item) ? (
          <Button type="button" size="sm" variant="outline" className="h-6 px-2 text-[10px]"
            disabled={lock || paidQty(item) > 0}
            onClick={() => run(() => ordersAPI.removeDiscount(order.id, item.id), 'Desconto removido')}
            data-testid={`remove-discount-btn-${item.id}`}>
            Tirar desconto
          </Button>
        ) : (
          <Button type="button" size="sm" variant="outline" disabled={lock || freeQty(item) <= 0}
            className="h-6 px-2 text-[10px] border-amber-500/50 text-amber-700"
            onClick={() => onDiscount(item)} data-testid={`discount-btn-${item.id}`}>
            Desconto
          </Button>
        )
      )}
    </span>
  );
}

function QuantityField({ item, value, onChange, testId }) {
  const max = freeQty(item);
  if (max <= 1) return null;
  return (
    <div className="space-y-1">
      <Label>Quantidade (de {max} sem pagamento)</Label>
      <Input type="number" min={1} max={max} step={1} value={value}
        onChange={(e) => onChange(e.target.value)} data-testid={testId} />
    </div>
  );
}

function AdminFields({ email, password, onEmail, onPassword }) {
  return (
    <div className="space-y-2 rounded border border-destructive/30 p-2">
      <p className="text-xs text-muted-foreground">Autorização do administrador</p>
      <Input type="email" placeholder="E-mail do administrador" value={email} autoComplete="off"
        onChange={(e) => onEmail(e.target.value)} data-testid="billing-admin-email" />
      <Input type="password" placeholder="Senha do administrador" value={password} autoComplete="new-password"
        onChange={(e) => onPassword(e.target.value)} data-testid="billing-admin-password" />
    </div>
  );
}

// ------------------------------------------------------------ cortesia
export function CourtesyDialog({ order, item, onClose, onDone }) {
  const [quantity, setQuantity] = useState(1);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setQuantity(item ? freeQty(item) : 1);
    setReason('');
    setBusy(false);
  }, [item]);

  const submit = async () => {
    const qty = parseInt(quantity, 10);
    if (!qty || qty <= 0 || qty > freeQty(item)) return toast.error('Quantidade inválida');
    if (!reason.trim()) return toast.error('Informe o motivo da cortesia');
    setBusy(true);
    try {
      await ordersAPI.courtesy(order.id, item.id, { is_courtesy: true, quantity: qty, reason: reason.trim() });
      toast.success(`${qty}x ${itemDisplayName(item)} em cortesia`);
      onClose();
      await onDone?.();
    } catch (e) {
      toast.error(apiError(e, 'Erro ao marcar cortesia'));
      setBusy(false);
    }
  };

  return (
    <Dialog open={Boolean(item)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Cortesia</DialogTitle>
          <DialogDescription>
            {item ? `${item.quantity}x ${itemDisplayName(item)}` : ''}: as unidades marcadas saem da conta,
            mas continuam baixando o estoque.
          </DialogDescription>
        </DialogHeader>
        {item && (
          <div className="space-y-3">
            <QuantityField item={item} value={quantity} onChange={setQuantity} testId="courtesy-qty" />
            <div className="space-y-1">
              <Label>Motivo</Label>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ex.: aniversário"
                data-testid="courtesy-reason" />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Voltar</Button>
          <Button onClick={submit} disabled={busy} data-testid="courtesy-confirm">
            {busy ? 'Salvando...' : 'Marcar cortesia'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------ desconto
export function DiscountDialog({ order, item, isAdmin, onClose, onDone }) {
  const [quantity, setQuantity] = useState(1);
  const [kind, setKind] = useState('percent');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setQuantity(item ? freeQty(item) : 1);
    setKind('percent');
    setValue('');
    setReason('');
    setAdminEmail('');
    setAdminPassword('');
    setBusy(false);
  }, [item]);

  const full = item ? fullPrice(item) : 0;
  const preview = useMemo(() => {
    const v = parseFloat(String(value).replace(',', '.'));
    if (!item || !v || v <= 0) return null;
    const fullC = cents(full);
    const off = kind === 'percent' ? Math.round(fullC * v / 100) : cents(v);
    if (off <= 0 || off >= fullC) return { invalid: true };
    const unitC = fullC - off;
    return { unit: unitC / 100, pct: Math.round(off * 10000 / fullC) / 100,
      promoBigger: promoActive(item) && cents(item.promo_price) <= unitC };
  }, [item, value, kind, full]);
  const needsAdmin = !isAdmin && preview && !preview.invalid && preview.pct > CASHIER_MAX_DISCOUNT_PCT;

  const submit = async () => {
    const qty = parseInt(quantity, 10);
    const v = parseFloat(String(value).replace(',', '.'));
    if (!qty || qty <= 0 || qty > freeQty(item)) return toast.error('Quantidade inválida');
    if (!v || v <= 0 || !preview || preview.invalid) return toast.error('Valor do desconto inválido');
    if (!reason.trim()) return toast.error('Informe o motivo do desconto');
    if (needsAdmin && (!adminEmail.trim() || !adminPassword)) {
      return toast.error(`Desconto acima de ${CASHIER_MAX_DISCOUNT_PCT}%: precisa do administrador`);
    }
    setBusy(true);
    try {
      const res = await ordersAPI.discount(order.id, item.id, {
        quantity: qty, type: kind, value: v, reason: reason.trim(),
        ...(needsAdmin ? { admin_email: adminEmail.trim(), admin_password: adminPassword } : {}),
      });
      if (res.data?.warning) toast.warning(res.data.warning);
      toast.success(`Desconto de ${preview.pct.toLocaleString('pt-BR')}% aplicado`);
      onClose();
      await onDone?.();
    } catch (e) {
      const msg = apiError(e, 'Erro ao aplicar desconto');
      if (e?.response?.status === 409 && msg.includes('não acumula')) toast.warning(msg);
      else toast.error(msg);
      setBusy(false);
    }
  };

  return (
    <Dialog open={Boolean(item)} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Desconto no item</DialogTitle>
          <DialogDescription>
            {item ? `${itemDisplayName(item)} · ${formatCurrency(full)}/un` : ''}. Caixa dá até{' '}
            {CASHIER_MAX_DISCOUNT_PCT}%; acima disso só o administrador.
          </DialogDescription>
        </DialogHeader>
        {item && (
          <div className="space-y-3">
            {promoActive(item) && (
              <p className="text-xs rounded bg-emerald-50 text-emerald-900 p-2">
                {promoLabel(item)} ({formatCurrency(item.promo_price)}/un). O desconto não acumula com a
                promoção: vale o maior.
              </p>
            )}
            <QuantityField item={item} value={quantity} onChange={setQuantity} testId="discount-qty" />
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label>Tipo</Label>
                <Select value={kind} onValueChange={setKind}>
                  <SelectTrigger data-testid="discount-type"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">%</SelectItem>
                    <SelectItem value="value">R$ por unidade</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{kind === 'percent' ? 'Percentual' : 'Valor (R$)'}</Label>
                <Input type="number" min="0" step="0.01" value={value}
                  onChange={(e) => setValue(e.target.value)} data-testid="discount-value" />
              </div>
            </div>
            {preview && (preview.invalid ? (
              <p className="text-xs text-destructive">Desconto igual ou maior que o preço: use Cortesia.</p>
            ) : (
              <p className="text-xs">
                Fica {formatCurrency(preview.unit)}/un ({preview.pct.toLocaleString('pt-BR')}%).
                {preview.promoBigger && (
                  <span className="block text-amber-700 font-medium">
                    A promoção já dá desconto maior: o desconto não será aplicado.
                  </span>
                )}
              </p>
            ))}
            <div className="space-y-1">
              <Label>Motivo</Label>
              <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ex.: demora no preparo"
                data-testid="discount-reason" />
            </div>
            {needsAdmin && (
              <AdminFields email={adminEmail} password={adminPassword}
                onEmail={setAdminEmail} onPassword={setAdminPassword} />
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Voltar</Button>
          <Button onClick={submit} disabled={busy} data-testid="discount-confirm">
            {busy ? 'Salvando...' : 'Aplicar desconto'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------ resumo da conta
export function BillingSummary({ order }) {
  const s = orderSummary(order);
  if (!s) return null;
  const row = (label, value, opts = {}) => (
    <div className={`flex justify-between text-xs sm:text-sm ${opts.className || ''}`} data-testid={opts.testId}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
  return (
    <div className="space-y-1 sm:space-y-2 border-t pt-2">
      {/* Promoções, descontos e cortesias já estão fora do subtotal: aqui só o quanto foi concedido. */}
      {s.promo > 0 && row('Promoções concedidas:', formatCurrency(s.promo), { className: 'text-emerald-700', testId: 'summary-promo' })}
      {s.discount > 0 && row('Descontos concedidos:', formatCurrency(s.discount), { className: 'text-amber-700', testId: 'summary-discount' })}
      {s.courtesy > 0 && row('Cortesias concedidas:', formatCurrency(s.courtesy), { className: 'text-purple-700', testId: 'summary-courtesy' })}
      {row('Subtotal cobrado:', formatCurrency(s.subtotal))}
      {row(`Serviço (${s.servicePct ?? 0}%):`, formatCurrency(s.serviceFee))}
      {Number(order.delivery_fee) > 0 && row('Taxa de entrega:', formatCurrency(order.delivery_fee))}
      <div className="flex justify-between font-bold text-base sm:text-lg">
        <span>Total:</span>
        <span className="text-primary">{formatCurrency(s.total)}</span>
      </div>
      {s.paid > 0 && (
        <>
          {row('Pago:', formatCurrency(s.paid), { className: 'text-green-700 font-medium', testId: 'summary-paid' })}
          <div className="flex justify-between font-bold text-sm sm:text-base text-red-700" data-testid="summary-remaining">
            <span>Falta pagar:</span>
            <span>{formatCurrency(s.remaining)}</span>
          </div>
        </>
      )}
      {(s.promo > 0 || s.discount > 0 || s.courtesy > 0) && (
        <p className="text-[10px] text-muted-foreground">
          Os {s.servicePct ?? 0}% são calculados sobre o valor cobrado, já sem promoções, descontos e cortesias.
        </p>
      )}
    </div>
  );
}

// ------------------------------------------------------------ pagamento parcial
const METHODS = ['cash', 'pix', 'credit', 'debit', 'voucher'];

export function PartialPaymentDialog({ order, open, onOpenChange, onDone }) {
  const [mode, setMode] = useState('amount');
  const [amount, setAmount] = useState('');
  const [selection, setSelection] = useState({});
  const [lines, setLines] = useState([{ method: 'pix', amount: '' }]);
  const [busy, setBusy] = useState(false);
  const summary = orderSummary(order);

  useEffect(() => {
    if (!open) return;
    setMode('amount');
    setAmount('');
    setSelection({});
    setLines([{ method: 'pix', amount: '' }]);
    setBusy(false);
  }, [open]);

  const payable = (order?.items || []).filter(
    (i) => !isCancelled(i) && !i.is_courtesy && Number(i.unit_price) > 0 && freeQty(i) > 0);
  const pct = Number(order?.service_fee_percentage || 0);
  const itemsBaseC = payable.reduce((sum, i) => sum + cents(i.unit_price) * Number(selection[i.id] || 0), 0);
  const itemsTargetC = Math.min(itemsBaseC + Math.round(itemsBaseC * pct / 100), cents(summary?.remaining));
  const targetC = mode === 'amount' ? cents(String(amount).replace(',', '.')) : itemsTargetC;
  const receivedC = lines.reduce((s, l) => s + cents(String(l.amount).replace(',', '.')), 0);
  const changeC = receivedC - targetC;

  // Preenche a 1ª forma com o valor escolhido enquanto só houver uma.
  useEffect(() => {
    if (lines.length === 1 && targetC > 0) {
      setLines((prev) => [{ ...prev[0], amount: (targetC / 100).toFixed(2) }]);
    }
  }, [targetC]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    if (targetC <= 0) return toast.error(mode === 'amount' ? 'Informe o valor a receber' : 'Escolha os itens');
    if (targetC > cents(summary.remaining)) return toast.error('Valor maior que o que falta pagar');
    if (receivedC < targetC) return toast.error('Pagamentos menores que o valor a receber');
    const payments = lines
      .map((l) => ({ method: l.method, amount: Number(String(l.amount).replace(',', '.')) || 0 }))
      .filter((p) => p.amount > 0);
    const payload = mode === 'amount'
      ? { amount: targetC / 100, payments }
      : { items: payable.filter((i) => Number(selection[i.id]) > 0)
          .map((i) => ({ item_id: i.id, quantity: Number(selection[i.id]) })), payments };
    setBusy(true);
    try {
      const res = await ordersAPI.partialPayment(order.id, payload);
      const { change, remaining } = res.data || {};
      toast.success(`Recebido ${formatCurrency(res.data?.partial_payment?.amount)}. Falta pagar ${formatCurrency(remaining)}`
        + (change > 0 ? ` · troco ${formatCurrency(change)}` : ''));
      onOpenChange(false);
      await onDone?.(res.data?.order);
    } catch (e) {
      toast.error(apiError(e, 'Erro ao registrar o pagamento'));
      setBusy(false);
    }
  };

  if (!order) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Receber parte da conta</DialogTitle>
          <DialogDescription>
            Falta pagar {formatCurrency(summary.remaining)}. A comanda continua aberta até zerar.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <Button type="button" variant={mode === 'amount' ? 'default' : 'outline'} onClick={() => setMode('amount')}
              data-testid="partial-mode-amount">Por valor</Button>
            <Button type="button" variant={mode === 'items' ? 'default' : 'outline'} onClick={() => setMode('items')}
              disabled={!payable.length} data-testid="partial-mode-items">Por itens</Button>
          </div>
          {mode === 'amount' ? (
            <div className="space-y-1">
              <Label>Valor a receber (R$)</Label>
              <Input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)}
                data-testid="partial-amount" />
            </div>
          ) : (
            <div className="space-y-2">
              {payable.map((i) => (
                <div key={i.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex-1 min-w-0 truncate">
                    {itemDisplayName(i)} · {formatCurrency(i.unit_price)}
                    <span className="text-xs text-muted-foreground"> ({freeQty(i)} sem pagamento)</span>
                  </span>
                  <Input type="number" min={0} max={freeQty(i)} step={1} className="w-20"
                    value={selection[i.id] ?? 0}
                    onChange={(e) => setSelection((s) => ({
                      ...s, [i.id]: Math.max(0, Math.min(freeQty(i), parseInt(e.target.value, 10) || 0)) }))}
                    data-testid={`partial-item-qty-${i.id}`} />
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                Valor dos itens{pct ? ` + ${pct}% de serviço` : ''}: {formatCurrency(itemsTargetC / 100)}
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label>Formas de pagamento</Label>
            {lines.map((line, idx) => (
              <div key={idx} className="flex gap-2">
                <Select value={line.method}
                  onValueChange={(v) => setLines((ls) => ls.map((l, i) => (i === idx ? { ...l, method: v } : l)))}>
                  <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {METHODS.map((m) => <SelectItem key={m} value={m}>{METHOD_LABELS[m]}</SelectItem>)}
                  </SelectContent>
                </Select>
                <Input type="number" min="0" step="0.01" value={line.amount}
                  onChange={(e) => setLines((ls) => ls.map((l, i) => (i === idx ? { ...l, amount: e.target.value } : l)))}
                  data-testid={`partial-pay-amount-${idx}`} />
                {lines.length > 1 && (
                  <Button type="button" variant="ghost" size="icon"
                    onClick={() => setLines((ls) => ls.filter((_, i) => i !== idx))}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="w-full"
              onClick={() => setLines((ls) => [...ls, { method: 'cash', amount: '' }])}>
              <Plus className="h-4 w-4 mr-2" />Outra forma
            </Button>
            {changeC > 0 && (
              <p className="text-sm font-medium">Troco: {formatCurrency(changeC / 100)} (só do dinheiro)</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Voltar</Button>
          <Button onClick={submit} disabled={busy || targetC <= 0} data-testid="partial-confirm">
            {busy ? 'Registrando...' : `Receber ${formatCurrency(targetC / 100)}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------ lista + estorno
export function PartialPaymentsList({ order, isAdmin, onChanged }) {
  const [target, setTarget] = useState(null);
  const [reason, setReason] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const partials = order?.partial_payments || [];
  if (!partials.length) return null;

  const open = (p) => {
    setTarget(p);
    setReason('');
    setAdminEmail('');
    setAdminPassword('');
    setBusy(false);
  };

  const submit = async () => {
    if (!reason.trim()) return toast.error('Informe o motivo do estorno');
    if (!isAdmin && (!adminEmail.trim() || !adminPassword)) return toast.error('Estorno só com o administrador');
    setBusy(true);
    try {
      await ordersAPI.reversePartial(order.id, target.id, {
        reason: reason.trim(),
        ...(isAdmin ? {} : { admin_email: adminEmail.trim(), admin_password: adminPassword }),
      });
      toast.success(`Pagamento de ${formatCurrency(target.amount)} estornado`);
      setTarget(null);
      await onChanged?.();
    } catch (e) {
      toast.error(apiError(e, 'Erro ao estornar'));
      setBusy(false);
    }
  };

  return (
    <div className="rounded border p-2 space-y-1" data-testid="partial-payments-list">
      <p className="text-xs font-medium">Pagamentos parciais</p>
      {partials.map((p) => {
        const reversed = p.status === 'reversed';
        return (
          <div key={p.id} className={`text-xs flex items-start justify-between gap-2 ${reversed ? 'opacity-60' : ''}`}>
            <span className="flex-1 min-w-0">
              <span className={reversed ? 'line-through' : 'font-medium'}>{formatCurrency(p.amount)}</span>
              {' · '}{(p.payments || []).map((x) => `${METHOD_LABELS[x.method] || x.method} ${formatCurrency(x.amount)}`).join(' + ')}
              <span className="block text-muted-foreground">
                {p.created_by_name} · {formatTime(p.created_at)}
                {(p.items || []).length > 0 && ` · ${p.items.map((i) => `${i.quantity}x ${i.product_name || ''}`).join(', ')}`}
              </span>
              {reversed && (
                <span className="block text-destructive">
                  Estornado por {p.reversed_by_name} · {formatTime(p.reversed_at)} · {p.reversal_reason}
                </span>
              )}
            </span>
            {!reversed && !order.is_closed && (
              <Button type="button" size="sm" variant="outline"
                className="h-6 px-2 text-[10px] border-destructive/40 text-destructive"
                onClick={() => open(p)} data-testid={`reverse-partial-btn-${p.id}`}>
                Estornar
              </Button>
            )}
          </div>
        );
      })}
      <Dialog open={Boolean(target)} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Estornar pagamento</DialogTitle>
            <DialogDescription>
              {target ? `${formatCurrency(target.amount)} de ${formatTime(target.created_at)}` : ''}: o valor
              sai do caixa e volta para "Falta pagar". Só o administrador estorna.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Motivo</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="reverse-reason" />
            {!isAdmin && (
              <AdminFields email={adminEmail} password={adminPassword}
                onEmail={setAdminEmail} onPassword={setAdminPassword} />
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTarget(null)} disabled={busy}>Voltar</Button>
            <Button variant="destructive" onClick={submit} disabled={busy} data-testid="reverse-confirm">
              {busy ? 'Estornando...' : 'Estornar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ------------------------------------------------------------ pré-conta (HTML)
export function preBillLineExtras(item, escape) {
  const notes = [];
  if (hasPromo(item) && promoActive(item)) {
    notes.push(`${escape(promoLabel(item))} (de ${escape(formatCurrency(item.promo_original_price))}/un)`);
  }
  if (hasDiscount(item)) {
    notes.push(`Desconto ${escape(Number(item.discount_pct || 0).toLocaleString('pt-BR'))}% `
      + `(de ${escape(formatCurrency(item.discount_original_price))}/un)`
      + (item.discount_reason ? `: ${escape(item.discount_reason)}` : ''));
  }
  if (item.is_courtesy) {
    notes.push(`CORTESIA (${escape(formatCurrency(Number(item.courtesy_original_price || 0) * Number(item.quantity || 0)))})`
      + (item.courtesy_reason ? `: ${escape(item.courtesy_reason)}` : ''));
  }
  if (paidQty(item) > 0) notes.push(`Pago ${paidQty(item)} de ${escape(item.quantity)}`);
  return notes.map((n) => `<tr><td colspan="2" class="note">${n}</td></tr>`).join('');
}
