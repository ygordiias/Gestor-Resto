// Configurações › Promoções: lista, status (ativa, agendada, encerrada, desligada) e formulário.
// Só admin chega aqui (a rota do servidor também recusa quem não é admin).
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { categoriesAPI, productsAPI, promotionsAPI } from '../lib/api';
import { apiError } from '../lib/billing';
import { formatCurrency } from '../lib/utils';
import { toast } from 'sonner';
import { Loader2, Pencil, Plus, Tag } from 'lucide-react';

const WEEKDAYS = [
  [1, 'Seg'], [2, 'Ter'], [3, 'Qua'], [4, 'Qui'], [5, 'Sex'], [6, 'Sáb'], [7, 'Dom'],
];
const CHANNELS = [['salao', 'Salão'], ['balcao', 'Balcão'], ['cardapio', 'Cardápio próprio']];
const STATUS = {
  ativa: { label: 'Ativa', className: 'bg-emerald-600 hover:bg-emerald-600' },
  agendada: { label: 'Agendada', className: 'bg-blue-600 hover:bg-blue-600' },
  encerrada: { label: 'Encerrada', className: 'bg-slate-500 hover:bg-slate-500' },
  desligada: { label: 'Desligada', className: 'bg-slate-300 text-slate-800 hover:bg-slate-300' },
};

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

const emptyForm = () => ({
  name: '', discount_type: 'percent', discount_value: '', category_ids: [], product_ids: [],
  start_date: today(), end_date: today(), weekdays: [], use_hours: false, start_time: '19:00',
  end_time: '21:00', channels: ['salao', 'balcao', 'cardapio'],
});

const toggle = (list, value) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

function discountLabel(p) {
  return p.discount_type === 'percent'
    ? `${Number(p.discount_value).toLocaleString('pt-BR')}%`
    : `${formatCurrency(p.discount_value)} por unidade`;
}

export default function PromotionsPanel() {
  const [promos, setPromos] = useState([]);
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null); // null = fechado
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [productSearch, setProductSearch] = useState('');

  const load = useCallback(async () => {
    try {
      const [p, c, pr] = await Promise.all([promotionsAPI.list(), categoriesAPI.getAll(), productsAPI.getAll()]);
      setPromos(p.data || []);
      setCategories(c.data || []);
      setProducts(pr.data || []);
    } catch (e) {
      toast.error(apiError(e, 'Erro ao carregar promoções'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const names = useMemo(() => ({
    category: Object.fromEntries(categories.map((c) => [c.id, c.name])),
    product: Object.fromEntries(products.map((p) => [p.id, p.name])),
  }), [categories, products]);

  const field = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const startNew = () => {
    setEditingId(null);
    setForm(emptyForm());
    setProductSearch('');
  };

  const startEdit = (p) => {
    setEditingId(p.id);
    setForm({
      ...emptyForm(), ...p, discount_value: String(p.discount_value),
      use_hours: Boolean(p.start_time && p.end_time),
      start_time: p.start_time || '19:00', end_time: p.end_time || '21:00',
    });
    setProductSearch('');
  };

  const save = async () => {
    const value = parseFloat(String(form.discount_value).replace(',', '.'));
    const payload = {
      name: form.name.trim(), discount_type: form.discount_type, discount_value: Number.isFinite(value) ? value : 0,
      category_ids: form.category_ids, product_ids: form.product_ids,
      start_date: form.start_date, end_date: form.end_date, weekdays: form.weekdays,
      start_time: form.use_hours ? form.start_time : null, end_time: form.use_hours ? form.end_time : null,
      channels: form.channels,
    };
    setSaving(true);
    try {
      if (editingId) await promotionsAPI.update(editingId, payload);
      else await promotionsAPI.create(payload);
      toast.success(editingId ? 'Promoção atualizada' : 'Promoção criada');
      setForm(null);
      await load();
    } catch (e) {
      toast.error(apiError(e, 'Erro ao salvar a promoção'));
    } finally {
      setSaving(false);
    }
  };

  const setActive = async (p, isActive) => {
    try {
      await promotionsAPI.setActive(p.id, isActive);
      toast.success(isActive ? `"${p.name}" ligada` : `"${p.name}" desligada (itens já lançados mantêm o desconto)`);
      await load();
    } catch (e) {
      toast.error(apiError(e, 'Erro ao ligar/desligar'));
    }
  };

  if (loading) {
    return <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;
  }

  const visibleProducts = products.filter((p) => p.name?.toLowerCase().includes(productSearch.toLowerCase()));

  return (
    <div className="space-y-4" data-testid="promotions-panel">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
          <div>
            <CardTitle className="font-heading flex items-center gap-2"><Tag className="h-5 w-5" />Promoções</CardTitle>
            <CardDescription>
              Vale para os itens lançados enquanto a promoção estiver ativa. Nunca vale para NostFood/iFood/99.
              Mais de uma para o mesmo item: vale a de maior desconto.
            </CardDescription>
          </div>
          {!form && (
            <Button onClick={startNew} data-testid="promotion-new-btn"><Plus className="h-4 w-4 mr-2" />Nova</Button>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {promos.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma promoção cadastrada.</p>}
          {promos.map((p) => {
            const st = STATUS[p.status] || STATUS.desligada;
            const scope = [
              ...(p.category_ids || []).map((id) => names.category[id] || 'categoria removida'),
              ...(p.product_ids || []).map((id) => names.product[id] || 'produto removido'),
            ].join(', ');
            return (
              <div key={p.id} className="flex flex-col sm:flex-row sm:items-center gap-2 rounded border p-3"
                data-testid={`promotion-row-${p.id}`}>
                <div className="flex-1 min-w-0 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{p.name}</span>
                    <Badge className={st.className}>{st.label}</Badge>
                    {p.status === 'ativa' && !p.applies_now && (
                      <Badge variant="outline">fora do horário agora</Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {discountLabel(p)} · {scope || '—'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {p.start_date.split('-').reverse().join('/')} a {p.end_date.split('-').reverse().join('/')}
                    {' · '}{p.schedule_label}
                    {' · '}{(p.channels || []).map((c) => CHANNELS.find(([k]) => k === c)?.[1] || c).join(', ')}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-2 text-xs">
                    <Switch checked={Boolean(p.is_active)} onCheckedChange={(v) => setActive(p, v)}
                      data-testid={`promotion-toggle-${p.id}`} />
                    {p.is_active ? 'Ligada' : 'Desligada'}
                  </label>
                  <Button size="sm" variant="outline" onClick={() => startEdit(p)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />Editar
                  </Button>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {form && (
        <Card data-testid="promotion-form">
          <CardHeader>
            <CardTitle className="font-heading">{editingId ? 'Editar promoção' : 'Nova promoção'}</CardTitle>
            {editingId && (
              <CardDescription>Itens já lançados não mudam: guardam a promoção que tiveram.</CardDescription>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid sm:grid-cols-3 gap-3">
              <div className="space-y-1 sm:col-span-1">
                <Label>Nome</Label>
                <Input value={form.name} onChange={(e) => field('name', e.target.value)} placeholder="Drinks 50%"
                  data-testid="promotion-name" />
              </div>
              <div className="space-y-1">
                <Label>Desconto</Label>
                <Select value={form.discount_type} onValueChange={(v) => field('discount_type', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">%</SelectItem>
                    <SelectItem value="value">R$ por unidade</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>{form.discount_type === 'percent' ? 'Percentual' : 'Valor (R$)'}</Label>
                <Input type="number" min="0" step="0.01" value={form.discount_value}
                  onChange={(e) => field('discount_value', e.target.value)} data-testid="promotion-value" />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Categorias</Label>
              <div className="flex flex-wrap gap-2">
                {categories.map((c) => (
                  <Button key={c.id} type="button" size="sm"
                    variant={form.category_ids.includes(c.id) ? 'default' : 'outline'}
                    onClick={() => field('category_ids', toggle(form.category_ids, c.id))}
                    data-testid={`promotion-category-${c.id}`}>
                    {c.name}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Produtos escolhidos (opcional, além das categorias)</Label>
              <Input placeholder="Buscar produto" value={productSearch} onChange={(e) => setProductSearch(e.target.value)} />
              <div className="max-h-40 overflow-y-auto rounded border p-2 grid sm:grid-cols-2 gap-1">
                {visibleProducts.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.product_ids.includes(p.id)}
                      onChange={() => field('product_ids', toggle(form.product_ids, p.id))} />
                    <span className="truncate">{p.name} · {formatCurrency(p.price)}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Início</Label>
                <Input type="date" value={form.start_date} onChange={(e) => field('start_date', e.target.value)}
                  data-testid="promotion-start" />
              </div>
              <div className="space-y-1">
                <Label>Fim</Label>
                <Input type="date" value={form.end_date} onChange={(e) => field('end_date', e.target.value)}
                  data-testid="promotion-end" />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Dias da semana (nenhum marcado = todos)</Label>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS.map(([d, label]) => (
                  <Button key={d} type="button" size="sm" variant={form.weekdays.includes(d) ? 'default' : 'outline'}
                    onClick={() => field('weekdays', toggle(form.weekdays, d).sort())}>
                    {label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={form.use_hours} onCheckedChange={(v) => field('use_hours', v)} />
                Só numa faixa de horário
              </label>
              {form.use_hours && (
                <div className="grid grid-cols-2 gap-3 max-w-xs">
                  <Input type="time" value={form.start_time} onChange={(e) => field('start_time', e.target.value)} />
                  <Input type="time" value={form.end_time} onChange={(e) => field('end_time', e.target.value)} />
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label>Canais</Label>
              <div className="flex flex-wrap gap-4">
                {CHANNELS.map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.channels.includes(key)}
                      onChange={() => field('channels', toggle(form.channels, key))} />
                    {label}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">NostFood, iFood e 99 nunca recebem promoção.</p>
            </div>

            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setForm(null)} disabled={saving}>Cancelar</Button>
              <Button onClick={save} disabled={saving} data-testid="promotion-save">
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
