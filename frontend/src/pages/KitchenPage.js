import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ordersAPI } from '../lib/api';
import { cn, getStatusColor, getStatusLabel, formatDate } from '../lib/utils';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import { ChefHat, Clock, Check, Timer } from 'lucide-react';

export default function KitchenPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOrders();
    
    // Connect to socket
    socketService.connect();
    socketService.joinRoom('kitchen');
    socketService.on('kitchen_update', (updatedOrders) => {
      setOrders(updatedOrders);
    });

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchOrders, 30000);

    return () => {
      socketService.off('kitchen_update');
      socketService.leaveRoom('kitchen');
      clearInterval(interval);
    };
  }, []);

  const fetchOrders = async () => {
    try {
      const response = await ordersAPI.getOpen();
      setOrders(response.data);
    } catch (error) {
      console.error('Error fetching orders:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateItemStatus = async (orderId, itemId, newStatus) => {
    try {
      await ordersAPI.updateItemStatus(orderId, itemId, newStatus);
      toast.success(`Status atualizado para: ${getStatusLabel(newStatus)}`);
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
        .filter(item => item.type === 'food' && item.status !== 'delivered')
        .forEach(item => {
          items.push({
            ...item,
            orderId: order.id,
            tableNumber: order.table_number,
            orderCreatedAt: order.created_at,
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
    <div className="flex-1 min-w-[300px]">
      <div className={cn('rounded-t-lg p-4 flex items-center gap-2', color)}>
        <Icon className="h-6 w-6" />
        <h3 className="font-heading text-xl">{title}</h3>
        <Badge variant="secondary" className="ml-auto">
          {items.length}
        </Badge>
      </div>
      <div className="bg-card border border-t-0 rounded-b-lg p-4 min-h-[60vh] space-y-4">
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
            <CardContent className="p-4">
              <div className="flex justify-between items-start mb-2">
                <Badge variant="outline" className="font-heading text-lg">
                  Mesa {item.tableNumber}
                </Badge>
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDate(item.orderCreatedAt)}
                </span>
              </div>
              <div className="mb-3">
                <p className="text-2xl font-bold">{item.quantity}x</p>
                <p className="text-xl font-medium">{item.product_name}</p>
                {item.notes && (
                  <p className="text-sm text-muted-foreground mt-1 p-2 bg-muted rounded">
                    📝 {item.notes}
                  </p>
                )}
              </div>
              {nextStatus && (
                <Button
                  className="w-full touch-target font-heading uppercase tracking-wider"
                  onClick={() => updateItemStatus(item.orderId, item.id, nextStatus)}
                  data-testid={`status-btn-${item.id}`}
                >
                  {nextLabel}
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
        {items.length === 0 && (
          <div className="text-center py-12 text-muted-foreground">
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
      <div className="space-y-4" data-testid="kitchen-page">
        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <Card className="bg-amber-100 dark:bg-amber-900/30 border-amber-400">
            <CardContent className="p-4 text-center">
              <p className="text-3xl font-heading font-bold">{pendingItems.length}</p>
              <p className="text-sm">Pendentes</p>
            </CardContent>
          </Card>
          <Card className="bg-blue-100 dark:bg-blue-900/30 border-blue-400">
            <CardContent className="p-4 text-center">
              <p className="text-3xl font-heading font-bold">{preparingItems.length}</p>
              <p className="text-sm">Preparando</p>
            </CardContent>
          </Card>
          <Card className="bg-green-100 dark:bg-green-900/30 border-green-400">
            <CardContent className="p-4 text-center">
              <p className="text-3xl font-heading font-bold">{readyItems.length}</p>
              <p className="text-sm">Prontos</p>
            </CardContent>
          </Card>
        </div>

        {/* Kanban Board */}
        <div className="flex gap-4 overflow-x-auto pb-4">
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
