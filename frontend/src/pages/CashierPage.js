import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { ScrollArea } from '../components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { ordersAPI, cashRegisterAPI, tablesAPI, invoicesAPI } from '../lib/api';
import { cn, formatCurrency, getStatusLabel, formatDate, getPaymentMethodLabel } from '../lib/utils';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import { 
  CreditCard, 
  DollarSign, 
  Receipt, 
  X, 
  Plus, 
  Minus,
  Wallet,
  QrCode,
  Banknote,
  Gift,
  FileText
} from 'lucide-react';

const paymentMethods = [
  { value: 'cash', label: 'Dinheiro', icon: Banknote },
  { value: 'card', label: 'Cartão', icon: CreditCard },
  { value: 'pix', label: 'PIX', icon: QrCode },
  { value: 'voucher', label: 'Vale', icon: Gift },
];

export default function CashierPage() {
  const [orders, setOrders] = useState([]);
  const [tables, setTables] = useState([]);
  const [register, setRegister] = useState(null);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openRegisterAmount, setOpenRegisterAmount] = useState('');
  const [movementAmount, setMovementAmount] = useState('');
  const [movementReason, setMovementReason] = useState('');

  useEffect(() => {
    let isMounted = true;
    
    const handleOrderClosed = () => {
      if (isMounted) fetchDataSafe();
    };
    const handleTablesUpdate = () => {
      if (isMounted) fetchDataSafe();
    };

    const fetchDataSafe = async () => {
      if (!isMounted) return;
      try {
        const [ordersRes, tablesRes, registerRes] = await Promise.all([
          ordersAPI.getOpen(),
          tablesAPI.getAll(),
          cashRegisterAPI.getCurrent(),
        ]);

        if (isMounted) {
          setOrders(ordersRes.data);
          setTables(tablesRes.data);
          setRegister(registerRes.data);
        }
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchDataSafe();
    socketService.connect();
    socketService.on('order_closed', handleOrderClosed);
    socketService.on('tables_updated', handleTablesUpdate);

    return () => {
      isMounted = false;
      socketService.off('order_closed');
      socketService.off('tables_updated');
    };
  }, []);

  const handleOpenRegister = async () => {
    if (!openRegisterAmount || parseFloat(openRegisterAmount) < 0) {
      toast.error('Informe o valor inicial do caixa');
      return;
    }

    try {
      await cashRegisterAPI.open({
        opened_by: 'Operador',
        initial_amount: parseFloat(openRegisterAmount),
      });
      toast.success('Caixa aberto com sucesso!');
      setOpenRegisterAmount('');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao abrir caixa');
    }
  };

  const handleCloseRegister = async () => {
    if (orders.length > 0) {
      toast.error('Feche todas as comandas antes de fechar o caixa');
      return;
    }

    try {
      const result = await cashRegisterAPI.close({ closed_by: 'Operador' });
      toast.success(`Caixa fechado! Valor final: ${formatCurrency(result.data.final_amount)}`);
      fetchData();
    } catch (error) {
      toast.error('Erro ao fechar caixa');
    }
  };

  const handleWithdrawal = async () => {
    if (!movementAmount || !movementReason) {
      toast.error('Preencha valor e motivo');
      return;
    }

    try {
      await cashRegisterAPI.withdrawal({
        amount: parseFloat(movementAmount),
        reason: movementReason,
      });
      toast.success('Sangria registrada');
      setMovementAmount('');
      setMovementReason('');
      fetchData();
    } catch (error) {
      toast.error('Erro ao registrar sangria');
    }
  };

  const handleDeposit = async () => {
    if (!movementAmount || !movementReason) {
      toast.error('Preencha valor e motivo');
      return;
    }

    try {
      await cashRegisterAPI.deposit({
        amount: parseFloat(movementAmount),
        reason: movementReason,
      });
      toast.success('Reforço registrado');
      setMovementAmount('');
      setMovementReason('');
      fetchData();
    } catch (error) {
      toast.error('Erro ao registrar reforço');
    }
  };

  const selectOrder = (order) => {
    setSelectedOrder(order);
    setPayments([{ method: 'cash', amount: order.total }]);
  };

  const addPayment = () => {
    setPayments([...payments, { method: 'cash', amount: 0 }]);
  };

  const updatePayment = (index, field, value) => {
    const newPayments = [...payments];
    newPayments[index][field] = field === 'amount' ? parseFloat(value) || 0 : value;
    setPayments(newPayments);
  };

  const removePayment = (index) => {
    setPayments(payments.filter((_, i) => i !== index));
  };

  const getTotalPayments = () => payments.reduce((sum, p) => sum + p.amount, 0);

  const handleCloseOrder = async () => {
    if (!selectedOrder) return;

    const totalPayments = getTotalPayments();
    if (totalPayments < selectedOrder.total) {
      toast.error('Valor dos pagamentos insuficiente');
      return;
    }

    try {
      await ordersAPI.close(selectedOrder.id, payments);
      toast.success('Comanda fechada com sucesso!');
      
      // Ask if want to emit invoice
      const emitInvoice = window.confirm('Deseja emitir Nota Fiscal?');
      if (emitInvoice) {
        await invoicesAPI.create({ order_id: selectedOrder.id });
        toast.success('NF-e criada (MOCK)');
      }
      
      setSelectedOrder(null);
      setPayments([]);
      fetchData();
    } catch (error) {
      toast.error('Erro ao fechar comanda');
    }
  };

  if (loading) {
    return (
      <Layout title="Caixa">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  // No register open
  if (!register) {
    return (
      <Layout title="Caixa">
        <div className="max-w-md mx-auto" data-testid="cashier-page">
          <Card>
            <CardHeader>
              <CardTitle className="font-heading text-center">
                Abrir Caixa
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Valor inicial do caixa</Label>
                <Input
                  type="number"
                  placeholder="0,00"
                  value={openRegisterAmount}
                  onChange={(e) => setOpenRegisterAmount(e.target.value)}
                  data-testid="open-register-amount"
                />
              </div>
              <Button
                className="w-full font-heading uppercase tracking-widest"
                onClick={handleOpenRegister}
                data-testid="open-register-btn"
              >
                Abrir Caixa
              </Button>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Caixa">
      <div className="space-y-6" data-testid="cashier-page">
        {/* Register Status */}
        <Card className="bg-primary/10 border-primary">
          <CardContent className="p-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Valor Inicial</p>
                <p className="text-lg font-bold">{formatCurrency(register.initial_amount)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Vendas</p>
                <p className="text-lg font-bold text-green-600">{formatCurrency(register.total_sales)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Sangrias</p>
                <p className="text-lg font-bold text-red-600">-{formatCurrency(register.withdrawals)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Reforços</p>
                <p className="text-lg font-bold text-blue-600">+{formatCurrency(register.deposits)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Saldo Atual</p>
                <p className="text-xl font-heading font-bold text-primary">
                  {formatCurrency(
                    register.initial_amount + register.total_sales + register.deposits - register.withdrawals
                  )}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Open Orders */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="font-heading">Comandas Abertas</CardTitle>
              </CardHeader>
              <CardContent>
                {orders.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">
                    Nenhuma comanda aberta
                  </p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {orders.map((order) => (
                      <Card
                        key={order.id}
                        className={cn(
                          'cursor-pointer card-hover',
                          selectedOrder?.id === order.id && 'ring-2 ring-primary'
                        )}
                        onClick={() => selectOrder(order)}
                        data-testid={`order-card-${order.id}`}
                      >
                        <CardContent className="p-4">
                          <div className="flex justify-between items-center mb-2">
                            <Badge variant="outline" className="font-heading text-lg">
                              Mesa {order.table_number}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {formatDate(order.created_at)}
                            </span>
                          </div>
                          <div className="space-y-1 mb-2">
                            {order.items.slice(0, 3).map((item, idx) => (
                              <div key={idx} className="flex justify-between text-sm">
                                <span>{item.quantity}x {item.product_name}</span>
                                <span>{formatCurrency(item.unit_price * item.quantity)}</span>
                              </div>
                            ))}
                            {order.items.length > 3 && (
                              <p className="text-xs text-muted-foreground">
                                +{order.items.length - 3} itens...
                              </p>
                            )}
                          </div>
                          <div className="pt-2 border-t flex justify-between">
                            <span className="font-medium">Total:</span>
                            <span className="text-lg font-bold text-primary">
                              {formatCurrency(order.total)}
                            </span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Payment Panel */}
          <div>
            {selectedOrder ? (
              <Card className="sticky top-24">
                <CardHeader>
                  <div className="flex justify-between items-center">
                    <CardTitle className="font-heading">
                      Mesa {selectedOrder.table_number}
                    </CardTitle>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setSelectedOrder(null)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Order Details */}
                  <ScrollArea className="h-48 border rounded p-2">
                    {selectedOrder.items.map((item, idx) => (
                      <div key={idx} className="flex justify-between text-sm py-1">
                        <span>{item.quantity}x {item.product_name}</span>
                        <span>{formatCurrency(item.unit_price * item.quantity)}</span>
                      </div>
                    ))}
                  </ScrollArea>

                  {/* Totals */}
                  <div className="space-y-2 border-t pt-2">
                    <div className="flex justify-between text-sm">
                      <span>Subtotal:</span>
                      <span>{formatCurrency(selectedOrder.subtotal)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span>Taxa de Serviço ({selectedOrder.service_fee_percentage}%):</span>
                      <span>{formatCurrency(selectedOrder.service_fee)}</span>
                    </div>
                    <div className="flex justify-between font-bold text-lg">
                      <span>Total:</span>
                      <span className="text-primary">{formatCurrency(selectedOrder.total)}</span>
                    </div>
                  </div>

                  {/* Payment Methods */}
                  <div className="space-y-2">
                    <Label>Formas de Pagamento</Label>
                    {payments.map((payment, idx) => (
                      <div key={idx} className="flex gap-2">
                        <Select
                          value={payment.method}
                          onValueChange={(v) => updatePayment(idx, 'method', v)}
                        >
                          <SelectTrigger className="w-32">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {paymentMethods.map((m) => (
                              <SelectItem key={m.value} value={m.value}>
                                {m.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <Input
                          type="number"
                          value={payment.amount}
                          onChange={(e) => updatePayment(idx, 'amount', e.target.value)}
                          className="flex-1"
                        />
                        {payments.length > 1 && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => removePayment(idx)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    ))}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={addPayment}
                      className="w-full"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Dividir Pagamento
                    </Button>
                  </div>

                  {/* Payment Total */}
                  <div className="flex justify-between font-bold">
                    <span>Total Pagamentos:</span>
                    <span className={cn(
                      getTotalPayments() >= selectedOrder.total ? 'text-green-600' : 'text-red-600'
                    )}>
                      {formatCurrency(getTotalPayments())}
                    </span>
                  </div>

                  {/* Change */}
                  {getTotalPayments() > selectedOrder.total && (
                    <div className="flex justify-between text-lg bg-muted p-2 rounded">
                      <span>Troco:</span>
                      <span className="font-bold">
                        {formatCurrency(getTotalPayments() - selectedOrder.total)}
                      </span>
                    </div>
                  )}

                  <Button
                    className="w-full font-heading uppercase tracking-widest"
                    onClick={handleCloseOrder}
                    disabled={getTotalPayments() < selectedOrder.total}
                    data-testid="close-order-btn"
                  >
                    <Receipt className="h-4 w-4 mr-2" />
                    Fechar Comanda
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle className="font-heading">Operações</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground text-center">
                    Selecione uma comanda para fechar
                  </p>

                  <div className="space-y-4 pt-4 border-t">
                    <div className="space-y-2">
                      <Label>Sangria / Reforço</Label>
                      <Input
                        type="number"
                        placeholder="Valor"
                        value={movementAmount}
                        onChange={(e) => setMovementAmount(e.target.value)}
                      />
                      <Input
                        placeholder="Motivo"
                        value={movementReason}
                        onChange={(e) => setMovementReason(e.target.value)}
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <Button
                          variant="outline"
                          onClick={handleWithdrawal}
                          className="text-red-600"
                        >
                          <Minus className="h-4 w-4 mr-2" />
                          Sangria
                        </Button>
                        <Button
                          variant="outline"
                          onClick={handleDeposit}
                          className="text-green-600"
                        >
                          <Plus className="h-4 w-4 mr-2" />
                          Reforço
                        </Button>
                      </div>
                    </div>

                    <Button
                      variant="destructive"
                      className="w-full"
                      onClick={handleCloseRegister}
                      data-testid="close-register-btn"
                    >
                      Fechar Caixa
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}
