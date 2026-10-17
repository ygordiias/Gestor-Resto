
import React, {
  useState,
  useEffect,
  useLayoutEffect,
  useCallback,
  useRef,
} from 'react';

import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ordersAPI } from '../lib/api';
import { cn, getStatusLabel, formatDate } from '../lib/utils';
import socketService, { playNotificationSound } from '../lib/socket';
import { toast } from 'sonner';

import {
  Clock,
  Check,
  Timer,
  Bell,
} from 'lucide-react';

import {
  OnlineOrderBadge,
  isOnlineOrder,
} from '../components/OnlineOrderBadge';

const STATUSES = ['pending', 'preparing', 'ready'];
const NEXT_STATUSES = ['preparing', 'ready', 'delivered'];

const itemKey = (item) => `${item.orderId}-${item.id}`;

export default function BarPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  const [selectedCol, setSelectedCol] = useState(0);
  const [selectedKey, setSelectedKey] = useState(null);
  const [updatingKey, setUpdatingKey] = useState(null);

  const isMountedRef = useRef(false);
  const prevPendingCountRef = useRef(0);
  const updateLockRef = useRef(false);
  const enterHeldRef = useRef(false);

  const columnsRef = useRef([[], [], []]);
  const selectedRef = useRef({ col: 0, key: null });
  const cardRefs = useRef({});
  const boardRef = useRef(null);
  const actionRef = useRef(null);
  const fetchVersionRef = useRef(0);

  const countPending = (list) =>
    list.reduce(
      (total, order) =>
        total +
        (order.items || []).filter(
          item =>
            item.type === 'drink' &&
            item.status === 'pending'
        ).length,
      0
    );

  const applyOrders = useCallback((newOrders, notify = true) => {
    if (!isMountedRef.current || !Array.isArray(newOrders)) return;

    const pendingCount = countPending(newOrders);

    if (
      notify &&
      pendingCount > prevPendingCountRef.current &&
      prevPendingCountRef.current > 0
    ) {
      playNotificationSound();

      toast.info('Novo pedido no bar!', {
        icon: <Bell className="h-4 w-4" />,
      });
    }

    prevPendingCountRef.current = pendingCount;
    setOrders(newOrders);
    setLoading(false);
  }, []);

  const fetchOrders = useCallback(async () => {
    if (!isMountedRef.current) return;

    const version = ++fetchVersionRef.current;

    try {
      const response = await ordersAPI.getOpen();

      if (
        !isMountedRef.current ||
        version !== fetchVersionRef.current ||
        updateLockRef.current
      ) {
        return;
      }

      applyOrders(response.data);
    } catch (error) {
      console.error('Erro ao buscar pedidos do bar:', error);

      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [applyOrders]);

  useEffect(() => {
    isMountedRef.current = true;

    const handleBarUpdate = (updatedOrders) => {
      if (!isMountedRef.current) return;

      // Não troca a lista durante uma atualização manual
      if (updateLockRef.current) return;

      ++fetchVersionRef.current;
      applyOrders(updatedOrders);
    };

    fetchOrders();

    socketService.connect();
    socketService.joinRoom('bar');
    socketService.on('bar_update', handleBarUpdate);

    const interval = setInterval(fetchOrders, 30000);

    return () => {
      isMountedRef.current = false;
      socketService.off('bar_update');
      socketService.leaveRoom('bar');
      clearInterval(interval);
    };
  }, [fetchOrders, applyOrders]);

  // Lista de bebidas do bar
  const barItems = orders.flatMap(order =>
    (order.items || [])
      .filter(
        item =>
          item.type === 'drink' &&
          item.status !== 'delivered'
      )
      .map(item => ({
        ...item,
        orderId: order.id,
        tableNumber: order.table_number,
        orderCreatedAt: order.created_at,
        waiterName: order.waiter_name,
        _order: order,
      }))
  );

  // Ordena os pedidos mais antigos primeiro
  const sortByAge = (a, b) => {
    const dateA = new Date(a.orderCreatedAt).getTime();
    const dateB = new Date(b.orderCreatedAt).getTime();

    return (
      (Number.isFinite(dateA) && Number.isFinite(dateB)
        ? dateA - dateB
        : 0) ||
      itemKey(a).localeCompare(itemKey(b))
    );
  };

  const columns = STATUSES.map(status =>
    barItems
      .filter(item => item.status === status)
      .sort(sortByAge)
  );

  const [pendingItems, preparingItems, readyItems] = columns;

  columnsRef.current = columns;

  const chooseItem = useCallback((col, key) => {
    selectedRef.current = { col, key };
    setSelectedCol(col);
    setSelectedKey(key);
  }, []);

  // Corrige a seleção quando um pedido muda ou desaparece
  useEffect(() => {
    const current = columns[selectedCol] || [];

    if (
      selectedKey &&
      current.some(item => itemKey(item) === selectedKey)
    ) {
      return;
    }

    if (current.length) {
      chooseItem(selectedCol, itemKey(current[0]));
      return;
    }

    const firstCol = columns.findIndex(col => col.length > 0);

    if (firstCol >= 0) {
      chooseItem(firstCol, itemKey(columns[firstCol][0]));
    } else {
      chooseItem(selectedCol, null);
    }
  }, [orders, selectedCol, selectedKey, chooseItem]);

  // CORREÇÃO PRINCIPAL:
  // A tela acompanha automaticamente o cartão selecionado
  useLayoutEffect(() => {
    if (!selectedKey) return;

    const key = `${selectedCol}:${selectedKey}`;

    let frame1;
    let frame2;

    frame1 = requestAnimationFrame(() => {
      frame2 = requestAnimationFrame(() => {
        const card = cardRefs.current[key];

        if (!card) return;

        card.scrollIntoView({
          behavior: 'instant',
          block: 'center',
          inline: 'nearest',
        });
      });
    });

    return () => {
      cancelAnimationFrame(frame1);

      if (frame2) {
        cancelAnimationFrame(frame2);
      }
    };
  }, [selectedCol, selectedKey]);

  // Navegação vertical: ↑ ↓
  const moveVertical = useCallback((direction) => {
    const { col, key } = selectedRef.current;
    const items = columnsRef.current[col] || [];

    if (!items.length) return;

    const currentIndex = items.findIndex(
      item => itemKey(item) === key
    );

    const nextIndex = Math.max(
      0,
      Math.min(
        items.length - 1,
        currentIndex < 0
          ? 0
          : currentIndex + direction
      )
    );

    chooseItem(col, itemKey(items[nextIndex]));
  }, [chooseItem]);

  // Navegação horizontal: ← →
  const moveHorizontal = useCallback((direction) => {
    const { col } = selectedRef.current;
    const nextCol = col + direction;

    if (nextCol < 0 || nextCol > 2) return;

    const items = columnsRef.current[nextCol] || [];

    chooseItem(
      nextCol,
      items.length ? itemKey(items[0]) : null
    );
  }, [chooseItem]);

  // Atualiza status com proteção contra comandos repetidos
  const updateItemStatus = useCallback(async (item, newStatus) => {
    if (!item || updateLockRef.current) return;

    updateLockRef.current = true;

    const key = itemKey(item);
    setUpdatingKey(key);

    const sourceCol = STATUSES.indexOf(item.status);
    const currentList = columnsRef.current[sourceCol] || [];

    const oldIndex = currentList.findIndex(
      current => itemKey(current) === key
    );

    const remaining = currentList.filter(
      current => itemKey(current) !== key
    );

    const nextItem = remaining[
      Math.min(Math.max(oldIndex, 0), remaining.length - 1)
    ];

    try {
      await ordersAPI.updateItemStatus(
        item.orderId,
        item.id,
        newStatus
      );

      if (newStatus === 'ready') {
        socketService.emit('item_ready', {
          tableNumber: item.tableNumber,
          productName: item.product_name,
          type: 'drink',
        });

        toast.success(
          `${item.product_name} pronto! Garçom notificado.`
        );
      } else {
        toast.success(`Status: ${getStatusLabel(newStatus)}`);
      }

      // Seleciona o próximo pedido da mesma coluna
      if (selectedRef.current.key === key) {
        if (nextItem) {
          chooseItem(sourceCol, itemKey(nextItem));
        } else {
          const otherCol = columnsRef.current.findIndex(
            (col, index) =>
              index !== sourceCol && col.length > 0
          );

          if (otherCol >= 0) {
            chooseItem(
              otherCol,
              itemKey(columnsRef.current[otherCol][0])
            );
          } else {
            chooseItem(sourceCol, null);
          }
        }
      }

      // Invalida buscas anteriores e atualiza a lista
      ++fetchVersionRef.current;

      const response = await ordersAPI.getOpen();

      if (isMountedRef.current) {
        applyOrders(response.data, false);
      }
    } catch (error) {
      console.error('Erro ao atualizar bebida:', error);
      toast.error('Erro ao atualizar status. Confira o pedido.');
      ++fetchVersionRef.current;
    } finally {
      updateLockRef.current = false;

      if (isMountedRef.current) {
        setUpdatingKey(null);
        fetchOrders();
      }
    }
  }, [chooseItem, applyOrders, fetchOrders]);

  actionRef.current = updateItemStatus;

  // TECLADO: sem necessidade de mouse
  useEffect(() => {
    const onKeyDown = (event) => {
      const target = event.target;

      if (
        target?.closest?.(
          'input, textarea, select, [contenteditable="true"]'
        )
      ) {
        return;
      }

      if (
        event.ctrlKey ||
        event.altKey ||
        event.metaKey
      ) {
        return;
      }

      const keys = [
        'ArrowUp',
        'ArrowDown',
        'ArrowLeft',
        'ArrowRight',
        'Enter',
      ];

      if (!keys.includes(event.key)) return;

      // Evita que as setas rolem a página por conta própria
      event.preventDefault();

      if (event.key === 'ArrowUp') {
        moveVertical(-1);
        return;
      }

      if (event.key === 'ArrowDown') {
        moveVertical(1);
        return;
      }

      if (event.key === 'ArrowLeft') {
        moveHorizontal(-1);
        return;
      }

      if (event.key === 'ArrowRight') {
        moveHorizontal(1);
        return;
      }

      if (event.key === 'Enter') {
        if (
          event.repeat ||
          enterHeldRef.current ||
          updateLockRef.current
        ) {
          return;
        }

        enterHeldRef.current = true;

        const { col, key } = selectedRef.current;

        const item = (columnsRef.current[col] || []).find(
          current => itemKey(current) === key
        );

        if (item) {
          actionRef.current?.(item, NEXT_STATUSES[col]);
        }
      }
    };

    const onKeyUp = (event) => {
      if (event.key === 'Enter') {
        enterHeldRef.current = false;
      }
    };

    const onBlur = () => {
      enterHeldRef.current = false;
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', onBlur);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
    };
  }, [moveVertical, moveHorizontal]);

  const KanbanColumn = ({
    title,
    items,
    icon: Icon,
    color,
    nextStatus,
    nextLabel,
    columnIndex,
  }) => (
    <div className="flex-1 min-w-[280px] sm:min-w-[300px]">

      <div
        className={cn(
          'rounded-t-lg p-3 sm:p-4 flex items-center gap-2',
          color,
          selectedCol === columnIndex && 'ring-2 ring-primary'
        )}
      >
        <Icon className="h-5 w-5 sm:h-6 sm:w-6" />

        <h3 className="font-heading text-lg sm:text-xl">
          {title}
        </h3>

        <Badge variant="secondary" className="ml-auto">
          {items.length}
        </Badge>
      </div>

      <div className="bg-card border border-t-0 rounded-b-lg p-2 sm:p-4 min-h-[50vh] sm:min-h-[60vh] space-y-2 sm:space-y-4">

        {items.map(item => {
          const key = itemKey(item);

          const isSelected =
            selectedCol === columnIndex &&
            selectedKey === key;

          const refKey = `${columnIndex}:${key}`;

          return (
            <div
              key={key}
              ref={element => {
                if (element) {
                  cardRefs.current[refKey] = element;
                } else {
                  delete cardRefs.current[refKey];
                }
              }}
              style={{ scrollMarginTop: '90px' }}
            >
              <Card
                className={cn(
                  'border-l-4 transition-all cursor-pointer',
                  item.status === 'pending' &&
                    'border-l-amber-500',
                  item.status === 'preparing' &&
                    'border-l-blue-500',
                  item.status === 'ready' &&
                    'border-l-green-500',
                  isSelected &&
                    'ring-4 ring-primary ring-offset-2 ring-offset-background shadow-xl'
                )}
                onClick={() => chooseItem(columnIndex, key)}
                data-testid={`bar-item-${item.id}`}
              >
                <CardContent className="p-3 sm:p-4">

                  {isSelected && (
                    <div className="mb-2 px-2 py-1 rounded bg-primary text-primary-foreground text-xs font-bold uppercase inline-block">
                      ▶ SELECIONADO — ENTER PARA AVANÇAR
                    </div>
                  )}

                  <div className="flex justify-between items-start gap-2 mb-2">

                    {isOnlineOrder(item._order) ? (
                      <OnlineOrderBadge
                        order={item._order}
                        size="lg"
                      />
                    ) : (
                      <Badge
                        variant="outline"
                        className="font-heading text-base sm:text-lg"
                      >
                        Mesa {item.tableNumber}
                      </Badge>
                    )}

                    <span className="text-xs text-muted-foreground flex items-center gap-1 shrink-0">
                      <Clock className="h-3 w-3" />
                      {formatDate(item.orderCreatedAt)}
                    </span>
                  </div>

                  {item.waiterName && (
                    <p className="text-xs text-muted-foreground mb-1">
                      Garçom:{' '}
                      <span className="font-semibold text-foreground">
                        {item.waiterName}
                      </span>
                    </p>
                  )}

                  <div className="mb-3">

                    <p className="text-xl sm:text-2xl font-bold">
                      {item.quantity}x
                    </p>

                    <p className="text-lg sm:text-xl font-medium">
                      {item.product_name}
                    </p>

                    {item.notes && (
                      <p className="text-sm text-muted-foreground mt-1 p-2 bg-muted rounded">
                        📝 {item.notes}
                      </p>
                    )}
                  </div>

                  <Button
                    className="w-full min-h-14 touch-target font-heading uppercase tracking-wider text-sm sm:text-base"
                    disabled={updatingKey !== null}
                    onClick={(event) => {
                      event.stopPropagation();
                      chooseItem(columnIndex, key);
                      updateItemStatus(item, nextStatus);
                    }}
                    data-testid={`status-btn-${item.id}`}
                  >
                    {updatingKey === key
                      ? 'Atualizando...'
                      : nextLabel}
                  </Button>

                </CardContent>
              </Card>
            </div>
          );
        })}

        {items.length === 0 && (
          <div className="text-center py-8 sm:py-12 font-semibold text-muted-foreground">
            Nenhum item
          </div>
        )}

      </div>
    </div>
  );

  if (loading) {
    return (
      <Layout title="Painel do Bar">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Painel do Bar">
      <div
        className="space-y-3 sm:space-y-4"
        data-testid="bar-page"
      >

        {/* INDICADORES */}
        <div className="grid grid-cols-3 gap-2 sm:gap-4">

          <Card
            className="border-0 shadow-lg"
            style={{ backgroundColor: '#1E293B' }}
          >
            <CardContent className="p-3 sm:p-5 text-center">
              <p className="text-3xl sm:text-4xl font-heading font-bold text-white">
                {pendingItems.length}
              </p>
              <p className="text-sm sm:text-base font-semibold text-slate-300">
                Pendentes
              </p>
            </CardContent>
          </Card>

          <Card
            className="border-0 shadow-lg"
            style={{ backgroundColor: '#1D4ED8' }}
          >
            <CardContent className="p-3 sm:p-5 text-center">
              <p className="text-3xl sm:text-4xl font-heading font-bold text-white">
                {preparingItems.length}
              </p>
              <p className="text-sm sm:text-base font-semibold text-blue-100">
                Preparando
              </p>
            </CardContent>
          </Card>

          <Card
            className="border-0 shadow-lg"
            style={{ backgroundColor: '#16A34A' }}
          >
            <CardContent className="p-3 sm:p-5 text-center">
              <p className="text-3xl sm:text-4xl font-heading font-bold text-white">
                {readyItems.length}
              </p>
              <p className="text-sm sm:text-base font-semibold text-green-100">
                Prontos
              </p>
            </CardContent>
          </Card>

        </div>

        {/* INSTRUÇÕES */}
        <div
          className="text-sm text-muted-foreground flex flex-wrap gap-3"
          data-testid="bar-keyboard-hint"
        >
          <span>↑ ↓ Selecionar bebida</span>
          <span>← → Mudar coluna</span>
          <span className="font-bold text-foreground">
            ENTER = AVANÇAR STATUS
          </span>
        </div>

        {/* QUADRO DE PEDIDOS */}
        <div
          ref={boardRef}
          className="flex gap-2 sm:gap-4 overflow-x-auto pb-4 -mx-4 px-4 sm:mx-0 sm:px-0"
        >

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
