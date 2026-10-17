
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
import { formatDate } from '../lib/utils';
import socketService, { playNotificationSound } from '../lib/socket';
import { toast } from 'sonner';

import {
  Clock,
  Check,
  Timer,
  Bell,
  AlertTriangle,
} from 'lucide-react';

import {
  OnlineOrderBadge,
  isOnlineOrder,
} from '../components/OnlineOrderBadge';

const STAGES = [
  {
    status: 'pending',
    title: 'Novos pedidos',
    Icon: Clock,
    action: 'Iniciar pedido',
    next: 'preparing',
  },
  {
    status: 'preparing',
    title: 'Em preparo',
    Icon: Timer,
    action: 'Marcar pronto',
    next: 'ready',
  },
  {
    status: 'ready',
    title: 'Prontos',
    Icon: Check,
    action: 'Liberar / entregar',
    next: 'delivered',
  },
];

const groupKey = (group) => String(group.order.id);

function formatElapsed(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;

  return (
    `${String(minutes).padStart(2, '0')}:` +
    `${String(remaining).padStart(2, '0')}`
  );
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

  return {
    delivery,
    elapsed,
    limit,
    late,
    warning,
  };
}

function getCardStyle(timing) {
  if (timing.late) {
    return {
      backgroundColor: '#991b1b',
      borderColor: '#f87171',
      color: '#fff',
    };
  }

  if (timing.warning) {
    return {
      backgroundColor: '#92400e',
      borderColor: '#fbbf24',
      color: '#fff',
    };
  }

  return {
    backgroundColor: '#14532d',
    borderColor: '#4ade80',
    color: '#fff',
  };
}

export default function KitchenPage() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());
  const [busyKey, setBusyKey] = useState(null);

  // Seleção pelo teclado
  const [selectedCol, setSelectedCol] = useState(0);
  const [selectedKey, setSelectedKey] = useState(null);

  const mounted = useRef(false);
  const pendingIds = useRef(new Set());
  const initialized = useRef(false);

  // Proteção contra comandos repetidos
  const busyRef = useRef(false);
  const enterHeldRef = useRef(false);

  // Referências de navegação e rolagem
  const columnsRef = useRef([[], [], []]);
  const selectionRef = useRef({
    col: 0,
    key: null,
  });

  const cardRefs = useRef({});
  const updateActionRef = useRef(null);
  const fetchVersionRef = useRef(0);

  // Recebe e organiza atualizações dos pedidos
  const applyOrders = useCallback((incoming) => {
    if (!mounted.current || !Array.isArray(incoming)) {
      return;
    }

    const next = new Set();

    incoming.forEach(order => {
      (order.items || []).forEach(item => {
        if (
          item.type === 'food' &&
          item.status === 'pending'
        ) {
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
        icon: <Bell className="h-4 w-4" />,
      });
    }

    initialized.current = true;
    pendingIds.current = next;

    setOrders(incoming);
    setLoading(false);
  }, []);

  // Busca os pedidos abertos
  const fetchOrders = useCallback(async () => {
    const version = ++fetchVersionRef.current;

    try {
      const response = await ordersAPI.getOpen();

      if (
        !mounted.current ||
        version !== fetchVersionRef.current ||
        busyRef.current
      ) {
        return;
      }

      applyOrders(response.data);
    } catch (error) {
      console.error(
        'Erro ao carregar pedidos da cozinha:',
        error
      );

      if (mounted.current) {
        setLoading(false);
      }
    }
  }, [applyOrders]);

  // WebSocket, atualização periódica e cronômetro
  useEffect(() => {
    mounted.current = true;

    const handleKitchenUpdate = (incoming) => {
      if (!mounted.current) return;

      // Evita trocar a lista enquanto uma comanda
      // está sendo atualizada manualmente
      if (busyRef.current) return;

      ++fetchVersionRef.current;
      applyOrders(incoming);
    };

    fetchOrders();

    socketService.connect();
    socketService.joinRoom('kitchen');
    socketService.on(
      'kitchen_update',
      handleKitchenUpdate
    );

    const refresh = setInterval(fetchOrders, 30000);

    const clock = setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => {
      mounted.current = false;

      socketService.off('kitchen_update');
      socketService.leaveRoom('kitchen');

      clearInterval(refresh);
      clearInterval(clock);
    };
  }, [fetchOrders, applyOrders]);

  // Agrupa os itens por comanda e etapa
  const groupsByStage = STAGES.map(stage =>
    orders
      .map(order => ({
        order,
        items: (order.items || []).filter(
          item =>
            item.type === 'food' &&
            item.status === stage.status
        ),
      }))
      .filter(group => group.items.length > 0)
      .sort((a, b) => {
        const dateA = new Date(
          a.order.created_at
        ).getTime();

        const dateB = new Date(
          b.order.created_at
        ).getTime();

        return (
          (Number.isFinite(dateA) && Number.isFinite(dateB)
            ? dateA - dateB
            : 0) ||
          groupKey(a).localeCompare(groupKey(b))
        );
      })
  );

  columnsRef.current = groupsByStage;

  // Seleciona uma comanda de forma estável
  const chooseGroup = useCallback((col, key) => {
    selectionRef.current = {
      col,
      key,
    };

    setSelectedCol(col);
    setSelectedKey(key);
  }, []);

  // Mantém a seleção quando pedidos entram,
  // mudam de status ou saem da tela
  useEffect(() => {
    const current = groupsByStage[selectedCol] || [];

    if (
      selectedKey !== null &&
      current.some(group => groupKey(group) === selectedKey)
    ) {
      return;
    }

    if (current.length > 0) {
      chooseGroup(
        selectedCol,
        groupKey(current[0])
      );

      return;
    }

    const firstAvailable = groupsByStage.findIndex(
      groups => groups.length > 0
    );

    if (firstAvailable >= 0) {
      chooseGroup(
        firstAvailable,
        groupKey(groupsByStage[firstAvailable][0])
      );
    } else if (selectedKey !== null) {
      chooseGroup(selectedCol, null);
    }
  }, [
    orders,
    selectedCol,
    selectedKey,
    chooseGroup,
  ]);

  // ROLAGEM AUTOMÁTICA
  // Faz a tela acompanhar a comanda selecionada
  useLayoutEffect(() => {
    if (selectedKey === null) return;

    const refKey = `${selectedCol}:${selectedKey}`;

    let frame1;
    let frame2;

    frame1 = requestAnimationFrame(() => {
      frame2 = requestAnimationFrame(() => {
        const card = cardRefs.current[refKey];

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

  // SETA PARA CIMA E PARA BAIXO
  const moveVertical = useCallback(
    (direction) => {
      const { col, key } = selectionRef.current;

      const groups = columnsRef.current[col] || [];

      if (groups.length === 0) return;

      const currentIndex = groups.findIndex(
        group => groupKey(group) === key
      );

      const nextIndex = Math.max(
        0,
        Math.min(
          groups.length - 1,
          currentIndex < 0
            ? 0
            : currentIndex + direction
        )
      );

      chooseGroup(
        col,
        groupKey(groups[nextIndex])
      );
    },
    [chooseGroup]
  );

  // SETA PARA ESQUERDA E DIREITA
  const moveHorizontal = useCallback(
    (direction) => {
      const { col } = selectionRef.current;

      const nextCol = col + direction;

      if (
        nextCol < 0 ||
        nextCol >= STAGES.length
      ) {
        return;
      }

      const groups =
        columnsRef.current[nextCol] || [];

      chooseGroup(
        nextCol,
        groups.length > 0
          ? groupKey(groups[0])
          : null
      );
    },
    [chooseGroup]
  );

  // Atualiza todos os itens de uma comanda
  const updateGroup = useCallback(
    async (order, items, newStatus) => {
      if (
        busyRef.current ||
        !order ||
        !items ||
        items.length === 0
      ) {
        return;
      }

      busyRef.current = true;

      const key = `${order.id}:${newStatus}`;
      setBusyKey(key);

      const sourceCol = STAGES.findIndex(
        stage => stage.next === newStatus
      );

      const currentGroups =
        columnsRef.current[sourceCol] || [];

      const currentIndex = currentGroups.findIndex(
        group =>
          String(group.order.id) === String(order.id)
      );

      const remaining = currentGroups.filter(
        group =>
          String(group.order.id) !== String(order.id)
      );

      const nextGroup = remaining[
        Math.min(
          Math.max(currentIndex, 0),
          remaining.length - 1
        )
      ];

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
          toast.success(
            `${success} item(ns) atualizado(s) com sucesso.`
          );
        } else {
          toast.error(
            `${success} de ${items.length} itens atualizados. Confira os restantes.`
          );
        }

        // Notifica os garçons quando os alimentos ficam prontos
        if (newStatus === 'ready') {
          items.forEach((item, index) => {
            if (
              results[index].status === 'fulfilled'
            ) {
              socketService.emit('item_ready', {
                tableNumber: order.table_number,
                productName: item.product_name,
                type: 'food',
              });
            }
          });
        }

        // Após atualizar, seleciona a próxima comanda
        if (
          success === items.length &&
          selectionRef.current.key === String(order.id)
        ) {
          if (nextGroup) {
            chooseGroup(
              sourceCol,
              groupKey(nextGroup)
            );
          } else {
            const otherCol =
              columnsRef.current.findIndex(
                (groups, index) =>
                  index !== sourceCol &&
                  groups.length > 0
              );

            if (otherCol >= 0) {
              chooseGroup(
                otherCol,
                groupKey(
                  columnsRef.current[otherCol][0]
                )
              );
            } else {
              chooseGroup(sourceCol, null);
            }
          }
        }

        // Atualiza a lista com o estado do servidor
        ++fetchVersionRef.current;

        const response = await ordersAPI.getOpen();

        if (mounted.current) {
          applyOrders(response.data);
        }
      } catch (error) {
        console.error(
          'Erro ao atualizar pedido:',
          error
        );

        toast.error(
          'Erro ao atualizar o pedido. Confira o status.'
        );
      } finally {
        busyRef.current = false;

        if (mounted.current) {
          setBusyKey(null);
          fetchOrders();
        }
      }
    },
    [chooseGroup, applyOrders, fetchOrders]
  );

  updateActionRef.current = updateGroup;

  // CONTROLE COMPLETO PELO TECLADO
  useEffect(() => {
    const onKeyDown = (event) => {
      const target = event.target;

      // Não interfere em campos de texto
      if (
        target?.closest?.(
          'input, textarea, select, [contenteditable="true"]'
        )
      ) {
        return;
      }

      // Não interfere em atalhos do navegador
      if (
        event.ctrlKey ||
        event.altKey ||
        event.metaKey
      ) {
        return;
      }

      const allowedKeys = [
        'ArrowUp',
        'ArrowDown',
        'ArrowLeft',
        'ArrowRight',
        'Enter',
      ];

      if (!allowedKeys.includes(event.key)) {
        return;
      }

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
          busyRef.current
        ) {
          return;
        }

        enterHeldRef.current = true;

        const { col, key } =
          selectionRef.current;

        const group = (
          columnsRef.current[col] || []
        ).find(
          current => groupKey(current) === key
        );

        if (!group) return;

        const nextStatus = STAGES[col]?.next;

        if (!nextStatus) return;

        updateActionRef.current?.(
          group.order,
          group.items,
          nextStatus
        );
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

    window.addEventListener(
      'keydown',
      onKeyDown
    );

    window.addEventListener(
      'keyup',
      onKeyUp
    );

    window.addEventListener(
      'blur',
      onBlur
    );

    return () => {
      window.removeEventListener(
        'keydown',
        onKeyDown
      );

      window.removeEventListener(
        'keyup',
        onKeyUp
      );

      window.removeEventListener(
        'blur',
        onBlur
      );
    };
  }, [moveVertical, moveHorizontal]);

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
      <div
        className="space-y-4"
        data-testid="kitchen-page"
      >

        {/* INDICADORES */}
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

        {/* LEGENDA */}
        <div className="text-sm text-muted-foreground">
          Cada cartão representa uma comanda ou pedido.
          Verde: no prazo · Laranja: atenção · Vermelho: atrasado.
        </div>

        {/* INSTRUÇÕES DO TECLADO */}
        <div
          className="flex flex-wrap items-center gap-2 text-sm"
          data-testid="kitchen-keyboard-hint"
        >

          <span className="px-3 py-2 rounded-lg bg-muted border font-medium">
            ↑ ↓ Selecionar comanda
          </span>

          <span className="px-3 py-2 rounded-lg bg-muted border font-medium">
            ← → Mudar coluna
          </span>

          <span className="px-3 py-2 rounded-lg bg-primary text-primary-foreground font-bold">
            ENTER = AVANÇAR STATUS
          </span>

        </div>

        {/* COLUNAS DA COZINHA */}
        <div className="flex gap-3 overflow-x-auto pb-4">

          {STAGES.map((stage, index) => (
            <div
              key={stage.status}
              className="flex-1 min-w-[300px]"
            >

              {/* CABEÇALHO DA COLUNA */}
              <div
                className={
                  'rounded-t-lg bg-slate-800 text-white p-3 ' +
                  'flex items-center gap-2 ' +
                  (
                    selectedCol === index
                      ? 'ring-2 ring-primary'
                      : ''
                  )
                }
              >
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

              {/* CARTÕES */}
              <div className="bg-card border rounded-b-lg p-2 space-y-3 min-h-[55vh]">

                {groupsByStage[index].map(
                  ({ order, items }) => {
                    const timing = getTiming(order, now);
                    const key = `${order.id}:${stage.next}`;

                    const selectionKey = String(order.id);

                    const isSelected =
                      selectedCol === index &&
                      selectedKey === selectionKey;

                    const refKey =
                      `${index}:${selectionKey}`;

                    return (
                      <div
                        key={order.id}
                        ref={element => {
                          if (element) {
                            cardRefs.current[refKey] = element;
                          } else {
                            delete cardRefs.current[refKey];
                          }
                        }}
                        style={{
                          scrollMarginTop: '90px',
                        }}
                      >
                        <Card
                          className={
                            'border-2 cursor-pointer transition-shadow ' +
                            (
                              isSelected
                                ? 'ring-4 ring-yellow-300 ring-offset-2 ring-offset-background shadow-2xl'
                                : ''
                            )
                          }
                          style={getCardStyle(timing)}
                          onClick={() =>
                            chooseGroup(
                              index,
                              selectionKey
                            )
                          }
                          data-testid={`kitchen-order-${order.id}`}
                        >

                          <CardContent className="p-3 space-y-3">

                            {/* IDENTIFICAÇÃO DO PEDIDO */}
                            {isSelected && (
                              <div className="bg-yellow-300 text-slate-950 px-3 py-2 rounded font-black text-xs sm:text-sm uppercase">
                                ▶ COMANDA SELECIONADA — ENTER PARA AVANÇAR
                              </div>
                            )}

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

                              {/* CRONÔMETRO E ALERTAS */}
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

                            {/* ITENS DA COMANDA */}
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

                            {/* GARÇOM */}
                            {order.waiter_name && (
                              <p className="text-xs">
                                Garçom: {order.waiter_name}
                              </p>
                            )}

                            {/* BOTÃO DE STATUS */}
                            <Button
                              className="w-full min-h-14 font-bold text-base"
                              variant="secondary"
                              disabled={busyKey !== null}
                              onClick={(event) => {
                                event.stopPropagation();

                                chooseGroup(
                                  index,
                                  selectionKey
                                );

                                updateGroup(
                                  order,
                                  items,
                                  stage.next
                                );
                              }}
                              data-testid={`kitchen-status-${order.id}`}
                            >
                              {busyKey === key
                                ? 'Atualizando...'
                                : stage.action}
                            </Button>

                          </CardContent>
                        </Card>
                      </div>
                    );
                  }
                )}

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
