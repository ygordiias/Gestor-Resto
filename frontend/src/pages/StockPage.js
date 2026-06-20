import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Progress } from '../components/ui/progress';
import { stockAPI, productsAPI } from '../lib/api';
import { formatDate } from '../lib/utils';
import { toast } from 'sonner';
import { 
  Plus, 
  Pencil, 
  AlertTriangle,
  Package,
  Scale,
  Droplet
} from 'lucide-react';

export default function StockPage() {
  const [stock, setStock] = useState([]);
  const [products, setProducts] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingStock, setEditingStock] = useState(null);
  const [activeType, setActiveType] = useState('all'); // all | raw_material | semi_finished | finished_product
  const [form, setForm] = useState({
    product_id: '',
    name: '',
    category: '',
    stock_type: 'raw_material',
    quantity: '',
    unit: 'unit',
    min_quantity: '5',
    max_quantity: '100',
    unit_cost: '0',
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [stockRes, productsRes, alertsRes] = await Promise.all([
        stockAPI.getAll(),
        productsAPI.getAll(),
        stockAPI.getAlerts(),
      ]);
      setStock(stockRes.data);
      setProducts(productsRes.data);
      setAlerts(alertsRes.data);
    } catch (error) {
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  const openDialog = (stockItem = null) => {
    if (stockItem) {
      setEditingStock(stockItem);
      setForm({
        product_id: stockItem.product_id || '',
        name: stockItem.name || '',
        category: stockItem.category || '',
        stock_type: stockItem.stock_type || 'finished_product',
        quantity: stockItem.quantity.toString(),
        unit: stockItem.unit,
        min_quantity: stockItem.min_quantity.toString(),
        max_quantity: stockItem.max_quantity.toString(),
        unit_cost: (stockItem.unit_cost ?? 0).toString(),
      });
    } else {
      setEditingStock(null);
      setForm({
        product_id: '',
        name: '',
        category: '',
        stock_type: 'raw_material',
        quantity: '',
        unit: 'unit',
        min_quantity: '5',
        max_quantity: '100',
        unit_cost: '0',
      });
    }
    setIsDialogOpen(true);
  };

  const handleSave = async () => {
    // Validacao: precisa de nome OU product_id
    if (!form.product_id && !form.name?.trim()) {
      toast.error('Informe um nome para o item ou selecione um produto do cardápio');
      return;
    }
    if (!form.quantity && form.quantity !== '0') {
      toast.error('Informe a quantidade');
      return;
    }

    const data = {
      product_id: form.product_id || null,
      name: form.name?.trim() || null,
      category: form.category?.trim() || null,
      stock_type: form.stock_type || 'finished_product',
      quantity: parseFloat(form.quantity),
      unit: form.unit,
      min_quantity: parseFloat(form.min_quantity),
      max_quantity: parseFloat(form.max_quantity),
      unit_cost: parseFloat(form.unit_cost) || 0,
    };

    try {
      if (editingStock) {
        await stockAPI.update(editingStock.id, data);
        toast.success('Estoque atualizado!');
      } else {
        await stockAPI.create(data);
        toast.success('Item de estoque criado!');
      }
      setIsDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao salvar');
    }
  };

  // Resolve nome do item: prioriza stock.name, senão busca em products
  const getItemName = (stockItem) => {
    if (stockItem.name) return stockItem.name;
    const product = products.find(p => p.id === stockItem.product_id);
    return product?.name || 'Sem nome';
  };

  const getProductName = (productId) => {
    const product = products.find(p => p.id === productId);
    return product?.name || 'Produto não encontrado';
  };

  const getUnitLabel = (unit) => {
    const labels = {
      unit: 'Unidade',
      kg: 'Quilograma',
      liter: 'Litro',
      gram: 'Grama',
    };
    return labels[unit] || unit;
  };

  const getStockLevel = (item) => {
    return (item.quantity / item.max_quantity) * 100;
  };

  const getStockStatus = (item) => {
    if (item.quantity <= item.min_quantity) return 'critical';
    if (item.quantity <= item.min_quantity * 2) return 'warning';
    return 'normal';
  };

  if (loading) {
    return (
      <Layout title="Estoque">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Estoque">
      <div className="space-y-6" data-testid="stock-page">
        {/* Alerts */}
        {alerts.length > 0 && (
          <Card className="border-amber-400 bg-amber-50 dark:bg-amber-900/20">
            <CardHeader>
              <CardTitle className="font-heading flex items-center gap-2 text-amber-700 dark:text-amber-300">
                <AlertTriangle className="h-5 w-5" />
                Alertas de Estoque Baixo
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {alerts.map(alert => (
                  <Badge key={alert.id} variant="outline" className="border-amber-400 text-amber-700">
                    {getItemName(alert)}: {alert.quantity} {getUnitLabel(alert.unit)}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Actions + Filtro por tipo */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex flex-wrap gap-2 flex-1" data-testid="stock-type-filters">
            {[
              { v: 'all', l: 'Todos', icon: Package },
              { v: 'raw_material', l: 'Matéria-prima', icon: Scale },
              { v: 'semi_finished', l: 'Semi-acabado', icon: Droplet },
              { v: 'finished_product', l: 'Produto acabado', icon: Package },
            ].map(t => {
              const Ico = t.icon;
              const active = activeType === t.v;
              return (
                <Button
                  key={t.v}
                  size="sm"
                  variant={active ? 'default' : 'outline'}
                  onClick={() => setActiveType(t.v)}
                  data-testid={`filter-${t.v}`}
                >
                  <Ico className="h-3.5 w-3.5 mr-1.5" /> {t.l}
                </Button>
              );
            })}
          </div>
          <Button onClick={() => openDialog()} data-testid="add-stock-btn">
            <Plus className="h-4 w-4 mr-2" />
            Novo Item
          </Button>
        </div>

        {/* Stock List */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {stock
            .filter(it => activeType === 'all' || (it.stock_type || 'finished_product') === activeType)
            .map(item => {
            const status = getStockStatus(item);
            const level = getStockLevel(item);
            const typeLabel = {
              raw_material: 'Matéria-prima',
              semi_finished: 'Semi-acabado',
              finished_product: 'Produto acabado',
            }[item.stock_type] || 'Produto acabado';
            const typeColor = {
              raw_material: 'border-amber-500/40 text-amber-500 bg-amber-500/10',
              semi_finished: 'border-blue-500/40 text-blue-500 bg-blue-500/10',
              finished_product: 'border-emerald-500/40 text-emerald-500 bg-emerald-500/10',
            }[item.stock_type] || 'border-emerald-500/40 text-emerald-500 bg-emerald-500/10';

            return (
              <Card key={item.id} className="card-hover" data-testid={`stock-item-${item.id}`}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="font-medium truncate">{getItemName(item)}</h3>
                      <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                        <Badge variant="outline" className={`text-[10px] ${typeColor}`}>{typeLabel}</Badge>
                        {item.category && (
                          <Badge variant="outline" className="text-[10px]">{item.category}</Badge>
                        )}
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-1">
                        Atualizado em {formatDate(item.last_updated)}
                      </p>
                    </div>
                    <div className={`p-2 rounded-full shrink-0 ${
                      status === 'critical' ? 'bg-red-100 text-red-600' :
                      status === 'warning' ? 'bg-amber-100 text-amber-600' :
                      'bg-green-100 text-green-600'
                    }`}>
                      {item.unit === 'kg' || item.unit === 'gram' ? (
                        <Scale className="h-5 w-5" />
                      ) : item.unit === 'liter' ? (
                        <Droplet className="h-5 w-5" />
                      ) : (
                        <Package className="h-5 w-5" />
                      )}
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span>Quantidade</span>
                        <span className="font-bold">
                          {item.quantity} {getUnitLabel(item.unit)}
                        </span>
                      </div>
                      <Progress 
                        value={level} 
                        className={
                          status === 'critical' ? 'bg-red-200' :
                          status === 'warning' ? 'bg-amber-200' :
                          'bg-green-200'
                        }
                      />
                    </div>

                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Mín: {item.min_quantity}</span>
                      <span>Máx: {item.max_quantity}</span>
                    </div>

                    {item.unit_cost > 0 && (
                      <div className="flex justify-between items-center text-xs px-2 py-1.5 rounded-md bg-primary/10 border border-primary/20" data-testid={`stock-cost-${item.id}`}>
                        <span className="text-muted-foreground">Custo unitário</span>
                        <span className="font-semibold text-primary">
                          R$ {Number(item.unit_cost).toFixed(2).replace('.', ',')} / {getUnitLabel(item.unit).toLowerCase()}
                        </span>
                      </div>
                    )}

                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => openDialog(item)}
                      data-testid={`edit-stock-${item.id}`}
                    >
                      <Pencil className="h-4 w-4 mr-2" />
                      Ajustar Estoque
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {stock.length === 0 && (
          <div className="text-center py-12">
            <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">Nenhum item no estoque</p>
          </div>
        )}

        {/* Dialog */}
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="font-heading">
                {editingStock ? 'Ajustar Estoque' : 'Novo Item de Estoque'}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Tipo *</Label>
                <Select
                  value={form.stock_type}
                  onValueChange={(v) => setForm({ ...form, stock_type: v })}
                  disabled={!!editingStock}
                >
                  <SelectTrigger data-testid="stock-type-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="raw_material">Matéria-prima (não aparece no cardápio)</SelectItem>
                    <SelectItem value="semi_finished">Semi-acabado (item produzido)</SelectItem>
                    <SelectItem value="finished_product">Produto acabado (revenda direta)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Nome {form.product_id ? '' : '*'}</Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex: Carne Bovina, Hambúrguer 100g..."
                  data-testid="stock-name-input"
                />
                <p className="text-xs text-muted-foreground">
                  Preencha o nome para itens independentes do cardápio (matéria-prima, semi-acabado).
                </p>
              </div>

              <div className="space-y-2">
                <Label>Categoria</Label>
                <Input
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  placeholder="Ex: Carnes, Hortifruti, Bebidas..."
                  data-testid="stock-category-input"
                />
              </div>

              <div className="space-y-2">
                <Label>Produto do Cardápio (opcional)</Label>
                <Select
                  value={form.product_id || '__none__'}
                  onValueChange={(v) => setForm({ ...form, product_id: v === '__none__' ? '' : v })}
                  disabled={!!editingStock}
                >
                  <SelectTrigger data-testid="stock-product-select">
                    <SelectValue placeholder="(nenhum)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">— Sem vínculo com cardápio —</SelectItem>
                    {products.map(product => (
                      <SelectItem key={product.id} value={product.id}>
                        {product.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Use só quando o item TAMBÉM é vendido no cardápio (ex: refrigerante, água).
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Quantidade *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={form.quantity}
                    onChange={(e) => setForm({ ...form, quantity: e.target.value })}
                    data-testid="stock-quantity-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Unidade</Label>
                  <Select
                    value={form.unit}
                    onValueChange={(v) => setForm({ ...form, unit: v })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="unit">Unidade</SelectItem>
                      <SelectItem value="kg">Quilograma</SelectItem>
                      <SelectItem value="gram">Grama</SelectItem>
                      <SelectItem value="liter">Litro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Quantidade Mínima</Label>
                  <Input
                    type="number"
                    value={form.min_quantity}
                    onChange={(e) => setForm({ ...form, min_quantity: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Quantidade Máxima</Label>
                  <Input
                    type="number"
                    value={form.max_quantity}
                    onChange={(e) => setForm({ ...form, max_quantity: e.target.value })}
                  />
                </div>
              </div>
              <div className="space-y-2 border-t pt-4">
                <Label className="flex items-center gap-2">
                  Custo Unitário (R$) <span className="text-xs text-muted-foreground">— usado no cálculo de CMV</span>
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.unit_cost}
                  onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
                  placeholder="0,00"
                  data-testid="stock-unit-cost-input"
                />
                <p className="text-xs text-muted-foreground">
                  Valor pago por 1 {getUnitLabel(form.unit).toLowerCase()} deste item.
                </p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleSave} data-testid="save-stock-btn">
                Salvar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
