import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { io } from 'socket.io-client';
import FooterTecnoDias from '../components/FooterTecnoDias';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_MAP = {
  pending: { label: 'Recebido', color: '#fbbf24', bg: '#422006' },
  preparing: { label: 'Preparando', color: '#60a5fa', bg: '#172554' },
  ready: { label: 'Pronto', color: '#4ade80', bg: '#052e16' },
  delivered: { label: 'Entregue', color: '#86efac', bg: '#14532d' },
  cancelled: { label: 'Cancelado', color: '#ef4444', bg: '#3b1111' },
};

const STEPS = ['pending', 'preparing', 'ready', 'delivered'];

export default function AcompanharPage() {
  const { codigo } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchOrder = () => {
    fetch(`${API}/api/public/pedido/${codigo}`)
      .then(r => r.json())
      .then(setOrder)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchOrder();

    // Socket.IO para atualizações em tempo real
    const socket = io(API, { transports: ['websocket', 'polling'] });
    socket.on('order_updated', (data) => {
      if (data?.order_code === codigo) {
        fetchOrder();
      }
    });
    socket.on('kitchen_update', () => fetchOrder());
    socket.on('bar_update', () => fetchOrder());

    return () => socket.disconnect();
  }, [codigo]);

  const overallStatus = order?.status || 'pending';
  const currentStepIdx = STEPS.indexOf(overallStatus);

  if (loading) {
    return (
      <div className="emaus-app flex items-center justify-center min-h-screen">
        <p style={{ color: 'var(--emaus-text-muted)' }}>Carregando...</p>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="emaus-app flex flex-col items-center justify-center min-h-screen gap-4 px-4">
        <p style={{ color: 'var(--emaus-text-muted)' }}>Pedido nao encontrado</p>
        <button className="emaus-btn emaus-btn-outline" onClick={() => navigate('/cliente')}>
          Voltar ao cardapio
        </button>
      </div>
    );
  }

  return (
    <>
      <header className="emaus-header flex items-center gap-3">
        <button onClick={() => navigate('/cliente')} data-testid="back-home">
          <ArrowLeft size={22} style={{ color: 'var(--emaus-gold)' }} />
        </button>
        <h1 className="emaus-title text-lg font-bold flex-1">Pedido {order.order_code}</h1>
        <button onClick={fetchOrder} data-testid="refresh-btn">
          <RefreshCw size={18} style={{ color: 'var(--emaus-gold)' }} />
        </button>
      </header>

      <div className="px-4 py-6">
        {/* Timeline de status */}
        <div className="flex items-center justify-between mb-8 px-2">
          {STEPS.map((step, idx) => {
            const s = STATUS_MAP[step];
            const active = idx <= currentStepIdx;
            return (
              <React.Fragment key={step}>
                <div className="flex flex-col items-center gap-1">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold transition-all"
                    style={{
                      background: active ? s.bg : 'var(--emaus-bg-elevated)',
                      color: active ? s.color : 'var(--emaus-text-muted)',
                      border: active ? `2px solid ${s.color}` : '2px solid var(--emaus-border)',
                    }}
                  >
                    {idx + 1}
                  </div>
                  <span className="text-xs font-semibold" style={{ color: active ? s.color : 'var(--emaus-text-muted)' }}>
                    {s.label}
                  </span>
                </div>
                {idx < STEPS.length - 1 && (
                  <div
                    className="flex-1 h-0.5 mx-1"
                    style={{ background: idx < currentStepIdx ? 'var(--emaus-gold)' : 'var(--emaus-border)' }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Itens */}
        <div className="rounded-xl p-4 space-y-2"
          style={{ background: 'var(--emaus-bg-card)', border: '1px solid var(--emaus-border)' }}>
          <p className="font-semibold text-sm mb-2" style={{ color: 'var(--emaus-gold-light)' }}>Itens do pedido</p>
          {order.items.map((item, idx) => {
            const st = STATUS_MAP[item.status] || STATUS_MAP.pending;
            return (
              <div key={idx} className="flex items-center justify-between">
                <span className="text-sm" style={{ color: 'var(--emaus-cream)' }}>
                  {item.quantity}x {item.name}
                </span>
                <span className="emaus-status" style={{ background: st.bg, color: st.color }}>
                  {st.label}
                </span>
              </div>
            );
          })}
          <div className="flex justify-between mt-3 pt-3 font-bold"
            style={{ borderTop: '1px solid var(--emaus-border)' }}>
            <span style={{ color: 'var(--emaus-gold)' }}>Total</span>
            <span style={{ color: 'var(--emaus-gold)' }}>R$ {order.total.toFixed(2)}</span>
          </div>
        </div>

        {/* Pagamento */}
        <div className="mt-3 rounded-xl p-4"
          style={{ background: 'var(--emaus-bg-card)', border: '1px solid var(--emaus-border)' }}>
          <div className="flex justify-between text-sm">
            <span style={{ color: 'var(--emaus-text-muted)' }}>Pagamento</span>
            <span className="emaus-status"
              style={{
                background: order.payment_status === 'paid' ? '#052e16' : '#422006',
                color: order.payment_status === 'paid' ? '#4ade80' : '#fbbf24',
              }}>
              {order.payment_status === 'paid' ? 'Pago' : 'Pendente'}
            </span>
          </div>
        </div>
      </div>

      <FooterTecnoDias />
    </>
  );
}
