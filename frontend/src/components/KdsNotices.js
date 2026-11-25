import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Volume2, VolumeX } from 'lucide-react';
import { kdsAPI } from '../lib/api';
import socketService from '../lib/socket';
import { formatDate } from '../lib/utils';
import { orderDisplayLabel } from './OnlineOrderBadge';

/**
 * Avisos comuns do KDS (Cozinha, Bar e Churrasqueira):
 * nova observação, pedido cancelado, item sem ligação e botão de som.
 * station: 'kitchen' | 'bar' | 'grill' (o "Ciente" vale para a tela).
 */

export function pendingObservations(order, station) {
  return (order?.observations || []).filter(obs => !obs?.acks?.[station]);
}

export function cancelledItemsFor(order, itemFilter) {
  return (order?.items || []).filter(item =>
    itemFilter({ ...item, status: item.status_before_cancel || item.status }));
}

export function cancelNeedsAck(order, station, itemFilter) {
  return (
    order?.status === 'cancelled' &&
    !order?.cancel_acks?.[station] &&
    cancelledItemsFor(order, itemFilter).length > 0
  );
}

function errorText(error, fallback) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

// Pedidos cancelados pela plataforma que ainda esperam "Ciente".
export function useCancelledOrders() {
  const [cancelled, setCancelled] = useState([]);
  const mounted = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const response = await kdsAPI.getCancelled();
      if (mounted.current && Array.isArray(response.data)) {
        setCancelled(response.data);
      }
    } catch (error) {
      console.warn('Erro ao carregar pedidos cancelados:', error?.message);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh();
    socketService.connect();
    socketService.on('kds_cancelled', () => refresh());
    const id = setInterval(refresh, 30000);
    return () => {
      mounted.current = false;
      socketService.off('kds_cancelled');
      clearInterval(id);
    };
  }, [refresh]);

  return { cancelled, refreshCancelled: refresh };
}

// O som toca sozinho. Este aviso só aparece se o navegador bloquear o autoplay.
export function SoundButton({ sound, dark = false }) {
  const base =
    'inline-flex items-center gap-2 rounded-lg px-4 py-2 font-bold text-sm border-2 min-h-11';
  if (!sound.blocked) {
    return (
      <span
        className={`${base} ${dark ? 'border-green-400 text-green-300' : 'border-green-600 text-green-700'}`}
        data-testid="kds-sound-on"
      >
        <Volume2 className="h-5 w-5" /> Som ativo
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`${base} bg-yellow-300 text-slate-950 border-yellow-500 animate-pulse`}
      onClick={sound.enable}
      data-testid="kds-sound-enable"
    >
      <VolumeX className="h-5 w-5" />
      Ativar som (o navegador bloqueou)
    </button>
  );
}

// Pedido simulado (/simular): faixa "TESTE" bem visível em todas as telas.
export function TestOrderBand({ order }) {
  if (!order?.is_test) return null;
  return (
    <div
      className="rounded bg-sky-500 text-white text-center py-1 text-sm font-black tracking-[0.3em]"
      data-testid="kds-test-order"
    >
      TESTE
    </div>
  );
}

export function UnlinkedItemBadge({ item }) {
  if (!item?.unlinked) return null;
  return (
    <span
      className="mt-1 inline-block rounded bg-fuchsia-600 text-white px-2 py-1 text-xs font-black uppercase tracking-wide"
      data-testid="kds-unlinked-item"
      title="Produto da NostFood sem ligação com o cardápio do Gestor: confira se é da cozinha ou do bar"
    >
      ⚠ ITEM SEM LIGAÇÃO — confira se é da cozinha ou do bar
    </span>
  );
}

export function ObservationBanners({ order, station, onAcked }) {
  const [busy, setBusy] = useState(null);
  const list = pendingObservations(order, station);
  if (list.length === 0) return null;

  const ack = async (event, obs) => {
    event.stopPropagation();
    if (busy) return;
    setBusy(obs.id);
    try {
      await kdsAPI.ackObservation(order.id, obs.id, station);
      onAcked?.();
    } catch (error) {
      toast.error(errorText(error, 'Não foi possível confirmar a observação'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-2">
      {list.map(obs => (
        <div
          key={obs.id}
          className="rounded-lg border-4 border-yellow-500 bg-yellow-300 text-slate-950 p-3"
          data-testid="kds-new-observation"
          onClick={event => event.stopPropagation()}
        >
          <p className="text-sm font-black uppercase tracking-wider">📢 NOVA OBSERVAÇÃO</p>
          <p className="text-lg font-black leading-snug break-words">{obs.text}</p>
          <p className="text-xs font-semibold">
            {obs.author_name || 'Caixa'} · {formatDate(obs.created_at)}
          </p>
          <button
            type="button"
            className="mt-2 w-full min-h-12 rounded-md bg-slate-950 text-yellow-300 font-black uppercase"
            disabled={busy === obs.id}
            onClick={event => ack(event, obs)}
            data-testid="kds-observation-ack"
          >
            {busy === obs.id ? 'Confirmando...' : 'Ciente'}
          </button>
        </div>
      ))}
    </div>
  );
}

// Cartões dos pedidos cancelados: esmaecidos, riscados, sem vermelho piscando.
export function CancelledOrdersPanel({ orders, station, itemFilter, onAcked, dark = false }) {
  const [busy, setBusy] = useState(null);
  const list = (orders || []).filter(order => cancelNeedsAck(order, station, itemFilter));
  if (list.length === 0) return null;

  const ack = async (order) => {
    if (busy) return;
    setBusy(order.id);
    try {
      await kdsAPI.ackCancel(order.id, station);
      onAcked?.();
    } catch (error) {
      toast.error(errorText(error, 'Não foi possível confirmar o cancelamento'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-2" data-testid="kds-cancelled-panel">
      <p className={`text-sm font-bold ${dark ? 'text-slate-300' : 'text-muted-foreground'}`}>
        Pedidos cancelados — não preparar. Toque em “Ciente” para tirar da tela.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {list.map(order => (
          <div
            key={order.id}
            className="rounded-xl border-4 border-slate-500 bg-slate-700 text-slate-100 p-4 space-y-2"
            data-testid={`kds-cancelled-${order.id}`}
          >
            <div className="rounded bg-slate-950 text-white text-center py-2 text-lg font-black tracking-[0.3em]">
              ✕ CANCELADO
            </div>
            <TestOrderBand order={order} />
            <div className="opacity-60 space-y-1">
              <p className="font-bold">
                {order.external_order_number
                  ? `Pedido ${orderDisplayLabel(order)}`
                  : `Mesa ${order.table_number ?? '—'}`}
                {order.customer_name ? ` · ${order.customer_name}` : ''}
              </p>
              {cancelledItemsFor(order, itemFilter).map(item => (
                <p key={item.id} className="text-lg font-bold line-through">
                  {item.quantity}× {item.product_name}
                </p>
              ))}
            </div>
            <p className="text-sm">
              <span className="font-bold">Motivo:</span> {order.cancellation_reason || 'não informado'}
            </p>
            <p className="text-xs opacity-80">
              Cancelado por {order.cancelled_by_name || '—'} · {formatDate(order.cancelled_at)}
            </p>
            <button
              type="button"
              className="w-full min-h-12 rounded-md bg-white text-slate-900 font-black uppercase"
              disabled={busy === order.id}
              onClick={() => ack(order)}
              data-testid="kds-cancel-ack"
            >
              {busy === order.id ? 'Confirmando...' : 'Ciente'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
