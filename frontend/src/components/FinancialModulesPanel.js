import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { toast } from 'sonner';
import { useAuth } from '../contexts/AuthContext';

const money = value => Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const today = () => {
  const fields = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(new Date());
  const get = type => fields.find(x => x.type === type)?.value || '';
  return `${get('year')}-${get('month')}-${get('day')}`;
};
const thisMonth = () => today().slice(0, 7);
const newId = () => (typeof window !== 'undefined' && window.crypto?.randomUUID?.()) ||
  `emp-${Date.now()}-${Math.random().toString(36).slice(2)}`;

async function request(path, method = 'GET', body) {
  const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {
    method,
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('token')}`,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(
    typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Falha na operação'
  );
  return data;
}

export default function FinancialModulesPanel() {
  const { user } = useAuth();
  const admin = user?.role === 'admin' || user?.role === 'superadmin';
  const [creditOpen, setCreditOpen] = useState(false);
  const [feesOpen, setFeesOpen] = useState(false);
  const [employees, setEmployees] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [products, setProducts] = useState([]);
  const [productId, setProductId] = useState('');
  const [qty, setQty] = useState(1);
  const [cart, setCart] = useState([]);
  const [busy, setBusy] = useState(false);
  const [staffName, setStaffName] = useState('');
  const [staffLimit, setStaffLimit] = useState('200');
  const [staffDiscount, setStaffDiscount] = useState('0');
  const [editLimit, setEditLimit] = useState('');
  const [editDiscount, setEditDiscount] = useState('0');
  const [staffActive, setStaffActive] = useState(true);
  const [statementMonth, setStatementMonth] = useState(thisMonth());
  const [statement, setStatement] = useState(null);
  const [settlementValue, setSettlementValue] = useState('');
  const [settlementNote, setSettlementNote] = useState('');
  const [feeWeek, setFeeWeek] = useState(today());
  const [fees, setFees] = useState(null);
  const purchaseIdRef = useRef(null);
  const settleIdRef = useRef(null);

  const selected = employees.find(x => x.id === selectedId);
  const itemTotal = useMemo(() => cart.reduce((sum, item) => sum + item.price * item.quantity, 0), [cart]);
  const discountedTotal = Math.round((itemTotal * (1 - Number(selected?.discount_pct || 0) / 100) + Number.EPSILON) * 100) / 100;

  const loadEmployees = useCallback(async () => {
    const data = await request('/employee-credit/employees');
    setEmployees(data.employees || []);
    return data.employees || [];
  }, []);

  const loadStatement = useCallback(async (employeeId, month) => {
    if (!admin || !employeeId || !month) return;
    const data = await request(`/employee-credit/employees/${encodeURIComponent(employeeId)}/statement?month=${encodeURIComponent(month)}`);
    setStatement(data);
  }, [admin]);

  const openCredit = async () => {
    setCreditOpen(true);
    try {
      const [people, menu] = await Promise.all([loadEmployees(), request('/products')]);
      setProducts((Array.isArray(menu) ? menu : []).filter(p => p.is_available !== false));
      setSelectedId(prev => prev || people.find(e => e.active)?.id || '');
    } catch (error) { toast.error(error.message); }
  };

  useEffect(() => {
    if (!creditOpen || !admin || !selectedId) return;
    loadStatement(selectedId, statementMonth).catch(err => toast.error(err.message));
  }, [creditOpen, admin, selectedId, statementMonth, loadStatement]);

  useEffect(() => {
    setCart([]);
    purchaseIdRef.current = null;
    settleIdRef.current = null;
    setStatement(null);
    if (selected) {
      setEditLimit(String(selected.limit));
      setEditDiscount(String(selected.discount_pct || 0));
      setStaffActive(selected.active);
    }
  // intentionally triggered by employee selection only; list refresh handled below
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const addCart = () => {
    const product = products.find(x => x.id === productId);
    if (!product) { toast.error('Escolha um produto'); return; }
    const quantity = Number(qty);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 30) {
      toast.error('Quantidade deve ser entre 1 e 30'); return;
    }
    setCart(old => {
      const existing = old.find(x => x.id === product.id);
      if (existing) {
        if (existing.quantity + quantity > 30) { toast.error('Máximo de 30 unidades por produto'); return old; }
        return old.map(x => x.id === product.id ? { ...x, quantity: x.quantity + quantity } : x);
      }
      return [...old, { id: product.id, name: product.name, price: Number(product.price || 0), quantity }];
    });
    purchaseIdRef.current = null;
    setProductId(''); setQty(1);
  };

  const savePurchase = async () => {
    if (busy || !selected?.active || !cart.length) return;
    if (discountedTotal > Number(selected.available || 0) + 0.001) {
      toast.error('Limite insuficiente para o consumo'); return;
    }
    const requestId = purchaseIdRef.current || newId();
    purchaseIdRef.current = requestId;
    setBusy(true);
    try {
      await request('/employee-credit/purchases', 'POST', {
        employee_id: selectedId, request_id: requestId,
        items: cart.map(x => ({ product_id: x.id, quantity: x.quantity }))
      });
      toast.success('Consumo registrado a prazo, fora do caixa físico.');
      setCart([]); purchaseIdRef.current = null;
      await loadEmployees();
      if (admin) await loadStatement(selectedId, statementMonth);
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  };

  const createEmployee = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await request('/employee-credit/employees', 'POST', {
        name: staffName.trim(), monthly_limit: Number(staffLimit), discount_pct: Number(staffDiscount)
      });
      toast.success('Funcionário cadastrado');
      setStaffName('');
      await loadEmployees();
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  };

  const saveEmployee = async () => {
    if (busy || !selectedId) return;
    setBusy(true);
    try {
      await request(`/employee-credit/employees/${encodeURIComponent(selectedId)}`, 'PUT', {
        monthly_limit: Number(editLimit), discount_pct: Number(editDiscount), active: staffActive
      });
      toast.success('Limite e cadastro atualizados');
      await loadEmployees();
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  };

  const settle = async () => {
    if (busy || !statement || Number(settlementValue) <= 0) return;
    if (!window.confirm(`Confirmar acerto externo de ${money(settlementValue)} para ${statement.employee}? Nenhum desconto será feito na folha automaticamente.`)) return;
    const requestId = settleIdRef.current || newId();
    settleIdRef.current = requestId;
    setBusy(true);
    try {
      await request(`/employee-credit/employees/${encodeURIComponent(selectedId)}/settlements`, 'POST', {
        request_id: requestId, month: statementMonth, amount: Number(settlementValue), note: settlementNote.trim()
      });
      toast.success('Acerto manual registrado no extrato');
      settleIdRef.current = null;
      setSettlementValue(''); setSettlementNote('');
      await loadEmployees();
      await loadStatement(selectedId, statementMonth);
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  };

  const voidPurchase = async tx => {
    const note = window.prompt(`Motivo do estorno do consumo de ${money(tx.amount)}:`, 'Correção de lançamento');
    if (!note?.trim()) return;
    setBusy(true);
    try {
      await request(`/employee-credit/employees/${encodeURIComponent(selectedId)}/void-purchase`, 'POST', {
        request_id: newId(), purchase_id: tx.id, note: note.trim()
      });
      toast.success('Lançamento estornado (histórico mantido)');
      await loadEmployees();
      await loadStatement(selectedId, statementMonth);
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  };

  const loadFees = async () => {
    try {
      setBusy(true);
      const data = await request(`/reports/service-fees/weekly?week=${encodeURIComponent(feeWeek)}`);
      setFees(data);
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  };

  return (
    <>
      <div className="flex flex-wrap gap-2 rounded-lg border bg-card p-3">
        <Button type="button" variant="outline" onClick={openCredit} data-testid="employee-credit-panel-btn">
          Consumo de funcionários
        </Button>
        {admin && (
          <Button type="button" variant="outline" onClick={() => { setFeesOpen(true); setFees(null); }} data-testid="service-fees-panel-btn">
            Relatório semanal dos 10%
          </Button>
        )}
      </div>

      <Dialog open={creditOpen} onOpenChange={open => { if (!busy) setCreditOpen(open); }}>
        <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Conta de consumo dos funcionários</DialogTitle>
            <DialogDescription>Crédito mensal individual; não registra dinheiro recebido nem desconto salarial automático.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label>Funcionário</Label>
                <select className="w-full rounded-md border bg-background p-2" value={selectedId} onChange={e => setSelectedId(e.target.value)}>
                  <option value="">Selecione</option>
                  {employees.filter(e => e.active || e.id === selectedId).map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </div>
              <div className="rounded-md border p-2 text-sm">
                {selected ? <>
                  <div>Limite mensal: <strong>{money(selected.limit)}</strong> · Usado: {money(selected.used)}</div>
                  <div>Disponível: <strong>{money(selected.available)}</strong> · Pendente: {money(selected.outstanding)}</div>
                  {selected.overdue > 0 && <div className="text-red-600 font-bold">Mês anterior pendente: {money(selected.overdue)} — crédito bloqueado</div>}
                </> : <span>Selecione um funcionário para consultar o limite.</span>}
              </div>
            </div>
            <div className="rounded-lg border p-3 space-y-2">
              <strong>Lançar consumo a prazo</strong>
              <div className="grid grid-cols-1 sm:grid-cols-6 gap-2">
                <select className="sm:col-span-4 rounded-md border bg-background p-2" value={productId} onChange={e => setProductId(e.target.value)}>
                  <option value="">Produto do cardápio...</option>
                  {products.map(p => <option key={p.id} value={p.id}>{p.name} — {money(p.price)}</option>)}
                </select>
                <Input className="sm:col-span-1" type="number" min="1" max="30" value={qty} onChange={e => setQty(e.target.value)} />
                <Button type="button" variant="secondary" onClick={addCart} disabled={!selected?.active}>Adicionar</Button>
              </div>
              {cart.map(x => <div className="flex items-center justify-between text-sm gap-2" key={x.id}>
                <span>{x.quantity}× {x.name}</span>
                <span>{money(x.price * x.quantity)} <button type="button" className="text-red-600 underline ml-2" onClick={() => { setCart(old => old.filter(v => v.id !== x.id)); purchaseIdRef.current = null; }}>Remover</button></span>
              </div>)}
              <div className="flex justify-between font-bold">Total a lançar {selected?.discount_pct ? `(${selected.discount_pct}% de desconto)` : ''}<span>{money(discountedTotal)}</span></div>
              <Button type="button" className="w-full" disabled={busy || !selected?.active || !cart.length || discountedTotal > Number(selected?.available || 0)} onClick={savePurchase}>
                {busy ? 'Registrando...' : 'Registrar débito administrativo'}
              </Button>
              <p className="text-xs text-muted-foreground">ATENÇÃO: este lançamento registra somente uma dívida administrativa. NÃO envia produtos à cozinha/bar e NÃO baixa estoque. A produção/saída precisa ser controlada em fluxo separado até a integração operacional.</p>
            </div>

            {admin && <>
              <div className="rounded-lg border p-3 space-y-2">
                <strong>Administração — cadastrar funcionário</strong>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <Input placeholder="Nome do funcionário" value={staffName} onChange={e => setStaffName(e.target.value)} />
                  <Input placeholder="Limite R$" type="number" min="0" step="0.01" value={staffLimit} onChange={e => setStaffLimit(e.target.value)} />
                  <Input placeholder="Desconto %" type="number" min="0" max="100" value={staffDiscount} onChange={e => setStaffDiscount(e.target.value)} />
                </div>
                <Button type="button" variant="outline" onClick={createEmployee} disabled={busy || staffName.trim().length < 2}>Cadastrar</Button>
              </div>
              {selected && <div className="rounded-lg border p-3 space-y-2">
                <strong>Administração — limite e situação de {selected.name}</strong>
                <div className="grid grid-cols-2 gap-2">
                  <div><Label>Limite mensal (R$)</Label><Input type="number" min="0" step="0.01" value={editLimit} onChange={e => setEditLimit(e.target.value)} /></div>
                  <div><Label>Desconto (%)</Label><Input type="number" min="0" max="100" value={editDiscount} onChange={e => setEditDiscount(e.target.value)} /></div>
                </div>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={staffActive} onChange={e => setStaffActive(e.target.checked)} /> Crédito ativo</label>
                <Button type="button" variant="outline" disabled={busy} onClick={saveEmployee}>Salvar alterações do cadastro</Button>
              </div>}
              {selected && <div className="rounded-lg border p-3 space-y-3">
                <strong>Extrato e acerto manual — {selected.name}</strong>
                <div><Label>Mês de referência</Label><Input type="month" value={statementMonth} onChange={e => { setStatementMonth(e.target.value); settleIdRef.current = null; }} /></div>
                {statement && <>
                  <div className="text-sm">Total consumido: {money(statement.used)} · Acertado: {money(statement.paid)} · <strong>Pendente: {money(statement.outstanding)}</strong></div>
                  <div className="space-y-1 max-h-48 overflow-y-auto text-sm">
                    {statement.transactions?.map(tx => <div key={tx.id} className="flex justify-between gap-2 border-b py-1">
                      <span>{new Date(tx.at).toLocaleString('pt-BR')} — {tx.type === 'purchase' ? `Consumo (${(tx.items || []).map(i => `${i.quantity}× ${i.product_name}`).join(', ')})` : tx.type === 'settlement' ? 'Acerto' : 'Estorno'} {tx.note ? `— ${tx.note}` : ''}</span>
                      <span className="shrink-0">{money(tx.amount)} {tx.type === 'purchase' && <button type="button" disabled={busy} className="text-red-600 underline" onClick={() => voidPurchase(tx)}>Estornar</button>}</span>
                    </div>)}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div><Label>Valor acertado fora do caixa (R$)</Label><Input type="number" min="0" step="0.01" value={settlementValue} onChange={e => { setSettlementValue(e.target.value); settleIdRef.current = null; }} /></div>
                    <div><Label>Referência / comprovante do acerto</Label><Input placeholder="Ex.: recibo de acerto 31/10" value={settlementNote} onChange={e => { setSettlementNote(e.target.value); settleIdRef.current = null; }} /></div>
                  </div>
                  <Button type="button" disabled={busy || Number(settlementValue) <= 0 || Number(settlementValue) > Number(statement.outstanding) || settlementNote.trim().length < 4} onClick={settle}>Registrar acerto confirmado</Button>
                  <p className="text-xs text-muted-foreground">O acerto é somente um registro administrativo. Não altera contracheque, salário, PIX ou gaveta.</p>
                </>}
              </div>}
            </>}
          </div>
        </DialogContent>
      </Dialog>

      {admin && <Dialog open={feesOpen} onOpenChange={setFeesOpen}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Taxa de serviço — relatório semanal</DialogTitle>
            <DialogDescription>Separação do valor cobrado de 10% e das vendas de produtos, sem confundir com lucro.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2 items-end">
              <div><Label>Escolha qualquer dia da semana</Label><Input type="date" value={feeWeek} onChange={e => setFeeWeek(e.target.value)} /></div>
              <Button type="button" onClick={loadFees} disabled={busy}>Consultar semana</Button>
            </div>
            {fees && <>
              <p className="text-sm">Período: <strong>{fees.week_start} a {fees.week_end_inclusive}</strong> (São Paulo)</p>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="border rounded p-2">Vendas sem gorjeta<br /><strong>{money(fees.summary.product_sales)}</strong></div>
                <div className="border rounded p-2">Taxa de serviço cobrada<br /><strong>{money(fees.summary.service_fee)}</strong></div>
                <div className="border rounded p-2">Total de vendas presenciais<br /><strong>{money(fees.summary.gross_total)}</strong></div>
                <div className="border rounded p-2">Comandas conciliadas<br /><strong>{fees.summary.orders}</strong></div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left p-1">Dia</th><th className="text-right p-1">Produtos</th><th className="text-right p-1">10%</th><th className="text-right p-1">Total</th></tr></thead><tbody>
                  {(fees.rows || []).map(day => <tr key={day.date} className="border-b"><td className="p-1">{day.date}</td><td className="text-right p-1">{money(day.product_sales)}</td><td className="text-right p-1">{money(day.service_fee)}</td><td className="text-right p-1">{money(day.gross_total)}</td></tr>)}
                </tbody></table>
              </div>
              {!!fees.excluded_unreconciled?.length && <p className="text-sm text-red-600">Atenção: {fees.excluded_unreconciled.length} comanda(s) com pagamento inconsistente foram excluídas. Confira antes de fechar o relatório.</p>}
              <p className="text-xs text-muted-foreground">Gorjeta destacada não é lucro líquido. Este relatório não realiza rateio ou pagamento aos funcionários.</p>
            </>}
          </div>
        </DialogContent>
      </Dialog>}
    </>
  );
}
