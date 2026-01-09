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
          });
        });
    });
    return items;
  };

  const kitchenItems = getKitchenItems();
  const pendingItems = kitchenItems.filter(i => i.status === 'pending');
  const preparingItems = kitchenItems.filter(i => i.status === 'preparing');
  const readyItems = kitchenItems.filter(i => i.status === 'ready');

  const KanbanColumn = ({ title, items, icon: Icon, color, nextStatus, nextLabel }) => (
    <div className="flex-1 min-w-[280px] sm:min-w-[300px]">
      <div className={cn('rounded-t-lg p-3 sm:p-4 flex items-center gap-2', color)}>
        <Icon className="h-5 w-5 sm:h-6 sm:w-6" />
        <h3 className="font-heading text-lg sm:text-xl">{title}</h3>
        <Badge variant="secondary" className="ml-auto">
          {items.length}
        </Badge>
      </div>
      <div className="bg-card border border-t-0 rounded-b-lg p-2 sm:p-4 min-h-[50vh] sm:min-h-[60vh] space-y-2 sm:space-y-4">
        {items.map((item) => (
          <Card 
            key={`${item.orderId}-${item.id}`} 
            className={cn(
              'border-l-4 animate-fade-in',
              item.status === 'pending' && 'border-l-amber-500',
              item.status === 'preparing' && 'border-l-blue-500',
              item.status === 'ready' && 'border-l-green-500'
            )}
            data-testid={`kitchen-item-${item.id}`}
          >
            <CardContent className="p-3 sm:p-4">
              <div className="flex justify-between items-start mb-2">
                <Badge variant="outline" className="font-heading text-base sm:text-lg">
                  Mesa {item.tableNumber}
                </Badge>
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDate(item.orderCreatedAt)}
                </span>
              </div>
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
                  className="w-full touch-target font-heading uppercase tracking-wider text-sm sm:text-base"
                  onClick={() => updateItemStatus(item.orderId, item.id, nextStatus, item.tableNumber, item.product_name)}
                  data-testid={`status-btn-${item.id}`}
                >
                  {nextLabel}
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
        {items.length === 0 && (
          <div className="text-center py-8 sm:py-12 text-muted-foreground">
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
          <Card className="bg-amber-100 dark:bg-amber-900/30 border-amber-400">
            <CardContent className="p-2 sm:p-4 text-center">
              <p className="text-2xl sm:text-3xl font-heading font-bold">{pendingItems.length}</p>
              <p className="text-xs sm:text-sm">Pendentes</p>
            </CardContent>
          </Card>
          <Card className="bg-blue-100 dark:bg-blue-900/30 border-blue-400">
            <CardContent className="p-2 sm:p-4 text-center">
              <p className="text-2xl sm:text-3xl font-heading font-bold">{preparingItems.length}</p>
              <p className="text-xs sm:text-sm">Preparando</p>
            </CardContent>
          </Card>
          <Card className="bg-green-100 dark:bg-green-900/30 border-green-400">
            <CardContent className="p-2 sm:p-4 text-center">
              <p className="text-2xl sm:text-3xl font-heading font-bold">{readyItems.length}</p>
              <p className="text-xs sm:text-sm">Prontos</p>
            </CardContent>
          </Card>
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
          />
          <KanbanColumn
            title="Em Preparo"
            items={preparingItems}
            icon={Timer}
            color="bg-blue-500 text-white"
            nextStatus="ready"
            nextLabel="Marcar Pronto"
          />
          <KanbanColumn
            title="Prontos"
            items={readyItems}
            icon={Check}
            color="bg-green-500 text-white"
            nextStatus="delivered"
            nextLabel="Entregar"
          />
        </div>
      </div>
    </Layout>
  );
}
