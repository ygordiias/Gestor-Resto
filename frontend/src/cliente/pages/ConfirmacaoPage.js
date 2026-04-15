import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckCircle, MessageCircle, Search } from 'lucide-react';
import FooterTecnoDias from '../components/FooterTecnoDias';

const API = process.env.REACT_APP_BACKEND_URL;

export default function ConfirmacaoPage() {
  const { codigo } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/public/pedido/${codigo}`).then(r => r.json()),
      fetch(`${API}/api/public/config`).then(r => r.json()),
    ])
      .then(([orderData, configData]) => {
        setOrder(orderData);
        setConfig(configData);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [codigo]);

  const buildWhatsAppMsg = () => {
    if (!order) return '';
    let msg = `Pedido *${order.order_code}*\n\n`;
    order.items.forEach(i => {
      msg += `${i.quantity}x ${i.name}\n`;
    });
    msg += `\nTotal: *R$ ${order.total.toFixed(2)}*`;
    if (order.delivery_type) {
      msg += `\nEntrega: ${order.delivery_type === 'delivery' ? 'Delivery' : 'Retirada'}`;
    }
    return encodeURIComponent(msg);
  };

  const whatsappNumber = config?.whatsapp || '5516981214154';

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
      <div className="px-4 py-8 text-center emaus-fade-in">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-full mb-4"
          style={{ background: 'rgba(74, 222, 128, 0.15)' }}>
          <CheckCircle size={44} style={{ color: 'var(--emaus-success)' }} />
        </div>
        <h1 className="emaus-title text-2xl font-bold mb-1">Pedido Confirmado!</h1>
        <p className="text-4xl font-bold my-3" style={{ color: 'var(--emaus-gold)' }}
          data-testid="order-code">
          {order.order_code}
        </p>
        <p className="text-sm" style={{ color: 'var(--emaus-text-muted)' }}>
          Guarde este codigo para acompanhar
        </p>
      </div>

      <div className="px-4 space-y-3">
        {/* Resumo */}
        <div className="rounded-xl p-4"
          style={{ background: 'var(--emaus-bg-card)', border: '1px solid var(--emaus-border)' }}>
          {order.items.map((i, idx) => (
            <div key={idx} className="flex justify-between text-sm mb-1">
              <span style={{ color: 'var(--emaus-text-muted)' }}>{i.quantity}x {i.name}</span>
              <span style={{ color: 'var(--emaus-cream)' }}>{i.status}</span>
            </div>
          ))}
          <div className="flex justify-between mt-2 pt-2 font-bold"
            style={{ borderTop: '1px solid var(--emaus-border)' }}>
            <span style={{ color: 'var(--emaus-gold)' }}>Total</span>
            <span style={{ color: 'var(--emaus-gold)' }}>R$ {order.total.toFixed(2)}</span>
          </div>
        </div>

        {/* Botão WhatsApp */}
        <a
          href={`https://wa.me/${whatsappNumber}?text=${buildWhatsAppMsg()}`}
          target="_blank"
          rel="noopener noreferrer"
          className="emaus-btn emaus-btn-whatsapp w-full text-base"
          data-testid="whatsapp-btn"
        >
          <MessageCircle size={20} /> Enviar para WhatsApp
        </a>

        {/* Acompanhar */}
        <button
          className="emaus-btn emaus-btn-outline w-full"
          onClick={() => navigate(`/cliente/acompanhar/${codigo}`)}
          data-testid="track-btn"
        >
          <Search size={18} /> Acompanhar pedido
        </button>

        {/* Novo pedido */}
        <button
          className="emaus-btn emaus-btn-outline w-full"
          onClick={() => navigate('/cliente')}
        >
          Fazer novo pedido
        </button>
      </div>

      <FooterTecnoDias />
    </>
  );
}
