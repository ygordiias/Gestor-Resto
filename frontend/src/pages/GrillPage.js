
import React, { useState, useEffect, useCallback, useRef } from 'react';
import Layout from '../components/Layout';
import { ordersAPI } from '../lib/api';
import socketService from '../lib/socket';
import { isOnlineOrder } from '../components/OnlineOrderBadge';
import { AlertTriangle, ChefHat, Clock, Flame } from 'lucide-react';

const EXCLUDED = [
  'batata frita',
  'batatas fritas',
  'batata tradicional',
  'batata com cheddar',
  'batata com catupiry',
  'anel de cebola',
  'aneis de cebola',
  'onion rings'
];

function normalize(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function belongsToGrill(item) {
  if (item.type !== 'food') return false;

  const name = normalize(item.product_name);

  return !EXCLUDED.some(excluded =>
    name.includes(normalize(excluded))
  );
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;

  return `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
}

function getTiming(order, now) {
  const limit = isOnlineOrder(order) ? 45 * 60 : 30 * 60;
  const created = new Date(order.created_at).getTime();

  const elapsed = Number.isFinite(created)
    ? Math.max(0, Math.floor((now - created) / 1000))
    : 0;

  return {
    elapsed,
    limit,
    late: elapsed > limit,
    warning: elapsed >= limit * 0.7 && elapsed <= limit
  };
}

function getColors(timing) {
  if (timing.late) {
    return {
      background: '#991b1b',
      border: '#f87171'
    };
  }

  if (timing.warning) {
    return {
      background: '#92400e',
      border: '#fbbf24'
    };
  }

  return {
    background: '#14532d',
    border: '#4ade80'
  };
}

export default function GrillPage() {
  const [orders, setOrders] = useState([]);
  const [now, setNow] = useState(Date.now());
  const [loading, setLoading] = useState(true);

  const mounted = useRef(false);

  const applyOrders = useCallback((incoming) => {
    if (!mounted.current || !Array.isArray(incoming)) return;

    setOrders(incoming);
    setLoading(false);
  }, []);

  const fetchOrders = useCallback(async () => {
    try {
      const response = await ordersAPI.getOpen();
      applyOrders(response.data);
    } catch (error) {
      console.error('Erro ao carregar tela da chapa:', error);

      if (mounted.current) {
        setLoading(false);
      }
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

  const activeOrders = orders
    .map(order => ({
      order,
      items: (order.items || []).filter(item =>
        belongsToGrill(item) &&
        (item.status === 'pending' || item.status === 'preparing')
      )
    }))
    .filter(group => group.items.length > 0)
    .sort((a, b) => {
      const aTime = new Date(a.order.created_at).getTime();
      const bTime = new Date(b.order.created_at).getTime();

      return aTime - bTime;
    });

  if (loading) {
    return (
      <Layout title="Painel da Chapa">
        <div className="p-8 text-center text-xl">
          Carregando pedidos da chapa...
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Painel da Chapa">
      <div className="space-y-5">

        <div className="bg-slate-900 text-white rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Flame className="h-9 w-9 text-orange-400" />

            <div>
              <h1 className="text-2xl sm:text-3xl font-black">
                CHAPA E MONTAGEM
              </h1>

              <p className="text-sm text-slate-300">
                Pedidos em tempo real · Somente visualização
              </p>
            </div>
          </div>

          <div className="text-right">
            <p className="text-4xl font-black">
              {activeOrders.length}
            </p>

            <p className="text-sm">
              Pedidos ativos
            </p>
          </div>
        </div>

        {activeOrders.length === 0 ? (
          <div className="rounded-xl border p-12 text-center">
            <ChefHat className="h-14 w-14 mx-auto mb-4 text-muted-foreground" />

            <h2 className="text-2xl font-bold">
              Nenhum pedido para a chapa
            </h2>

            <p className="text-muted-foreground mt-2">
              Aguardando novos pedidos...
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-4">

            {activeOrders.map(({ order, items }) => {
              const timing = getTiming(order, now);
              const colors = getColors(timing);

              const pending = items.filter(
                item => item.status === 'pending'
              ).length;

              const preparing = items.filter(
                item => item.status === 'preparing'
              ).length;

              return (
                <div
                  key={order.id}
                  className="rounded-xl border-4 p-5 text-white shadow-lg space-y-4"
                  style={{
                    backgroundColor: colors.background,
                    borderColor: colors.border
                  }}
                >

                  <div className="flex justify-between items-start gap-3">

                    <div className="space-y-1">
                      {isOnlineOrder(order) ? (
                        <>
                          <p className="text-lg font-bold">
                            DELIVERY
                          </p>

                          <p className="text-2xl font-black">
                            {order.platform || order.source || 'PEDIDO ONLINE'}
                          </p>

                          <p className="text-sm">
                            Pedido: {order.external_order_id || order.id?.slice(0, 8)}
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="text-lg font-bold">
                            MESA {order.table_number ?? '—'}
                          </p>

                          {order.tab_number != null && (
                            <p className="text-3xl font-black">
                              COMANDA {order.tab_number}
                            </p>
                          )}
                        </>
                      )}
                    </div>

                    <div className="text-right shrink-0 space-y-2">

                      {timing.late && (
                        <div className="bg-white text-red-800 rounded-lg px-3 py-2 font-black flex items-center gap-2 animate-pulse">
                          <AlertTriangle className="h-5 w-5" />
                          ATRASADO!
                        </div>
                      )}

                      {timing.warning && (
                        <div className="bg-white text-amber-900 rounded-lg px-3 py-2 font-black">
                          ATENÇÃO
                        </div>
                      )}

                      <div className="flex items-center justify-end gap-2">
                        <Clock className="h-6 w-6" />

                        <span className="text-3xl font-black tabular-nums">
                          {formatTime(timing.elapsed)}
                        </span>
                      </div>

                      <p className="text-xs">
                        Limite: {timing.limit / 60} minutos
                      </p>
                    </div>

                  </div>

                  <div className="border-t-2 border-white/40 pt-3 space-y-3">

                    {items.map(item => (
                      <div
                        key={item.id}
                        className="border-b border-white/30 pb-3"
                      >
                        <div className="flex items-start justify-between gap-3">

                          <p className="text-xl sm:text-2xl font-black">
                            {item.quantity}× {item.product_name}
                          </p>

                          <span className="text-xs font-bold bg-white/20 px-2 py-1 rounded shrink-0">
                            {item.status === 'preparing'
                              ? 'EM PREPARO'
                              : 'NOVO'}
                          </span>

                        </div>

                        {item.notes && (
                          <div className="mt-2 rounded-lg bg-white text-red-900 p-3 font-black text-base">
                            OBS: {item.notes}
                          </div>
                        )}
                      </div>
                    ))}

                  </div>

                  <div className="flex justify-between text-sm font-bold">
                    <span>Novos: {pending}</span>
                    <span>Em preparo: {preparing}</span>
                  </div>

                  {order.waiter_name && (
                    <p className="text-sm">
                      Garçom: {order.waiter_name}
                    </p>
                  )}

                </div>
              );
            })}

          </div>
        )}

      </div>
    </Layout>
  );
}
