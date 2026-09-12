import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { ScrollArea } from '../components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../components/ui/dialog';
import { ordersAPI, cashRegisterAPI, tablesAPI, invoicesAPI } from '../lib/api';
import { cn, formatCurrency, formatDate } from '../lib/utils';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import { 
  CreditCard, 
  Receipt, 
  X, 
  Plus, 
  Minus,
  QrCode,
  Banknote,
  Gift,
  Sparkles
} from 'lucide-react';

const PAYMENT_METHODS = [
  { value: 'cash', label: 'Dinheiro', icon: Banknote },
  { value: 'card', label: 'Cartão', icon: CreditCard },
  { value: 'pix', label: 'PIX', icon: QrCode },
  { value: 'voucher', label: 'Vale', icon: Gift },
];

// Componente de pagamento com estado controlado
function PaymentRow({ payment, index, onUpdate, onRemove, canRemove }) {
  const handleMethodChange = useCallback((value) => {
    onUpdate(index, 'method', value);
  }, [index, onUpdate]);

  const handleAmountChange = useCallback((e) => {
    onUpdate(index, 'amount', e.target.value);
  }, [index, onUpdate]);

  return (
    <div className="flex gap-2 items-center">
      <Select value={payment.method} onValueChange={handleMethodChange}>
        <SelectTrigger className="w-24 sm:w-32" data-testid={`payment-method-${index}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PAYMENT_METHODS.map((m) => (
            <SelectItem key={m.value} value={m.value}>
              {m.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Input
        type="number"
        step="0.01"
        value={payment.amount}
        onChange={handleAmountChange}
        className="flex-1"
        data-testid={`payment-amount-${index}`}
      />
      {canRemove && (
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onRemove(index)}
          className="shrink-0"
          data-testid={`remove-payment-${index}`}
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

export default function CashierPage() {
  const [orders, setOrders] = useState([]);
  const [tables, setTables] = useState([]);
  const [register, setRegister] = useState(null);
  const [selectedOrderId, setSelectedOrderId] = useState(null);
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openRegisterAmount, setOpenRegisterAmount] = useState('');
  const [movementAmount, setMovementAmount] = useState('');
  const [movementReason, setMovementReason] = useState('');
  // Cancelamento individual de item
  const [cancelItemState, setCancelItemState] = useState(null); // { item }
  const [cancelQty, setCancelQty] = useState(1);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelAdminEmail, setCancelAdminEmail] = useState('');
  const [cancelAdminPassword, setCancelAdminPassword] = useState('');
  const [cancelRestore, setCancelRestore] = useState('no'); // 'yes' | 'no'
  const [cancelSubmitting, setCancelSubmitting] = useState(false);
  const isMountedRef = useRef(true);

  // Encontra o pedido selecionado de forma memoizada
  const selectedOrder = useMemo(() => {
    return orders.find(o => o.id === selectedOrderId) || null;
  }, [orders, selectedOrderId]);

  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const [ordersRes, tablesRes, registerRes] = await Promise.all([
        ordersAPI.getOpen(),
        tablesAPI.getAll(),
        cashRegisterAPI.getCurrent(),
      ]);
      if (isMountedRef.current) {
        setOrders(ordersRes.data);
        setTables(tablesRes.data);
        setRegister(registerRes.data);
        setLoading(false);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
      if (isMountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    
    const handleOrderClosed = () => {
      if (isMountedRef.current) fetchData();
    };
    const handleTablesUpdate = () => {
      if (isMountedRef.current) fetchData();
    };

    fetchData();
    socketService.connect();
    socketService.on('order_closed', handleOrderClosed);
    socketService.on('tables_updated', handleTablesUpdate);

    return () => {
      isMountedRef.current = false;
      socketService.off('order_closed');
      socketService.off('tables_updated');
    };
  }, [fetchData]);

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

  const selectOrder = useCallback((order) => {
    setSelectedOrderId(order.id);
    setPayments([{ id: Date.now(), method: 'cash', amount: order.total }]);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedOrderId(null);
    setPayments([]);
  }, []);

  const addPayment = useCallback(() => {
    setPayments(prev => [...prev, { id: Date.now(), method: 'cash', amount: 0 }]);
  }, []);

  const updatePayment = useCallback((index, field, value) => {
    setPayments(prev => {
      const newPayments = [...prev];
      newPayments[index] = {
        ...newPayments[index],
        [field]: field === 'amount' ? (parseFloat(value) || 0) : value
      };
      return newPayments;
    });
  }, []);

  const removePayment = useCallback((index) => {
    setPayments(prev => prev.filter((_, i) => i !== index));
  }, []);

  const getTotalPayments = useMemo(() => {
    return payments.reduce((sum, p) => sum + (parseFloat(p.amount) || 0), 0);
  }, [payments]);

  const handleRequestCleaning = async (tableId, tableNumber) => {
    try {
      await tablesAPI.update(tableId, { status: 'cleaning' });
      toast.success(`Limpeza solicitada para Mesa ${tableNumber}`);
      fetchData();
    } catch (error) {
      toast.error('Erro ao solicitar limpeza');
    }
  };

  const handleCloseOrder = async () => {
    if (!selectedOrder) return;

    if (getTotalPayments < selectedOrder.total) {
      toast.error('Valor dos pagamentos insuficiente');
      return;
    }

    try {
      // Fecha o pedido
      await ordersAPI.close(selectedOrder.id, payments.map(p => ({ method: p.method, amount: p.amount })));
      toast.success('Comanda fechada com sucesso!');
      
      // Pergunta sobre NF-e
      const emitInvoice = window.confirm('Deseja emitir Nota Fiscal?');
      if (emitInvoice) {
        await invoicesAPI.create({ order_id: selectedOrder.id });
        toast.success('NF-e criada (MOCK)');
      }

      // Pergunta sobre solicitar limpeza
      const requestCleaning = window.confirm('Solicitar limpeza da mesa?');
      if (requestCleaning) {
        await tablesAPI.update(selectedOrder.table_id, { status: 'cleaning' });
        toast.info(`Mesa ${selectedOrder.table_number} aguardando limpeza`);
      }
      
      clearSelection();
      fetchData();
    } catch (error) {
      toast.error('Erro ao fechar comanda');
    }
  };

  const openCancelItem = (item) => {
    setCancelItemState({ item });
    setCancelQty(item.quantity || 1);
    setCancelReason('');
    setCancelAdminEmail('');
    setCancelAdminPassword('');
    setCancelRestore(item.stock_deducted ? 'no' : 'no');
  };

  const closeCancelItem = () => {
    setCancelItemState(null);
    setCancelSubmitting(false);
  };

  const submitCancelItem = async () => {
    if (!cancelItemState || !selectedOrder) return;
    const item = cancelItemState.item;
    const qtyNum = parseInt(cancelQty, 10);
    if (!qtyNum || qtyNum <= 0 || qtyNum > item.quantity) {
      toast.error('Quantidade inválida');
      return;
    }
    if (!cancelReason.trim()) {
      toast.error('Informe o motivo');
      return;
    }
    if (!cancelAdminEmail.trim() || !cancelAdminPassword) {
      toast.error('Credenciais do administrador são obrigatórias');
      return;
    }
    setCancelSubmitting(true);
    try {
      const res = await ordersAPI.cancelItem(selectedOrder.id, item.id, {
        quantity: qtyNum,
        reason: cancelReason.trim(),
        admin_email: cancelAdminEmail.trim(),
        admin_password: cancelAdminPassword,
        restore_stock: item.stock_deducted ? (cancelRestore === 'yes') : false,
      });
      toast.success(
        `Item cancelado (${qtyNum}x) — autorizado por ${res.data.authorized_by}${res.data.stock_restored ? ' • estoque devolvido' : ''}`
      );
      closeCancelItem();
      await fetchData();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message || 'Erro ao cancelar item');
      setCancelSubmitting(false);
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

  // Caixa não aberto
  if (!register) {
    return (
      <Layout title="Caixa">
        <div className="max-w-md mx-auto px-4" data-testid="cashier-page">
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
      <div className="space-y-4 sm:space-y-6" data-testid="cashier-page">
        {/* Status do Caixa - Responsivo */}
        <Card className="bg-primary/10 border-primary">
          <CardContent className="p-3 sm:p-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-4">
              <div>
                <p className="text-xs sm:text-sm text-muted-foreground">Inicial</p>
                <p className="text-sm sm:text-lg font-bold">{formatCurrency(register.initial_amount)}</p>
              </div>
              <div>
                <p className="text-xs sm:text-sm text-muted-foreground">Vendas</p>
                <p className="text-sm sm:text-lg font-bold text-green-600">{formatCurrency(register.total_sales)}</p>
              </div>
              <div>
                <p className="text-xs sm:text-sm text-muted-foreground">Sangrias</p>
                <p className="text-sm sm:text-lg font-bold text-red-600">-{formatCurrency(register.withdrawals)}</p>
              </div>
              <div>
                <p className="text-xs sm:text-sm text-muted-foreground">Reforços</p>
                <p className="text-sm sm:text-lg font-bold text-blue-600">+{formatCurrency(register.deposits)}</p>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <p className="text-xs sm:text-sm text-muted-foreground">Saldo</p>
                <p className="text-lg sm:text-xl font-heading font-bold text-primary">
                  {formatCurrency(
                    register.initial_amount + register.total_sales + register.deposits - register.withdrawals
                  )}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
          {/* Lista de Comandas */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader className="pb-2 sm:pb-4">
                <CardTitle className="font-heading text-lg sm:text-xl">Comandas Abertas</CardTitle>
              </CardHeader>
              <CardContent>
                {orders.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">
                    Nenhuma comanda aberta
                  </p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                    {orders.map((order) => (
                      <Card
                        key={order.id}
                        className={cn(
                          'cursor-pointer card-hover touch-target',
                          selectedOrderId === order.id && 'ring-2 ring-primary'
                        )}
                        onClick={() => selectOrder(order)}
                        data-testid={`order-card-${order.id}`}
                      >
                        <CardContent className="p-3 sm:p-4">
                          <div className="flex justify-between items-center mb-2">
                            <Badge variant="outline" className="font-heading text-base sm:text-lg">
                              Mesa {order.table_number}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {formatDate(order.created_at)}
                            </span>
                          </div>
                          <div className="space-y-1 mb-2">
                            {order.items.slice(0, 3).map((item) => (
                              <div key={item.id} className="flex justify-between text-xs sm:text-sm">
                                <span className="truncate">{item.quantity}x {item.product_name}</span>
                                <span>{formatCurrency(item.unit_price * item.quantity)}</span>
                              </div>
                            ))}
                            {order.items.length > 3 && (
                              <p className="text-xs text-muted-foreground">
                                +{order.items.length - 3} itens...
                              </p>
                            )}
                          </div>
                          <div className="pt-2 border-t flex justify-between items-center">
                            <span className="font-medium text-sm">Total:</span>
                            <span className="text-base sm:text-lg font-bold text-primary">
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

          {/* Painel de Pagamento */}
          <div>
            {selectedOrder ? (
              <Card className="sticky top-20">
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-center">
                    <CardTitle className="font-heading text-lg">
                      Mesa {selectedOrder.table_number}
                    </CardTitle>
                    <Button variant="ghost" size="icon" onClick={clearSelection}>
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 sm:space-y-4">
                  {/* Itens do Pedido */}
                  <ScrollArea className="h-32 sm:h-48 border rounded p-2">
                    {selectedOrder.items.map((item) => {
                      const isCancelled = item.status === 'cancelled';
                      return (
                        <div
                          key={item.id}
                          className={cn(
                            'flex justify-between items-center gap-2 text-xs sm:text-sm py-1',
                            isCancelled && 'opacity-60 line-through'
                          )}
                          data-testid={`cashier-item-row-${item.id}`}
                        >
                          <span className="flex-1 min-w-0 truncate">
                            {item.quantity}x {item.product_name}
                            {isCancelled && (
                              <Badge
                                variant="destructive"
                                className="ml-2 text-[10px]"
                                data-testid={`item-cancelled-badge-${item.id}`}
                              >
                                CANCELADO
                              </Badge>
                            )}
                          </span>
                          <span className="shrink-0">
                            {formatCurrency(item.unit_price * item.quantity)}
                          </span>
                          {!isCancelled && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 shrink-0 text-destructive hover:bg-destructive/10"
                              onClick={() => openCancelItem(item)}
                              title="Cancelar este item"
                              data-testid={`cancel-item-btn-${item.id}`}
                            >
                              <X className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </ScrollArea>

                  {/* Totais */}
                  <div className="space-y-1 sm:space-y-2 border-t pt-2">
                    <div className="flex justify-between text-xs sm:text-sm">
                      <span>Subtotal:</span>
                      <span>{formatCurrency(selectedOrder.subtotal)}</span>
                    </div>
                    <div className="flex justify-between text-xs sm:text-sm">
                      <span>Serviço ({selectedOrder.service_fee_percentage}%):</span>
                      <span>{formatCurrency(selectedOrder.service_fee)}</span>
                    </div>
                    <div className="flex justify-between font-bold text-base sm:text-lg">
                      <span>Total:</span>
                      <span className="text-primary">{formatCurrency(selectedOrder.total)}</span>
                    </div>
                  </div>

                  {/* Formas de Pagamento */}
                  <div className="space-y-2">
                    <Label className="text-sm">Pagamento</Label>
                    {payments.map((payment, idx) => (
                      <PaymentRow
                        key={payment.id}
                        payment={payment}
                        index={idx}
                        onUpdate={updatePayment}
                        onRemove={removePayment}
                        canRemove={payments.length > 1}
                      />
                    ))}
                    <Button variant="outline" size="sm" onClick={addPayment} className="w-full">
                      <Plus className="h-4 w-4 mr-2" />
                      Dividir
                    </Button>
                  </div>

                  {/* Total de Pagamentos */}
                  <div className="flex justify-between font-bold text-sm">
                    <span>Total Pagamentos:</span>
                    <span className={cn(
                      getTotalPayments >= selectedOrder.total ? 'text-green-600' : 'text-red-600'
                    )}>
                      {formatCurrency(getTotalPayments)}
                    </span>
                  </div>

                  {/* Troco */}
                  {getTotalPayments > selectedOrder.total && (
                    <div className="flex justify-between text-base sm:text-lg bg-muted p-2 rounded">
                      <span>Troco:</span>
                      <span className="font-bold">
                        {formatCurrency(getTotalPayments - selectedOrder.total)}
                      </span>
                    </div>
                  )}

                  <Button
                    className="w-full font-heading uppercase tracking-widest text-sm"
                    onClick={handleCloseOrder}
                    disabled={getTotalPayments < selectedOrder.total}
                    data-testid="close-order-btn"
                  >
                    <Receipt className="h-4 w-4 mr-2" />
                    Fechar Comanda
                  </Button>

                  {/* Cortesia / Permuta */}
                  {!selectedOrder.is_comp ? (
                    <Button
                      variant="outline"
                      className="w-full text-xs border-purple-500/40 text-purple-600 hover:bg-purple-500/10"
                      onClick={async () => {
                        const reason = window.prompt('Motivo da cortesia/permuta:', '');
                        if (!reason || !reason.trim()) return;
                        try {
                          const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/orders/${selectedOrder.id}/comp`, {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
                            body: JSON.stringify({ is_comp: true, comp_reason: reason.trim() }),
                          });
                          if (!r.ok) throw new Error((await r.json()).detail || 'Erro');
                          toast.success('Pedido marcado como cortesia');
                          window.location.reload();
                        } catch (e) {
                          toast.error(e.message);
                        }
                      }}
                      data-testid="mark-comp-btn"
                    >
                      🎁 Marcar como Cortesia/Permuta
                    </Button>
                  ) : (
                    <div className="p-2 rounded border border-purple-500/40 bg-purple-500/10 text-xs" data-testid="comp-info">
                      <span className="font-bold text-purple-700">🎁 CORTESIA</span>
                      {selectedOrder.comp_reason && <span className="ml-2 text-muted-foreground">— {selectedOrder.comp_reason}</span>}
                    </div>
                  )}

                  {/* Cancelar comanda (exige admin) */}
                  <Button
                    variant="outline"
                    className="w-full text-xs border-destructive/40 text-destructive hover:bg-destructive/10"
                    onClick={async () => {
                      const reason = window.prompt('Motivo do cancelamento:', '');
                      if (!reason || !reason.trim()) return;
                      const email = window.prompt('E-mail do administrador:', '');
                      if (!email) return;
                      const password = window.prompt('Senha do administrador:', '');
                      if (!password) return;
                      try {
                        const r = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/orders/${selectedOrder.id}/cancel`, {
                          method: 'PATCH',
                          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
                          body: JSON.stringify({ reason: reason.trim(), admin_email: email.trim(), admin_password: password }),
                        });
                        if (!r.ok) throw new Error((await r.json()).detail || 'Erro');
                        const res = await r.json();
                        toast.success(`Comanda cancelada (autorizado por ${res.cancelled_by})`);
                        window.location.reload();
                      } catch (e) {
                        toast.error(e.message);
                      }
                    }}
                    data-testid="cancel-order-btn"
                  >
                    ❌ Cancelar Comanda (exige admin)
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="font-heading text-lg">Operações</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground text-center">
                    Selecione uma comanda
                  </p>

                  <div className="space-y-3 pt-4 border-t">
                    <Label className="text-sm">Sangria / Reforço</Label>
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
                      <Button variant="outline" onClick={handleWithdrawal} className="text-red-600 text-xs sm:text-sm">
                        <Minus className="h-4 w-4 mr-1" />
                        Sangria
                      </Button>
                      <Button variant="outline" onClick={handleDeposit} className="text-green-600 text-xs sm:text-sm">
                        <Plus className="h-4 w-4 mr-1" />
                        Reforço
                      </Button>
                    </div>

                    <Button
                      variant="destructive"
                      className="w-full text-sm"
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

      {/* Dialog: Cancelamento individual de item */}
      <Dialog open={!!cancelItemState} onOpenChange={(o) => { if (!o) closeCancelItem(); }}>
        <DialogContent className="max-w-md" data-testid="cancel-item-dialog">
          <DialogHeader>
            <DialogTitle>Cancelar item</DialogTitle>
            <DialogDescription>
              {cancelItemState?.item && (
                <>
                  <strong>{cancelItemState.item.product_name}</strong> — atualmente{' '}
                  {cancelItemState.item.quantity}x{' '}
                  {formatCurrency(cancelItemState.item.unit_price)}.
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Quantidade a cancelar</Label>
              <Input
                type="number"
                min={1}
                max={cancelItemState?.item?.quantity || 1}
                value={cancelQty}
                onChange={(e) => setCancelQty(e.target.value)}
                data-testid="cancel-item-qty"
              />
              {cancelItemState?.item && (
                <p className="text-[11px] text-muted-foreground">
                  Máx.: {cancelItemState.item.quantity}. Restarão{' '}
                  {Math.max(0, (cancelItemState.item.quantity || 0) - (parseInt(cancelQty, 10) || 0))}x ativos.
                </p>
              )}
            </div>

            <div className="space-y-1">
              <Label>Motivo do cancelamento</Label>
              <Input
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Ex.: cliente desistiu"
                data-testid="cancel-item-reason"
              />
            </div>

            {cancelItemState?.item?.stock_deducted && (
              <div className="space-y-1 rounded border border-amber-500/40 bg-amber-500/10 p-2">
                <Label className="text-amber-800">
                  Estoque já foi baixado — Devolver ao estoque?
                </Label>
                <div className="flex gap-4 text-sm">
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="radio"
                      name="restore"
                      checked={cancelRestore === 'yes'}
                      onChange={() => setCancelRestore('yes')}
                      data-testid="cancel-item-restore-yes"
                    />
                    Sim
                  </label>
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="radio"
                      name="restore"
                      checked={cancelRestore === 'no'}
                      onChange={() => setCancelRestore('no')}
                      data-testid="cancel-item-restore-no"
                    />
                    Não
                  </label>
                </div>
              </div>
            )}

            <div className="pt-2 border-t space-y-2">
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Autorização do administrador
              </Label>
              <Input
                type="email"
                placeholder="E-mail do admin"
                value={cancelAdminEmail}
                onChange={(e) => setCancelAdminEmail(e.target.value)}
                autoComplete="off"
                data-testid="cancel-item-admin-email"
              />
              <Input
                type="password"
                placeholder="Senha do admin"
                value={cancelAdminPassword}
                onChange={(e) => setCancelAdminPassword(e.target.value)}
                autoComplete="new-password"
                data-testid="cancel-item-admin-password"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={closeCancelItem}
              disabled={cancelSubmitting}
              data-testid="cancel-item-cancel-btn"
            >
              Voltar
            </Button>
            <Button
              variant="destructive"
              onClick={submitCancelItem}
              disabled={cancelSubmitting}
              data-testid="cancel-item-confirm-btn"
            >
              {cancelSubmitting ? 'Cancelando...' : 'Confirmar cancelamento'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
