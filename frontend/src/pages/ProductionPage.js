import React, { useState, useEffect, useMemo } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Badge } from '../components/ui/badge';
import { productionsAPI, stockAPI, productsAPI } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/utils';
import { toast } from 'sonner';
import {
  Plus, Trash2, Factory, Boxes, CircleDollarSign,
  Loader2, ArrowDown, ArrowUp, Calculator,
} from 'lucide-react';

export default function ProductionPage() {
  const [stockItems, setStockItems] = useState([]);
  const [productsById, setProductsById] = useState({});
  const [productions, setProductions] = useState([]);
  const [dashboard, setDashboard] = useState({ rows: [], total_productions: 0, total_produced_cost: 0 });
  const [loading, setLoading] = useState(true);

  // Form
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    produced_stock_item_id: '',
    quantity: '',
    notes: '',
    ingredients: [{ stock_item_id: '', quantity: '' }],
  });

  const loadAll = async () => {
    setLoading(true);
    try {
      const [stockRes, prodRes, listRes, dashRes] = await Promise.all([
        stockAPI.getAll(),
        productsAPI.getAll(),
        productionsAPI.getAll(),
        productionsAPI.getDashboard(),
      ]);
      const pById = Object.fromEntries(prodRes.data.map(p => [p.id, p]));
      setProductsById(pById);
      const items = stockRes.data.map(s => ({
        ...s,
        product_name: pById[s.product_id]?.name || s.product_id,
      })).sort((a, b) => a.product_name.localeCompare(b.product_name));
      setStockItems(items);
      setProductions(listRes.data || []);
      setDashboard(dashRes.data || { rows: [], total_productions: 0, total_produced_cost: 0 });
    } catch (e) {
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  const openDialog = () => {
    setForm({
      produced_stock_item_id: '',
      quantity: '',
      notes: '',
      ingredients: [{ stock_item_id: '', quantity: '' }],
    });
    setOpen(true);
  };

  const addIng = () => setForm(f => ({ ...f, ingredients: [...f.ingredients, { stock_item_id: '', quantity: '' }] }));
  const removeIng = (idx) => setForm(f => ({ ...f, ingredients: f.ingredients.filter((_, i) => i !== idx) }));
  const updateIng = (idx, field, value) => {
    setForm(f => ({
      ...f,
      ingredients: f.ingredients.map((it, i) => i === idx ? { ...it, [field]: value } : it),
    }));
  };

  // Custo total em tempo real
  const totalCost = useMemo(() => {
    let t = 0;
    for (const ing of form.ingredients) {
      const s = stockItems.find(x => x.id === ing.stock_item_id);
      const q = parseFloat(ing.quantity) || 0;
      if (s) t += q * Number(s.unit_cost || 0);
    }
    return t;
  }, [form.ingredients, stockItems]);

  const qty = parseFloat(form.quantity) || 0;
  const unitCost = qty > 0 ? totalCost / qty : 0;

  const handleSave = async () => {
    if (!form.produced_stock_item_id || qty <= 0) {
      toast.error('Selecione o item produzido e a quantidade');
      return;
    }
    const items = form.ingredients
      .filter(i => i.stock_item_id && parseFloat(i.quantity) > 0)
      .map(i => ({ stock_item_id: i.stock_item_id, quantity: parseFloat(i.quantity) }));
    if (items.length === 0) {
      toast.error('Adicione pelo menos 1 ingrediente consumido');
      return;
    }
    setSaving(true);
    try {
      await productionsAPI.create({
        produced_stock_item_id: form.produced_stock_item_id,
        quantity: qty,
        notes: form.notes,
        ingredients: items,
      });
      toast.success('Produção registrada com sucesso!');
      setOpen(false);
      await loadAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao salvar produção');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Layout title="Produção">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Produção">
      <div className="space-y-6" data-testid="production-page">
        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <Card data-testid="prod-stat-total">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/15 p-2.5"><Factory className="h-5 w-5 text-primary" /></div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Produções</p>
                  <p className="text-xl font-bold font-heading">{dashboard.total_productions}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card data-testid="prod-stat-cost">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-amber-400/15 p-2.5"><CircleDollarSign className="h-5 w-5 text-amber-400" /></div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Custo total produzido</p>
                  <p className="text-xl font-bold font-heading">{formatCurrency(dashboard.total_produced_cost)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card data-testid="prod-stat-items">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-emerald-500/15 p-2.5"><Boxes className="h-5 w-5 text-emerald-500" /></div>
                <div>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Itens monitorados</p>
                  <p className="text-xl font-bold font-heading">{dashboard.rows.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Botao Nova Producao */}
        <div className="flex justify-end">
          <Button onClick={openDialog} data-testid="new-production-btn">
            <Plus className="h-4 w-4 mr-2" /> Nova Produção
          </Button>
        </div>

        {/* Dashboard table: produzido / vendido / estoque */}
        <Card>
          <CardHeader><CardTitle className="font-heading text-lg">Resumo de Produção × Consumo</CardTitle></CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm" data-testid="production-summary-table">
              <thead className="bg-muted/40">
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 font-heading font-semibold">Item</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Produzido</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Consumido</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Estoque Atual</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Custo unitário</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Custo total</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.rows.length === 0 ? (
                  <tr><td colSpan={6} className="text-center py-8 text-muted-foreground">Nenhuma produção registrada ainda</td></tr>
                ) : dashboard.rows.map(r => (
                  <tr key={r.stock_item_id} className="border-b border-border/50 hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">{r.name}</td>
                    <td className="px-4 py-3 text-right text-emerald-500"><ArrowUp className="h-3 w-3 inline" /> {r.produced}</td>
                    <td className="px-4 py-3 text-right text-destructive"><ArrowDown className="h-3 w-3 inline" /> {r.consumed}</td>
                    <td className="px-4 py-3 text-right font-bold">{r.current_stock}</td>
                    <td className="px-4 py-3 text-right">{formatCurrency(r.unit_cost)}</td>
                    <td className="px-4 py-3 text-right">{formatCurrency(r.total_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Histórico de produções */}
        <Card>
          <CardHeader><CardTitle className="font-heading text-lg">Histórico de Produções</CardTitle></CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm" data-testid="productions-history-table">
              <thead className="bg-muted/40">
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 font-heading font-semibold">Data</th>
                  <th className="text-left px-4 py-3 font-heading font-semibold">Produto</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Quantidade</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Custo</th>
                  <th className="text-left px-4 py-3 font-heading font-semibold">Responsável</th>
                  <th className="text-left px-4 py-3 font-heading font-semibold">Observação</th>
                </tr>
              </thead>
              <tbody>
                {productions.length === 0 ? (
                  <tr><td colSpan={6} className="text-center py-8 text-muted-foreground">Nenhuma produção registrada</td></tr>
                ) : productions.map(p => (
                  <tr key={p.id} className="border-b border-border/50 hover:bg-muted/30" data-testid={`production-row-${p.id}`}>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(p.created_at)}</td>
                    <td className="px-4 py-3 font-medium">{p.produced_product_name}</td>
                    <td className="px-4 py-3 text-right">
                      <Badge variant="outline" className="text-emerald-500 border-emerald-500/30">+{p.quantity}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold">{formatCurrency(p.total_cost)}</td>
                    <td className="px-4 py-3 text-xs">{p.user_name || '—'}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{p.notes || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Dialog Nova Produção */}
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="production-dialog">
            <DialogHeader>
              <DialogTitle className="font-heading flex items-center gap-2">
                <Factory className="h-5 w-5 text-primary" /> Registrar Produção
              </DialogTitle>
            </DialogHeader>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Item Produzido (saída) *</Label>
                  <Select value={form.produced_stock_item_id} onValueChange={v => setForm(f => ({ ...f, produced_stock_item_id: v }))}>
                    <SelectTrigger data-testid="produced-select">
                      <SelectValue placeholder="Selecione o item..." />
                    </SelectTrigger>
                    <SelectContent>
                      {stockItems.map(s => (
                        <SelectItem key={s.id} value={s.id}>{s.product_name} · {s.unit}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Quantidade produzida *</Label>
                  <Input
                    type="number" step="0.01" min="0"
                    value={form.quantity}
                    onChange={e => setForm(f => ({ ...f, quantity: e.target.value }))}
                    data-testid="production-qty-input"
                  />
                </div>
              </div>

              {/* Resumo */}
              <div className="grid grid-cols-3 gap-2 p-3 rounded-lg bg-muted/40 border border-border" data-testid="production-summary">
                <div className="text-center">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Custo total</p>
                  <p className="text-sm font-bold">{formatCurrency(totalCost)}</p>
                </div>
                <div className="text-center">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Quantidade</p>
                  <p className="text-sm font-bold">{qty}</p>
                </div>
                <div className="text-center">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Custo por unidade</p>
                  <p className="text-sm font-bold text-primary">{formatCurrency(unitCost)}</p>
                </div>
              </div>

              {/* Ingredientes */}
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Calculator className="h-4 w-4" /> Ingredientes consumidos
                </Label>
                {form.ingredients.map((ing, idx) => {
                  const s = stockItems.find(x => x.id === ing.stock_item_id);
                  const q = parseFloat(ing.quantity) || 0;
                  const line = s ? q * Number(s.unit_cost || 0) : 0;
                  return (
                    <div key={idx} className="flex gap-2 items-center" data-testid={`ing-row-${idx}`}>
                      <Select value={ing.stock_item_id} onValueChange={v => updateIng(idx, 'stock_item_id', v)}>
                        <SelectTrigger className="flex-1"><SelectValue placeholder="Item do estoque..." /></SelectTrigger>
                        <SelectContent>
                          {stockItems
                            .filter(s2 => s2.id !== form.produced_stock_item_id)
                            .map(s2 => (
                              <SelectItem key={s2.id} value={s2.id}>
                                {s2.product_name} · R$ {Number(s2.unit_cost || 0).toFixed(2)}/{s2.unit} · saldo {s2.quantity}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                      <Input
                        type="number" step="0.01" min="0" placeholder="Qtd"
                        value={ing.quantity}
                        onChange={e => updateIng(idx, 'quantity', e.target.value)}
                        className="w-24"
                        data-testid={`ing-qty-${idx}`}
                      />
                      <div className="w-24 text-right text-xs text-muted-foreground">{s ? formatCurrency(line) : ''}</div>
                      <Button type="button" size="icon" variant="ghost" onClick={() => removeIng(idx)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  );
                })}
                <Button type="button" variant="outline" onClick={addIng} className="w-full" data-testid="add-ing-btn">
                  <Plus className="h-4 w-4 mr-2" /> Adicionar Ingrediente
                </Button>
              </div>

              <div className="space-y-2">
                <Label>Observação</Label>
                <Textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  placeholder="Lote, validade, observações..."
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancelar</Button>
              <Button onClick={handleSave} disabled={saving} data-testid="save-production-btn">
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Factory className="h-4 w-4 mr-2" />}
                Registrar Produção
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
