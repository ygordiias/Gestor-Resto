import React, { useState } from 'react';
import api from '../lib/api';
import { toast } from 'sonner';
import { CalendarDays, Download, Search, SlidersHorizontal } from 'lucide-react';

const brMoney = (v) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(v || 0));
const today = () => new Date().toLocaleDateString('sv-SE', {timeZone:'America/Sao_Paulo'});
const monthStart = () => `${today().slice(0, 7)}-01`;
const safeCsv = (v) => { const raw = String(v ?? ''); const val = /^[\s]*[=+@-]/.test(raw) ? `'${raw}` : raw; return `"${val.replace(/"/g, '""')}"`; };
const getErr = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'Erro ao consultar os relatórios';

export default function AdvancedReportsPanel() {
  const [filters, setFilters] = useState({start: monthStart(), end: today(), channel:'all', payment:'all', group_by:'day', search:''});
  const [metric, setMetric] = useState('gross_total');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const field = (key, value) => setFilters(f => ({...f, [key]: value}));
  const presets = (name) => {
    const end = today();
    const d = new Date(`${end}T12:00:00Z`);
    if (name === 'today') return setFilters(f=>({...f, start:end, end}));
    if (name === '7') { d.setUTCDate(d.getUTCDate()-6); return setFilters(f=>({...f, start:d.toISOString().slice(0,10), end})); }
    if (name === 'month') return setFilters(f=>({...f, start:monthStart(), end}));
  };
  const query = async (event) => {
    event?.preventDefault?.();
    if (!filters.start || !filters.end || filters.start > filters.end) return toast.error('Informe um intervalo válido');
    setLoading(true);
    try { const response = await api.get('/reports/advanced', { params: filters, timeout: 30000 }); setResult(response.data); }
    catch(e) { toast.error(getErr(e)); }
    finally { setLoading(false); }
  };
  const download = () => {
    if (!result) return;
    const columns = ['Período', 'Pedidos', 'Produtos', 'Taxa 10%', 'Total', 'Presencial', 'Online'];
    const rows = result.rows.map(x => [x.period,x.orders,x.product_sales,x.service_fee,x.gross_total,x.local_total,x.online_total]);
    const csv = '\ufeff' + [columns,...rows].map(row=>row.map(safeCsv).join(';')).join('\r\n');
    const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url;
    a.download = `gestor-resto-relatorio-${result.filters.start}-a-${result.filters.end}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };
  const summary = result?.summary;
  const metricNames = {gross_total:'Total de pedidos', product_sales:'Venda de produtos', service_fee:'Taxa de serviço (10%)', local_total:'Presencial', online_total:'Online', orders:'Quantidade de pedidos'};
  return <section className="rounded-xl border bg-card p-4 sm:p-5 space-y-4" data-testid="advanced-reports-panel">
    <div className="flex items-start gap-2"><SlidersHorizontal className="w-6 h-6 text-primary shrink-0"/><div><h2 className="font-heading text-xl font-bold">Consulta financeira por período</h2><p className="text-sm text-muted-foreground">Selecione datas no calendário, canal, método de pagamento e tipo de relatório. Consulta independente dos gráficos rápidos abaixo.</p></div></div>
    <form onSubmit={query} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      <label className="text-sm">Data inicial<input className="mt-1 w-full border rounded p-2 bg-background" type="date" required value={filters.start} onChange={e=>field('start', e.target.value)}/></label>
      <label className="text-sm">Data final<input className="mt-1 w-full border rounded p-2 bg-background" type="date" required value={filters.end} onChange={e=>field('end', e.target.value)}/></label>
      <label className="text-sm">Canal<select className="mt-1 w-full border rounded p-2 bg-background" value={filters.channel} onChange={e=>field('channel',e.target.value)}><option value="all">Todos os canais</option><option value="local">Salão e balcão</option><option value="online">Pedidos online / plataformas</option></select></label>
      <label className="text-sm">Pagamento<select className="mt-1 w-full border rounded p-2 bg-background" value={filters.payment} onChange={e=>field('payment',e.target.value)}><option value="all">Todos os métodos</option><option value="cash">Dinheiro</option><option value="pix">Pix</option><option value="credit">Crédito</option><option value="debit">Débito</option><option value="card">Cartão (legado)</option><option value="voucher">Vale alimentação/refeição</option><option value="platform">Plataformas online</option></select></label>
      <label className="text-sm">Agrupar resultados<select className="mt-1 w-full border rounded p-2 bg-background" value={filters.group_by} onChange={e=>field('group_by',e.target.value)}><option value="day">Por dia</option><option value="week">Por semana</option><option value="month">Por mês</option></select></label>
      <label className="text-sm">Buscar pedido/mesa/comanda<input className="mt-1 w-full border rounded p-2 bg-background" value={filters.search} onChange={e=>field('search',e.target.value)} maxLength={100} placeholder="Ex.: 205, 99Food ou número"/></label>
      <div className="sm:col-span-2 lg:col-span-3 flex flex-wrap gap-2 items-center"><button type="button" onClick={()=>presets('today')} className="px-3 py-2 border rounded text-sm">Hoje</button><button type="button" onClick={()=>presets('7')} className="px-3 py-2 border rounded text-sm">Últimos 7 dias</button><button type="button" onClick={()=>presets('month')} className="px-3 py-2 border rounded text-sm">Este mês</button><button type="submit" disabled={loading} className="ml-auto px-4 py-2 bg-primary text-primary-foreground rounded flex items-center gap-2"><Search className="w-4 h-4"/> {loading?'Consultando...':'Consultar'}</button></div>
    </form>
    {!result && <div className="text-sm p-3 border rounded bg-muted/30 flex gap-2 items-center"><CalendarDays className="w-4 h-4"/> Escolha o intervalo e clique em Consultar. Não cria, altera ou fecha pedidos.</div>}
    {result && <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ['Valor dos pedidos',brMoney(summary.gross_total)], ['Produtos',brMoney(summary.product_sales)],
          ['Taxa de serviço',brMoney(summary.service_fee)], ['Pedidos',summary.orders],
          ['Presencial',brMoney(summary.local_total)], ['Online',brMoney(summary.online_total)],
          ['Ticket médio',brMoney(summary.avg_ticket)], ['Presenciais sem conciliação',summary.unreconciled_local_orders],
        ].map(([label,value])=><div className="p-3 border rounded-lg" key={label}><div className="text-xs text-muted-foreground">{label}</div><div className="font-semibold text-lg mt-1 break-words">{value}</div></div>)}
      </div>
      <div className="flex justify-between gap-2 flex-wrap items-center"><label className="text-sm">Tipo para destacar<select className="ml-2 border rounded p-2 bg-background" value={metric} onChange={e=>setMetric(e.target.value)}>{Object.entries(metricNames).map(([v,n])=><option value={v} key={v}>{n}</option>)}</select></label><button onClick={download} className="border rounded px-3 py-2 flex items-center gap-2 text-sm"><Download className="w-4 h-4"/> Exportar CSV</button></div>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-muted/50"><tr>{['Período','Pedidos','Produtos','Taxa 10%','Total','Presencial','Online'].map(x=><th className="px-3 py-2 text-left whitespace-nowrap" key={x}>{x}</th>)}</tr></thead><tbody>{result.rows.length ? result.rows.map(row=><tr key={row.period} className="border-b"><td className="px-3 py-2">{row.period}</td><td className={`px-3 py-2 ${metric==='orders'?'font-bold':''}`}>{row.orders}</td><td className={`px-3 py-2 whitespace-nowrap ${metric==='product_sales'?'font-bold':''}`}>{brMoney(row.product_sales)}</td><td className={`px-3 py-2 whitespace-nowrap ${metric==='service_fee'?'font-bold':''}`}>{brMoney(row.service_fee)}</td><td className={`px-3 py-2 whitespace-nowrap ${metric==='gross_total'?'font-bold':''}`}>{brMoney(row.gross_total)}</td><td className={`px-3 py-2 whitespace-nowrap ${metric==='local_total'?'font-bold':''}`}>{brMoney(row.local_total)}</td><td className={`px-3 py-2 whitespace-nowrap ${metric==='online_total'?'font-bold':''}`}>{brMoney(row.online_total)}</td></tr>) : <tr><td className="p-4" colSpan={7}>Nenhum pedido encontrado para os filtros.</td></tr>}</tbody></table></div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div><h3 className="font-semibold mb-2">Produtos mais vendidos</h3><div className="overflow-x-auto max-h-72"><table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-2">Produto</th><th className="text-right">Qtde.</th><th className="text-right">Valor</th></tr></thead><tbody>{result.top_products.map(p=><tr key={p.name} className="border-b"><td className="py-2">{p.name}</td><td className="text-right">{p.quantity}</td><td className="text-right whitespace-nowrap">{brMoney(p.revenue)}</td></tr>)}</tbody></table></div></div>
        <div><h3 className="font-semibold mb-2">Recebimentos informados no presencial</h3><div className="overflow-x-auto max-h-72"><table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-2">Método</th><th className="text-right">Valor registrado</th></tr></thead><tbody>{result.payment_methods.map(x=><tr key={x.method} className="border-b"><td className="py-2">{x.method}</td><td className="text-right">{brMoney(x.amount)}</td></tr>)}</tbody></table></div></div>
      </div>
      <p className="text-xs text-muted-foreground border-t pt-3">{result.note}</p>
    </div>}
  </section>;
}
