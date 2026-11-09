import React, { useEffect, useMemo, useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const brl = (n) => Number(n || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

/** Painel montado dentro da comanda selecionada do Caixa. */
export default function OrderDiscountPanel({ order, onApplied }) {
  const [scope, setScope] = useState('order');
  const [itemId, setItemId] = useState('');
  const [kind, setKind] = useState('percent');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [adminEmail, setAdminEmail] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const items = useMemo(() => (order?.items || []).filter(x => x.status !== 'cancelled'), [order]);

  useEffect(() => {
    setScope('order'); setItemId(''); setKind('percent');
    setValue(''); setReason(''); setAdminPassword('');
  }, [order?.id]);

  if (!order || order.is_closed || order.is_comp || order.source === 'online') return null;

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    if (scope === 'item' && !itemId) { toast.error('Selecione o item'); return; }
    if (kind !== 'clear' && (value === '' || Number(value) < 0)) { toast.error('Informe o desconto'); return; }
    if (reason.trim().length < 5 || !adminEmail.trim() || !adminPassword) {
      toast.error('Motivo e credenciais do administrador são obrigatórios'); return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API}/orders/${encodeURIComponent(order.id)}/discounts`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope, item_id: scope === 'item' ? itemId : null,
          kind, value: kind === 'clear' ? 0 : Number(value),
          reason: reason.trim(), admin_email: adminEmail.trim(), admin_password: adminPassword }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Erro HTTP ${response.status}`);
      toast.success(`Desconto registrado. Novo total: ${brl(data.order?.total)}`);
      setAdminPassword(''); setReason(''); setValue('');
      if (onApplied) await onApplied(data.order);
    } catch (e) { toast.error(e.message || 'Erro ao aplicar desconto'); }
    finally { setBusy(false); }
  };

  return (
    <Card className="border-amber-600/30" data-testid="discount-panel">
      <CardHeader className="pb-2"><CardTitle className="text-base">Descontos autorizados</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-2">
          <div>Itens: <strong>{brl(order.item_discount_total)}</strong></div>
          <div>Geral: <strong>{brl(order.order_discount_amount)}</strong></div>
        </div>
        <p className="text-xs text-muted-foreground">Aplicar antes do pagamento e da emissão de nota. Descontos reduzem a base dos 10%.</p>
        <form onSubmit={submit} className="space-y-2">
          <label className="block">Aplicar em
            <select className="border rounded-md h-10 w-full px-2 bg-background" value={scope} onChange={e => setScope(e.target.value)}>
              <option value="order">Comanda completa</option><option value="item">Item específico</option>
            </select>
          </label>
          {scope === 'item' && <label className="block">Produto
            <select className="border rounded-md h-10 w-full px-2 bg-background" value={itemId} onChange={e => setItemId(e.target.value)}>
              <option value="">Selecione o item...</option>
              {items.map(x => <option key={x.id} value={x.id}>{x.quantity}× {x.product_name} — {brl(x.line_total ?? x.unit_price * x.quantity)}</option>)}
            </select>
          </label>}
          <div className="grid grid-cols-2 gap-2">
            <label>Tipo
              <select className="border rounded-md h-10 w-full px-2 bg-background" value={kind} onChange={e => setKind(e.target.value)}>
                <option value="percent">Percentual (%)</option><option value="amount">Valor fixo (R$)</option><option value="clear">Remover desconto</option>
              </select>
            </label>
            {kind !== 'clear' && <label>Valor
              <Input type="number" min="0" max={kind === 'percent' ? '100' : undefined} step="0.01" value={value} onChange={e => setValue(e.target.value)} required />
            </label>}
          </div>
          <label className="block">Motivo (obrigatório)
            <Input maxLength={300} value={reason} onChange={e => setReason(e.target.value)} placeholder="Ex.: compensação por atraso" required />
          </label>
          <label className="block">E-mail do administrador
            <Input type="email" autoComplete="username" value={adminEmail} onChange={e => setAdminEmail(e.target.value)} required />
          </label>
          <label className="block">Senha para autorizar
            <Input type="password" autoComplete="current-password" value={adminPassword} onChange={e => setAdminPassword(e.target.value)} required />
          </label>
          <Button type="submit" className="w-full" disabled={busy}>{busy ? 'Registrando...' : 'Aplicar / atualizar desconto'}</Button>
        </form>
      </CardContent>
    </Card>
  );
}
