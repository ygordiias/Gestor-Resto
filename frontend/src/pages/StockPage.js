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
  const [form, setForm] = useState({
    product_id: '',
    quantity: '',
    unit: 'unit',
    min_quantity: '5',
    max_quantity: '100',
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
        product_id: stockItem.product_id,
        quantity: stockItem.quantity.toString(),
        unit: stockItem.unit,
        min_quantity: stockItem.min_quantity.toString(),
        max_quantity: stockItem.max_quantity.toString(),
      });
    } else {
      setEditingStock(null);
      setForm({
        product_id: '',
        quantity: '',
        unit: 'unit',
        min_quantity: '5',
        max_quantity: '100',
      });
    }
    setIsDialogOpen(true);
  };

  const handleSave = async () => {
    if (!form.product_id || !form.quantity) {
      toast.error('Preencha os campos obrigatórios');
      return;
    }

    const data = {
      product_id: form.product_id,
      quantity: parseFloat(form.quantity),
      unit: form.unit,
      min_quantity: parseFloat(form.min_quantity),
      max_quantity: parseFloat(form.max_quantity),
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
      toast.error('Erro ao salvar');
    }
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
                    {getProductName(alert.product_id)}: {alert.quantity} {getUnitLabel(alert.unit)}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Actions */}
        <div className="flex justify-end">
          <Button onClick={() => openDialog()} data-testid="add-stock-btn">
            <Plus className="h-4 w-4 mr-2" />
            Novo Item
          </Button>
        </div>

        {/* Stock List */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {stock.map(item => {
            const status = getStockStatus(item);
            const level = getStockLevel(item);
            
            return (
              <Card key={item.id} className="card-hover" data-testid={`stock-item-${item.id}`}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="font-medium">{getProductName(item.product_id)}</h3>
                      <p className="text-sm text-muted-foreground">
                        Atualizado em {formatDate(item.last_updated)}
                      </p>
                    </div>
                    <div className={`p-2 rounded-full ${
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
                <Label>Produto *</Label>
                <Select
                  value={form.product_id}
                  onValueChange={(v) => setForm({ ...form, product_id: v })}
                  disabled={!!editingStock}
                >
                  <SelectTrigger data-testid="stock-product-select">
                    <SelectValue placeholder="Selecione o produto" />
                  </SelectTrigger>
                  <SelectContent>
                    {products.map(product => (
                      <SelectItem key={product.id} value={product.id}>
                        {product.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
