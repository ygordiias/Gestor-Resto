import React, { useState, useEffect, useCallback, useRef } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ordersAPI } from '../lib/api';
import { cn, getStatusLabel, formatDate } from '../lib/utils';
import socketService, { playNotificationSound } from '../lib/socket';
import { toast } from 'sonner';
import { ChefHat, Clock, Check, Timer, Bell } from 'lucide-react';

export default function KitchenPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const isMountedRef = useRef(true);
  const prevPendingCountRef = useRef(0);

  const fetchOrders = useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const response = await ordersAPI.getOpen();
      if (isMountedRef.current) {
        const newOrders = response.data;
        
        // Conta itens pendentes de comida
        let newPendingCount = 0;
        newOrders.forEach(order => {
          order.items?.forEach(item => {
            if (item.type === 'food' && item.status === 'pending') {
              newPendingCount++;
            }
          });
        });
        
        // Beep se tiver novos pedidos
        if (newPendingCount > prevPendingCountRef.current && prevPendingCountRef.current > 0) {
          playNotificationSound();
          toast.info('Novo pedido na cozinha!', { icon: <Bell className="h-4 w-4" /> });
        }
        prevPendingCountRef.current = newPendingCount;
        
        setOrders(newOrders);
        setLoading(false);
      }
    } catch (error) {
      console.error('Error fetching orders:', error);
      if (isMountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    let interval;
    
    const handleKitchenUpdate = (updatedOrders) => {
      if (!isMountedRef.current) return;
      
      // Conta itens pendentes
      let newPendingCount = 0;
      updatedOrders.forEach(order => {
        order.items?.forEach(item => {
          if (item.type === 'food' && item.status === 'pending') {
            newPendingCount++;
          }
        });
      });
      
      // Beep se tiver novos pedidos
      if (newPendingCount > prevPendingCountRef.current) {
        playNotificationSound();
        toast.info('Novo pedido na cozinha!', { icon: <Bell className="h-4 w-4" /> });
      }
      prevPendingCountRef.current = newPendingCount;
      
      setOrders(updatedOrders);
    };

    fetchOrders();
    socketService.connect();
    socketService.joinRoom('kitchen');
    socketService.on('kitchen_update', handleKitchenUpdate);
    interval = setInterval(fetchOrders, 30000);

    return () => {
      isMountedRef.current = false;
      socketService.off('kitchen_update');
      socketService.leaveRoom('kitchen');
      if (interval) clearInterval(interval);
    };
  }, [fetchOrders]);

  const updateItemStatus = async (orderId, itemId, newStatus, tableNumber, productName) => {
    try {
      await ordersAPI.updateItemStatus(orderId, itemId, newStatus);
      
      // Notifica garçom quando item está pronto
      if (newStatus === 'ready') {
        socketService.emit('item_ready', { tableNumber, productName, type: 'food' });
        toast.success(`${productName} pronto! Garçom notificado.`);
      } else {
        toast.success(`Status: ${getStatusLabel(newStatus)}`);
      }
      
      fetchOrders();
    } catch (error) {
      toast.error('Erro ao atualizar status');
    }
  };

  // Filter only food items
  const getKitchenItems = () => {
    const items = [];
    orders.forEach(order => {
      order.items
        ?.filter(item => item.type === 'food' && item.status !== 'delivered')
        .forEach(item => {
          items.push({
            ...item,
            orderId: order.id,
            tableNumber: order.table_number,
            orderCreatedAt: order.created_at,
            waiterId: order.waiter_id,
            waiterName: order.waiter_name,
          });
        });
    });
    return items;
  };

  const kitchenItems = getKitchenItems();
  const pendingItems = kitchenItems.filter(i => i.status === 'pending');
  const preparingItems = kitchenItems.filter(i => i.status === 'preparing');
  const readyItems = kitchenItems.filter(i => i.status === 'ready');

  // Keyboard navigation (arrow keys + Enter). TAB continua funcionando normalmente.
  const columnsRef = useRef([pendingItems, preparingItems, readyItems]);
  columnsRef.current = [pendingItems, preparingItems, readyItems];
  const [selectedCol, setSelectedCol] = useState(0);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const NEXT_STATUS = ['preparing', 'ready', 'delivered'];
  const NEXT_LABEL = ['Iniciar', 'Marcar Pronto', 'Entregar'];

  useEffect(() => {
    const onKey = (e) => {
      // Ignora se estiver digitando em input/textarea
      const t = e.target;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
      const cols = columnsRef.current;
      const curCol = cols[selectedCol] || [];
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIdx(i => Math.min(i + 1, Math.max(0, curCol.length - 1)));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIdx(i => Math.max(0, i - 1));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setSelectedCol(c => Math.min(c + 1, 2));
        setSelectedIdx(0);
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setSelectedCol(c => Math.max(c - 1, 0));
        setSelectedIdx(0);
      } else if (e.key === 'Enter' || e.key === ' ') {
        // Avanca o item selecionado
        const item = curCol[selectedIdx];
        if (item) {
          e.preventDefault();
          const next = NEXT_STATUS[selectedCol];
          updateItemStatus(item.orderId, item.id, next, item.tableNumber, item.product_name);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedCol, selectedIdx]);

  // Corrige indice quando lista muda
  useEffect(() => {
    const curCol = [pendingItems, preparingItems, readyItems][selectedCol] || [];
    if (selectedIdx >= curCol.length) setSelectedIdx(Math.max(0, curCol.length - 1));
  }, [pendingItems.length, preparingItems.length, readyItems.length, selectedCol]);

  const KanbanColumn = ({ title, items, icon: Icon, color, nextStatus, nextLabel, columnIndex }) => (
    <div className="flex-1 min-w-[280px] sm:min-w-[300px]">
      <div className={cn('rounded-t-lg p-3 sm:p-4 flex items-center gap-2', color, selectedCol === columnIndex && 'ring-2 ring-primary')}>
        <Icon className="h-5 w-5 sm:h-6 sm:w-6" />
        <h3 className="font-heading text-lg sm:text-xl">{title}</h3>
        <Badge variant="secondary" className="ml-auto">
          {items.length}
        </Badge>
      </div>
      <div className="bg-card border border-t-0 rounded-b-lg p-2 sm:p-4 min-h-[50vh] sm:min-h-[60vh] space-y-2 sm:space-y-4">
        {items.map((item, idx) => {
          const isSelected = selectedCol === columnIndex && selectedIdx === idx;
          return (
          <Card 
            key={`${item.orderId}-${item.id}`} 
            className={cn(
              'border-l-4 animate-fade-in transition-all',
              item.status === 'pending' && 'border-l-amber-500',
              item.status === 'preparing' && 'border-l-blue-500',
              item.status === 'ready' && 'border-l-green-500',
              isSelected && 'ring-4 ring-primary ring-offset-2 ring-offset-background scale-[1.02] shadow-2xl border-l-primary'
            )}
            onClick={() => { setSelectedCol(columnIndex); setSelectedIdx(idx); }}
            data-testid={`kitchen-item-${item.id}`}
          >
            <CardContent className="p-3 sm:p-4">
              {isSelected && (
                <div className="mb-2 -mt-1 -mx-1 px-2 py-0.5 rounded bg-primary text-primary-foreground text-xs font-bold tracking-widest uppercase inline-block">
                  ▶ Selecionado
                </div>
              )}
              <div className="flex justify-between items-start mb-2">
                <Badge variant="outline" className="font-heading text-base sm:text-lg">
                  Mesa {item.tableNumber}
                </Badge>
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDate(item.orderCreatedAt)}
                </span>
              </div>
              {item.waiterName && (
                <p className="text-xs text-muted-foreground mb-1">Garçom: <span className="font-semibold text-foreground">{item.waiterName}</span></p>
              )}
              <div className="mb-3">
                <p className="text-xl sm:text-2xl font-bold">{item.quantity}x</p>
                <p className="text-lg sm:text-xl font-medium">{item.product_name}</p>
                {item.notes && (
                  <p className="text-sm text-muted-foreground mt-1 p-2 bg-muted rounded">
                    📝 {item.notes}
                  </p>
                )}
              </div>
              {nextStatus && (
                <Button
                  className={cn(
                    "w-full touch-target font-heading uppercase tracking-wider text-sm sm:text-base",
                    isSelected && "ring-2 ring-primary-foreground"
                  )}
                  onClick={() => updateItemStatus(item.orderId, item.id, nextStatus, item.tableNumber, item.product_name)}
                  data-testid={`status-btn-${item.id}`}
                >
                  {nextLabel}
                </Button>
              )}
            </CardContent>
          </Card>
          );
        })}
        {items.length === 0 && (
          <div className="text-center py-8 sm:py-12 font-semibold" style={{ color: '#94A3B8' }}>
            Nenhum item
          </div>
        )}
      </div>
    </div>
  );

  if (loading) {
    return (
      <Layout title="Painel da Cozinha">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Painel da Cozinha">
      <div className="space-y-3 sm:space-y-4" data-testid="kitchen-page">
        {/* Stats - Responsivo */}
        <div className="grid grid-cols-3 gap-2 sm:gap-4">
          <Card className="border-0 shadow-lg" style={{ backgroundColor: '#1E293B' }}>
            <CardContent className="p-3 sm:p-5 text-center">
              <p className="text-3xl sm:text-4xl font-heading font-bold text-white">{pendingItems.length}</p>
              <p className="text-sm sm:text-base font-semibold text-slate-300">Pendentes</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-lg" style={{ backgroundColor: '#1D4ED8' }}>
            <CardContent className="p-3 sm:p-5 text-center">
              <p className="text-3xl sm:text-4xl font-heading font-bold text-white">{preparingItems.length}</p>
              <p className="text-sm sm:text-base font-semibold text-blue-100">Preparando</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-lg" style={{ backgroundColor: '#16A34A' }}>
            <CardContent className="p-3 sm:p-5 text-center">
              <p className="text-3xl sm:text-4xl font-heading font-bold text-white">{readyItems.length}</p>
              <p className="text-sm sm:text-base font-semibold text-green-100">Prontos</p>
            </CardContent>
          </Card>
        </div>

        {/* Legenda teclado */}
        <div className="text-xs text-muted-foreground -mt-2 mb-2 flex flex-wrap gap-x-3 gap-y-1" data-testid="kitchen-keyboard-hint">
          <span><kbd className="px-1.5 py-0.5 rounded bg-muted border font-mono text-[10px]">↑↓</kbd> navegar</span>
          <span><kbd className="px-1.5 py-0.5 rounded bg-muted border font-mono text-[10px]">←→</kbd> mudar coluna</span>
          <span><kbd className="px-1.5 py-0.5 rounded bg-muted border font-mono text-[10px]">Enter</kbd> avançar status</span>
        </div>

        {/* Kanban Board - Responsivo com scroll horizontal */}
        <div className="flex gap-2 sm:gap-4 overflow-x-auto pb-4 -mx-4 px-4 sm:mx-0 sm:px-0">
          <KanbanColumn
            title="Novos Pedidos"
            items={pendingItems}
            icon={Clock}
            color="bg-amber-500 text-amber-950"
            nextStatus="preparing"
            nextLabel="Iniciar Preparo"
            columnIndex={0}
          />
          <KanbanColumn
            title="Em Preparo"
            items={preparingItems}
            icon={Timer}
            color="bg-blue-500 text-white"
            nextStatus="ready"
            nextLabel="Marcar Pronto"
            columnIndex={1}
          />
          <KanbanColumn
            title="Prontos"
            items={readyItems}
            icon={Check}
            color="bg-green-500 text-white"
            nextStatus="delivered"
            nextLabel="Entregar"
            columnIndex={2}
          />
        </div>
      </div>
    </Layout>
  );
}
