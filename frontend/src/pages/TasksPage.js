import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout';
import api from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';
import { ClipboardCheck, Plus, CheckCircle2, AlertTriangle, RefreshCw, History, Pencil, PauseCircle } from 'lucide-react';

const SECTORS = [
  ['all', 'Todos os setores'], ['kitchen', 'Cozinha'], ['bar', 'Bar'],
  ['cashier', 'Caixa'], ['service', 'Atendimento'], ['stock', 'Estoque'],
  ['purchasing', 'Compras'], ['maintenance', 'Manutenção'],
];
const TYPES = [
  ['cleaning', 'Limpeza'], ['stock', 'Conferência de estoque'], ['expiry', 'Validades'],
  ['oil_change', 'Troca de óleo'], ['preparation', 'Preparação'],
  ['purchasing', 'Compras'], ['maintenance', 'Manutenção'], ['other', 'Outros'],
];
const FREQS = [['daily','Diária'], ['weekly','Semanal'], ['once','Única'], ['occurrence','Por ocorrência']];
const dateNow = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' });
const emptyTask = () => ({ title: '', description: '', sector: 'kitchen', task_type: 'cleaning',
  frequency: 'daily', due_on: dateNow(), due_time: '20:00', assignee_id: '', active: true });
const errorText = (e) => typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'Erro na solicitação; confira o backend';
const fmt = (s) => { try { return new Date(s).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }); } catch { return s; } };
const statusClass = (s) => s === 'overdue' ? 'bg-red-100 text-red-800' : s === 'done' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-900';
const statusText = { overdue: 'Vencida', pending: 'Pendente', done: 'Concluída', inactive: 'Inativa' };

export default function TasksPage() {
  const { user } = useAuth();
  const admin = ['superadmin', 'admin'].includes(user?.role);
  const [sector, setSector] = useState('all');
  const [view, setView] = useState('active');
  const [tasks, setTasks] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyTask());
  const [saving, setSaving] = useState(false);
  const [events, setEvents] = useState(null);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/operations/tasks', { params: { sector, state: view } });
      setTasks(res.data.tasks || []);
    } catch (e) { toast.error(errorText(e)); }
    finally { setLoading(false); }
  }, [sector, view]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (admin) api.get('/operations/assignees').then(r => setUsers(r.data.users || [])).catch(() => {});
  }, [admin]);
  const counts = useMemo(() => ({ pending: tasks.filter(t => t.status === 'pending').length,
    overdue: tasks.filter(t => t.status === 'overdue').length }), [tasks]);
  const field = (name, value) => setForm(f => ({ ...f, [name]: value }));
  const newForm = (task) => {
    setEditingId(task?.id || null);
    setForm(task ? { title: task.title, description: task.description || '', sector: task.sector,
      task_type: task.task_type, frequency: task.frequency, due_on: task.due_on,
      due_time: task.due_time, assignee_id: task.assignee_id || '', active: task.active } : emptyTask());
    setFormOpen(true);
  };
  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form, assignee_id: form.assignee_id || null };
      if (editingId) await api.put(`/operations/tasks/${editingId}`, payload);
      else await api.post('/operations/tasks', payload);
      toast.success(editingId ? 'Tarefa atualizada' : 'Tarefa criada');
      setFormOpen(false); await refresh();
    } catch (err) { toast.error(errorText(err)); }
    finally { setSaving(false); }
  };
  const complete = async (task) => {
    if (!window.confirm(`Marcar como concluída: ${task.title}?`)) return;
    try {
      await api.post(`/operations/tasks/${task.id}/complete`, { note: '' });
      toast.success('Conclusão registrada'); await refresh();
    } catch (e) { toast.error(errorText(e)); }
  };
  const blocker = async (task) => {
    const reason = window.prompt('Por que esta tarefa não foi concluída? (mínimo 5 caracteres)');
    if (reason === null) return;
    try {
      await api.post(`/operations/tasks/${task.id}/blocker`, { note: reason.trim() });
      toast.success('Motivo salvo. A tarefa continua pendente'); await refresh();
    } catch (e) { toast.error(errorText(e)); }
  };
  const history = async (task) => {
    try { const r = await api.get(`/operations/tasks/${task.id}/history`); setEvents(r.data); }
    catch (e) { toast.error(errorText(e)); }
  };
  return (
    <Layout title="Gestão Operacional">
      <div className="space-y-5" data-testid="operational-tasks-page">
        <div className="rounded-xl border bg-card p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 font-heading font-bold text-xl"><ClipboardCheck className="w-6 h-6" /> Tarefas do EMAÚS</div>
            <p className="mt-1 text-sm text-muted-foreground">Checklists de limpeza, cozinha, bar, fritadeira, estoque, compras e manutenção. Pendências vencidas não desaparecem.</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button onClick={refresh} className="px-3 py-2 border rounded-md flex items-center gap-2" disabled={loading}><RefreshCw className="w-4 h-4" /> Atualizar</button>
            {admin && <button onClick={() => newForm(null)} className="px-3 py-2 rounded-md bg-primary text-primary-foreground flex items-center gap-2"><Plus className="w-4 h-4"/> Nova tarefa</button>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border p-3"><div className="text-sm text-muted-foreground">Pendentes nesta visualização</div><div className="text-2xl font-bold">{counts.pending}</div></div>
          <div className="rounded-lg border p-3"><div className="text-sm text-muted-foreground">Vencidas nesta visualização</div><div className="text-2xl font-bold text-red-600">{counts.overdue}</div></div>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          {admin && <label className="text-sm">Setor<select value={sector} onChange={e => setSector(e.target.value)} className="block mt-1 border rounded p-2 bg-background">{SECTORS.map(([v,n]) => <option key={v} value={v}>{n}</option>)}</select></label>}
          <label className="text-sm">Visualização<select value={view} onChange={e => setView(e.target.value)} className="block mt-1 border rounded p-2 bg-background"><option value="active">Pendentes</option><option value="done">Concluídas (únicas)</option><option value="all">Todas</option></select></label>
        </div>
        {loading ? <p className="text-muted-foreground">Carregando tarefas...</p> : tasks.length === 0 ?
          <div className="border rounded-lg p-8 text-center text-muted-foreground">Nenhuma tarefa encontrada nesse filtro.</div> :
          <div className="space-y-3">{tasks.map(t => <div className="rounded-lg border bg-card p-4 space-y-3" key={t.id}>
            <div className="flex flex-wrap justify-between gap-3">
              <div><div className="font-semibold">{t.title}</div><p className="text-sm text-muted-foreground">{t.description || 'Sem descrição'}</p></div>
              <span className={`text-xs font-medium rounded-full px-3 py-1 self-start ${statusClass(t.status)}`}>{statusText[t.status] || t.status}</span>
            </div>
            <div className="text-sm flex flex-wrap gap-x-5 gap-y-1 text-muted-foreground">
              <span>Setor: {SECTORS.find(x=>x[0]===t.sector)?.[1]}</span>
              <span>Tipo: {TYPES.find(x=>x[0]===t.task_type)?.[1]}</span>
              <span>Frequência: {FREQS.find(x=>x[0]===t.frequency)?.[1]}</span>
              <span>Vencimento: {t.due_on} às {t.due_time}</span>
              <span>Concluída {t.completed_count || 0} vez(es)</span>
              {t.assignee_id && <span>Responsável: {users.find(u => u.id === t.assignee_id)?.name || 'Designado'}</span>}
            </div>
            {t.last_event && <p className="text-xs text-muted-foreground">Último registro: {t.last_event.by_name} • {fmt(t.last_event.at)} • {t.last_event.action === 'blocker' ? 'Pendência' : 'Concluído'}{t.last_event.note ? ` — ${t.last_event.note}` : ''}</p>}
            <div className="flex gap-2 flex-wrap">
              {t.active && !t.completed && <button onClick={()=>complete(t)} className="border rounded px-3 py-2 text-sm flex gap-1 items-center hover:bg-muted"><CheckCircle2 className="w-4 h-4"/> Concluir</button>}
              {t.active && !t.completed && <button onClick={()=>blocker(t)} className="border rounded px-3 py-2 text-sm flex gap-1 items-center hover:bg-muted"><AlertTriangle className="w-4 h-4"/> Registrar impedimento</button>}
              <button onClick={()=>history(t)} className="border rounded px-3 py-2 text-sm flex gap-1 items-center hover:bg-muted"><History className="w-4 h-4"/> Histórico</button>
              {admin && !t.completed && <button onClick={()=>newForm(t)} className="border rounded px-3 py-2 text-sm flex gap-1 items-center hover:bg-muted"><Pencil className="w-4 h-4"/> Editar</button>}
            </div>
          </div>)}</div>}
        {formOpen && admin && <div className="fixed inset-0 z-[70] bg-black/50 p-3 overflow-y-auto flex items-center justify-center" role="dialog" aria-modal="true">
          <form onSubmit={save} className="bg-card border rounded-xl p-5 w-full max-w-2xl space-y-3 max-h-[95vh] overflow-y-auto">
            <h2 className="font-heading text-lg font-bold">{editingId ? 'Editar tarefa' : 'Criar tarefa'}</h2>
            <label className="block text-sm">Nome da tarefa<input required minLength={3} maxLength={120} value={form.title} onChange={e=>field('title', e.target.value)} className="w-full mt-1 border rounded p-2 bg-background" placeholder="Ex.: Higienizar chapa"/></label>
            <label className="block text-sm">Descrição<textarea maxLength={500} value={form.description} onChange={e=>field('description',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background" rows={2}/></label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-sm">Setor<select value={form.sector} onChange={e=>field('sector',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background">{SECTORS.filter(x=>x[0]!=='all').map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>
              <label className="text-sm">Categoria<select value={form.task_type} onChange={e=>field('task_type',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background">{TYPES.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>
              <label className="text-sm">Frequência<select value={form.frequency} onChange={e=>field('frequency',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background">{FREQS.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>
              <label className="text-sm">Vencimento<input type="date" required value={form.due_on} onChange={e=>field('due_on',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background"/></label>
              <label className="text-sm">Horário<input type="time" required value={form.due_time} onChange={e=>field('due_time',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background"/></label>
              <label className="text-sm">Responsável<select value={form.assignee_id} onChange={e=>field('assignee_id',e.target.value)} className="w-full mt-1 border rounded p-2 bg-background"><option value="">Equipe do setor (sem nome específico)</option>{users.filter(u=> ['admin','superadmin'].includes(u.role) || ({ kitchen:'kitchen', bar:'bar', cashier:'cashier', service:'waiter' })[form.sector] === u.role).map(u=><option value={u.id} key={u.id}>{u.name} ({u.role})</option>)}</select></label>
            </div>
            {editingId && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.active} onChange={e=>field('active',e.target.checked)}/><PauseCircle className="w-4 h-4"/> Tarefa ativa</label>}
            <div className="flex justify-end gap-2"><button type="button" className="border rounded px-4 py-2" onClick={()=>setFormOpen(false)}>Cancelar</button><button type="submit" disabled={saving} className="bg-primary text-primary-foreground rounded px-4 py-2">{saving ? 'Salvando...' : 'Salvar tarefa'}</button></div>
          </form>
        </div>}
        {events && <div className="fixed inset-0 z-[70] bg-black/50 p-3 overflow-y-auto flex justify-center items-center" role="dialog" aria-modal="true">
          <div className="bg-card border rounded-xl p-5 w-full max-w-xl space-y-3 max-h-[90vh] overflow-y-auto">
            <h2 className="font-bold text-lg">Histórico — {events.title}</h2>
            {events.events.length === 0 ? <p className="text-sm text-muted-foreground">Sem registros ainda.</p> : events.events.map(ev=><div key={ev.id} className="text-sm border-b pb-2"><b>{ev.action === 'completed' ? 'Concluída' : 'Impedimento'}</b> por {ev.by_name} em {fmt(ev.at)}<div>Ciclo: {ev.cycle_due_on}</div>{ev.note && <div>Motivo/observação: {ev.note}</div>}</div>)}
            <button className="border rounded px-4 py-2" onClick={()=>setEvents(null)}>Fechar</button>
          </div>
        </div>}
      </div>
    </Layout>
  );
}
