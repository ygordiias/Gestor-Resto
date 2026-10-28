import React, { useCallback, useEffect, useState } from 'react';
import Layout from '../components/Layout';
import api from '../lib/api';
import { toast } from 'sonner';
import { FileText, Search, ChevronLeft, ChevronRight } from 'lucide-react';
const money = v => new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(Number(v || 0));
const fmt = date => { try { return new Date(date).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'}); } catch { return date; } };
const getErr = e => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'Erro ao consultar histórico';
export default function InvoiceHistoryPage() {
  const [filters, setFilters] = useState({start:'',end:'',status:'all',number:'',customer:''});
  const [searchFilters, setSearchFilters] = useState({...filters});
  const [page, setPage] = useState(1);
  const [data, setData] = useState({items:[],page:1,pages:1,total:0});
  const [loading, setLoading] = useState(false);
  const fetchData = useCallback(async () => {
    setLoading(true);
    try { const response = await api.get('/invoices/history',{params:{...searchFilters,page,page_size:50}}); setData(response.data); }
    catch(e) { toast.error(getErr(e)); }
    finally { setLoading(false); }
  },[searchFilters,page]);
  useEffect(()=>{ fetchData(); },[fetchData]);
  const submit = e => { e.preventDefault(); setPage(1); setSearchFilters({...filters}); };
  return <Layout title="Histórico de Notas">
    <div className="space-y-5" data-testid="invoices-history-page">
      <div className="border rounded-lg p-4 bg-card"><h2 className="font-heading text-xl font-bold flex items-center gap-2"><FileText className="w-6 h-6"/> Consulta de notas registradas</h2><p className="text-sm text-muted-foreground mt-1">Histórico paginado, sem limite fixo de 500 registros. Apenas consulta: não emite nota, não altera notas anteriores e não recupera dados que não foram registrados.</p></div>
      <form onSubmit={submit} className="border rounded-lg bg-card p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <label className="text-sm">De<input type="date" value={filters.start} onChange={e=>setFilters(f=>({...f,start:e.target.value}))} className="mt-1 w-full p-2 bg-background border rounded"/></label>
        <label className="text-sm">Até<input type="date" value={filters.end} onChange={e=>setFilters(f=>({...f,end:e.target.value}))} className="mt-1 w-full p-2 bg-background border rounded"/></label>
        <label className="text-sm">Status<select value={filters.status} onChange={e=>setFilters(f=>({...f,status:e.target.value}))} className="mt-1 w-full p-2 bg-background border rounded"><option value="all">Todos</option><option value="mock">MOCK / simulação</option><option value="pending">Pendente</option><option value="issued">Emitida</option><option value="cancelled">Cancelada</option></select></label>
        <label className="text-sm">Número da nota<input value={filters.number} onChange={e=>setFilters(f=>({...f,number:e.target.value}))} className="mt-1 w-full p-2 bg-background border rounded" placeholder="NF-..."/></label>
        <label className="text-sm">Nome do cliente<input value={filters.customer} onChange={e=>setFilters(f=>({...f,customer:e.target.value}))} className="mt-1 w-full p-2 bg-background border rounded" placeholder="Buscar por cliente"/></label>
        <div className="self-end"><button type="submit" className="rounded bg-primary text-primary-foreground px-4 py-2 flex items-center gap-2"><Search className="w-4 h-4"/> Filtrar</button></div>
      </form>
      <div className="border rounded-lg bg-card p-4 space-y-3"><div className="flex flex-wrap justify-between gap-3"><h3 className="font-semibold">{loading?'Consultando...':`${data.total} registros encontrados`}</h3><div className="text-sm text-muted-foreground">Página {data.page} de {data.pages}</div></div>
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-muted/40"><tr>{['Número','Data','Cliente','Status','Valor'].map(h=><th className="text-left p-3 whitespace-nowrap" key={h}>{h}</th>)}</tr></thead><tbody>{!data.items.length ? <tr><td colSpan={5} className="text-center p-6 text-muted-foreground">Nenhuma nota encontrada. Isso não significa que exista uma nota não registrada.</td></tr> : data.items.map(i=><tr key={i.id || i.number} className="border-b"><td className="p-3 font-medium">{i.number || '—'}</td><td className="p-3 whitespace-nowrap">{fmt(i.created_at)}</td><td className="p-3">{i.customer_name || 'Não informado'}</td><td className="p-3">{i.status || '—'}</td><td className="p-3 whitespace-nowrap">{money(i.total)}</td></tr>)}</tbody></table></div>
        <div className="flex justify-end gap-3"><button disabled={loading || page<=1} onClick={()=>setPage(p=>Math.max(1,p-1))} className="border rounded px-3 py-2 disabled:opacity-40 flex gap-1 items-center"><ChevronLeft className="w-4 h-4"/> Anterior</button><button disabled={loading || page>=data.pages} onClick={()=>setPage(p=>p+1)} className="border rounded px-3 py-2 disabled:opacity-40 flex gap-1 items-center">Próxima <ChevronRight className="w-4 h-4"/></button></div>
      </div>
      <div className="text-xs text-muted-foreground">Atenção: uma nota com status MOCK é somente um registro simulado; a tela não comprova emissão fiscal na SEFAZ.</div>
    </div>
  </Layout>;
}
