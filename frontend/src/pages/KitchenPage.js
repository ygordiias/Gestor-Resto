
import React, { useState, useEffect, useCallback, useRef } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ordersAPI } from '../lib/api';
import { formatDate } from '../lib/utils';
import socketService, { playNotificationSound } from '../lib/socket';
import { toast } from 'sonner';
import { Clock, Check, Timer, Bell, AlertTriangle } from 'lucide-react';
import { OnlineOrderBadge, isOnlineOrder } from '../components/OnlineOrderBadge';

const STAGES = [
  {
    status: 'pending',
    title: 'Novos pedidos',
    Icon: Clock,
    action: 'Iniciar pedido',
    next: 'preparing'
  },
  {
    status: 'preparing',
    title: 'Em preparo',
    Icon: Timer,
    action: 'Marcar pronto',
    next: 'ready'
  },
  {
    status: 'ready',
    title: 'Prontos',
    Icon: Check,
    action: 'Liberar / entregar',
    next: 'delivered'
  }
];

function formatElapsed(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;

  return `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
}

function getTiming(order, now) {
  const delivery = isOnlineOrder(order);
  const limit = delivery ? 45 * 60 : 30 * 60;

  const timestamp = new Date(order.created_at).getTime();

  const elapsed = Number.isFinite(timestamp)
    ? Math.max(0, Math.floor((now - timestamp) / 1000))
    : 0;

  const late = elapsed > limit;
  const warning = !late && elapsed >= limit * 0.7;

  return { delivery, elapsed, limit, late, warning };
}

function getCardStyle(timing) {
  if (timing.late) {
    return {
      backgroundColor: '#991b1b',
      borderColor: '#f87171',
      color: '#fff'
    };
  }

  if (timing.warning) {
    return {
      backgroundColor: '#92400e',
      borderColor: '#fbbf24',
      color: '#fff'
    };
  }

  return {
    backgroundColor: '#14532d',
    borderColor: '#4ade80',
    color: '#fff'
  };
}

export default function KitchenPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());
  const [busyKey, setBusyKey] = useState(null);

  const mounted = useRef(false);
  const pendingIds = useRef(new Set());
  const initialized = useRef(false);

  const applyOrders = useCallback((incoming) => {
    if (!mounted.current || !Array.isArray(incoming)) return;

    const next = new Set();

    incoming.forEach(order => {
      (order.items || []).forEach(item => {
        if (item.type === 'food' && item.status === 'pending') {
          next.add(`${order.id}:${item.id}`);
        }
      });
    });

    if (
      initialized.current &&
      [...next].some(id => !pendingIds.current.has(id))
    ) {
      playNotificationSound();
      toast.info('Novo pedido na cozinha!', {
        icon: <Bell className="h-4 w-4" />
      });
    }

    initialized.current = true;
    pendingIds.current = next;

    setOrders(incoming);
    setLoading(false);
  }, []);

  const fetchOrders = useCallback(async () => {
    try {
      const response = await ordersAPI.getOpen();
      applyOrders(response.data);
    } catch (error) {
      console.error('Erro ao carregar pedidos da cozinha:', error);
      if (mounted.current) setLoading(false);
    }
  }, [applyOrders]);

  useEffect(() => {
    mounted.current = true;

    fetchOrders();

    socketService.connect();
    socketService.joinRoom('kitchen');
    socketService.on('kitchen_update', applyOrders);

    const refresh = setInterval(fetchOrders, 30000);
    const clock = setInterval(() => setNow(Date.now()), 1000);

    return () => {
      mounted.current = false;
      socketService.off('kitchen_update');
      socketService.leaveRoom('kitchen');

      clearInterval(refresh);
      clearInterval(clock);
    };
  }, [fetchOrders, applyOrders]);

  const groupsByStage = STAGES.map(stage => {
    return orders
      .map(order => ({
        order,
        items: (order.items || []).filter(
          item =>
            item.type === 'food' &&
            item.status === stage.status
        )
      }))
      .filter(group => group.items.length > 0)
      .sort(
        (a, b) =>
          new Date(a.order.created_at).getTime() -
          new Date(b.order.created_at).getTime()
      );
  });

  const updateGroup = async (order, items, newStatus) => {
    const key = `${order.id}:${newStatus}`;

    if (busyKey !== null) return;

    setBusyKey(key);

    try {
      const results = await Promise.allSettled(
        items.map(item =>
          ordersAPI.updateItemStatus(
            order.id,
            item.id,
            newStatus
          )
        )
      );

      const success = results.filter(
        result => result.status === 'fulfilled'
      ).length;

      if (success === items.length) {
        toast.success(`${success} item(ns) atualizado(s) com sucesso.`);
      } else {
        toast.error(
          `${success} de ${items.length} itens atualizados. Confira os restantes.`
        );
      }

      if (newStatus === 'ready') {
        items.forEach((item, index) => {
          if (results[index].status === 'fulfilled') {
            socketService.emit('item_ready', {
              tableNumber: order.table_number,
              productName: item.product_name,
              type: 'food'
            });
          }
        });
      }

      await fetchOrders();
    } catch (error) {
      toast.error('Erro ao atualizar o pedido.');
    } finally {
      if (mounted.current) setBusyKey(null);
    }
  };

  if (loading) {
    return (
      <Layout title="Painel da Cozinha">
        <div className="p-8 text-center text-xl">
          Carregando pedidos...
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Painel da Cozinha">
      <div className="space-y-4" data-testid="kitchen-page">

        <div className="grid grid-cols-3 gap-2 sm:gap-4">
          {STAGES.map((stage, index) => (
            <Card
              key={stage.status}
              className="bg-slate-900 text-white border-0"
            >
              <CardContent className="p-3 sm:p-5 text-center">
                <p className="text-3xl sm:text-4xl font-bold">
                  {groupsByStage[index].length}
                </p>

                <p className="text-xs sm:text-base">
                  {stage.title}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="text-sm text-muted-foreground">
          Cada cartão representa uma comanda ou pedido.
          Verde: no prazo · Laranja: atenção · Vermelho: atrasado.
        </div>

        <div className="flex gap-3 overflow-x-auto pb-4">

          {STAGES.map((stage, index) => (
            <div
              key={stage.status}
              className="flex-1 min-w-[300px]"
            >

              <div className="rounded-t-lg bg-slate-800 text-white p-3 flex items-center gap-2">
                <stage.Icon className="h-5 w-5" />

                <h3 className="font-bold">
                  {stage.title}
                </h3>

                <Badge
                  variant="secondary"
                  className="ml-auto"
                >
                  {groupsByStage[index].length}
                </Badge>
              </div>

              <div className="bg-card border rounded-b-lg p-2 space-y-3 min-h-[55vh]">

                {groupsByStage[index].map(({ order, items }) => {
                  const timing = getTiming(order, now);
                  const key = `${order.id}:${stage.next}`;

                  return (
                    <Card
                      key={order.id}
                      className="border-2"
                      style={getCardStyle(timing)}
                    >
                      <CardContent className="p-3 space-y-3">

                        <div className="flex justify-between items-start gap-2">

                          <div className="space-y-1 min-w-0">

                            {isOnlineOrder(order) ? (
                              <OnlineOrderBadge
                                order={order}
                                size="lg"
                              />
                            ) : (
                              <>
                                <p className="text-base font-bold">
                                  Mesa {order.table_number ?? '—'}
                                </p>

                                {order.tab_number != null && (
                                  <p className="text-xl sm:text-2xl font-black">
                                    COMANDA {order.tab_number}
                                  </p>
                                )}
                              </>
                            )}

                            <p className="text-xs opacity-90">
                              Entrada: {formatDate(order.created_at)}
                            </p>

                          </div>

                          <div className="flex flex-col items-end gap-1 shrink-0">

                            {timing.late && (
                              <span className="bg-white text-red-800 rounded px-2 py-1 text-xs font-black flex gap-1 items-center animate-pulse">
                                <AlertTriangle className="h-4 w-4" />
                                ATRASADO!
                              </span>
                            )}

                            {timing.warning && (
                              <span className="bg-white text-amber-900 rounded px-2 py-1 text-xs font-bold">
                                ATENÇÃO
                              </span>
                            )}

                            <span className="text-2xl font-black tabular-nums">
                              {formatElapsed(timing.elapsed)}
                            </span>

                            <span className="text-xs opacity-90">
                              Limite: {timing.limit / 60} min
                            </span>

                          </div>
                        </div>

                        <div className="border-t border-white/40 pt-2 space-y-2">

                          {items.map(item => (
                            <div
                              key={item.id}
                              className="border-b border-white/20 pb-2"
                            >
                              <p className="text-lg font-bold">
                                {item.quantity}× {item.product_name}
                              </p>

                              {item.notes && (
                                <p className="mt-1 bg-white text-slate-900 rounded p-2 text-sm font-bold">
                                  📝 {item.notes}
                                </p>
                              )}
                            </div>
                          ))}

                        </div>

                        {order.waiter_name && (
                          <p className="text-xs">
                            Garçom: {order.waiter_name}
                          </p>
                        )}

                        <Button
                          className="w-full font-bold text-base"
                          variant="secondary"
                          disabled={busyKey !== null}
                          onClick={() =>
                            updateGroup(order, items, stage.next)
                          }
                        >
                          {busyKey === key
                            ? 'Atualizando...'
                            : stage.action}
                        </Button>

                      </CardContent>
                    </Card>
                  );
                })}

                {groupsByStage[index].length === 0 && (
                  <p className="text-center text-muted-foreground py-10">
                    Nenhum pedido
                  </p>
                )}

              </div>
            </div>
          ))}

        </div>
      </div>
    </Layout>
  );
}

