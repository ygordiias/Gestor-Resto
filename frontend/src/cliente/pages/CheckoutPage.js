import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import FooterTecnoDias from '../components/FooterTecnoDias';

const API = process.env.REACT_APP_BACKEND_URL;

export default function CheckoutPage({ cart, cartTotal, clearCart }) {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({
    customer_name: '',
    customer_phone: '',
    delivery_type: 'retirada',
    address: '',
    payment_method: 'pix',
    change_for: '',
  });
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API}/api/public/config`).then(r => r.json()).then(setConfig).catch(() => {});
  }, []);

  useEffect(() => {
    if (cart.length === 0) navigate('/cliente');
  }, [cart, navigate]);

  const deliveryFee = form.delivery_type === 'delivery' ? (config?.delivery_fee || 5) : 0;
  const total = cartTotal + deliveryFee;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!form.customer_name.trim()) { setError('Informe seu nome'); return; }
    if (!form.customer_phone.trim()) { setError('Informe seu telefone'); return; }
    if (form.delivery_type === 'delivery' && !form.address.trim()) { setError('Informe o endereco'); return; }

    setSending(true);
    try {
      const body = {
        customer_name: form.customer_name.trim(),
        customer_phone: form.customer_phone.trim(),
        delivery_type: form.delivery_type,
        address: form.delivery_type === 'delivery' ? form.address.trim() : null,
        payment_method: form.payment_method,
        change_for: form.payment_method === 'cash' && form.change_for ? parseFloat(form.change_for) : null,
        items: cart.map(i => ({
          product_id: i.product_id,
          name: i.name,
          price: i.price,
          quantity: i.quantity,
        })),
      };

      const res = await fetch(`${API}/api/public/pedido`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Erro ao criar pedido');
      }

      const data = await res.json();
      clearCart();
      navigate(`/cliente/confirmacao/${data.order_code}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }));

  return (
    <>
      <header className="emaus-header flex items-center gap-3">
        <button onClick={() => navigate('/cliente/carrinho')} data-testid="back-to-cart">
          <ArrowLeft size={22} style={{ color: 'var(--emaus-gold)' }} />
        </button>
        <h1 className="emaus-title text-lg font-bold">Finalizar Pedido</h1>
      </header>

      <form onSubmit={handleSubmit} className="px-4 py-4 pb-8 space-y-4">
        {/* Dados pessoais */}
        <div>
          <label className="emaus-label">Nome</label>
          <input className="emaus-input" placeholder="Seu nome" value={form.customer_name}
            onChange={e => set('customer_name', e.target.value)} data-testid="input-name" />
        </div>
        <div>
          <label className="emaus-label">Telefone</label>
          <input className="emaus-input" placeholder="(16) 99999-9999" value={form.customer_phone}
            onChange={e => set('customer_phone', e.target.value)} data-testid="input-phone" />
        </div>

        {/* Tipo de entrega */}
        <div>
          <label className="emaus-label">Tipo de entrega</label>
          <div className="flex gap-2">
            {['retirada', 'delivery'].map(t => (
              <button key={t} type="button"
                className={`emaus-cat-pill flex-1 text-center ${form.delivery_type === t ? 'active' : ''}`}
                onClick={() => set('delivery_type', t)}
                data-testid={`delivery-${t}`}
              >
                {t === 'retirada' ? 'Retirar no local' : 'Delivery'}
              </button>
            ))}
          </div>
        </div>

        {form.delivery_type === 'delivery' && (
          <div className="emaus-fade-in">
            <label className="emaus-label">Endereco</label>
            <input className="emaus-input" placeholder="Rua, numero, bairro..."
              value={form.address} onChange={e => set('address', e.target.value)} data-testid="input-address" />
          </div>
        )}

        {/* Pagamento */}
        <div>
          <label className="emaus-label">Forma de pagamento</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { key: 'pix', label: 'PIX' },
              { key: 'card', label: 'Cartao' },
              { key: 'cash', label: 'Dinheiro' },
            ].map(m => (
              <button key={m.key} type="button"
                className={`emaus-cat-pill text-center ${form.payment_method === m.key ? 'active' : ''}`}
                onClick={() => set('payment_method', m.key)}
                data-testid={`pay-${m.key}`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {form.payment_method === 'cash' && (
          <div className="emaus-fade-in">
            <label className="emaus-label">Troco para</label>
            <input className="emaus-input" type="number" placeholder="Ex: 100.00"
              value={form.change_for} onChange={e => set('change_for', e.target.value)} data-testid="input-change" />
          </div>
        )}

        {/* Resumo */}
        <div className="rounded-xl p-4" style={{ background: 'var(--emaus-bg-card)', border: '1px solid var(--emaus-border)' }}>
          <p className="font-semibold mb-2" style={{ color: 'var(--emaus-gold-light)' }}>Resumo</p>
          {cart.map(i => (
            <div key={i.product_id} className="flex justify-between text-sm mb-1">
              <span style={{ color: 'var(--emaus-text-muted)' }}>{i.quantity}x {i.name}</span>
              <span style={{ color: 'var(--emaus-cream)' }}>R$ {(i.price * i.quantity).toFixed(2)}</span>
            </div>
          ))}
          {deliveryFee > 0 && (
            <div className="flex justify-between text-sm mt-2 pt-2" style={{ borderTop: '1px solid var(--emaus-border)' }}>
              <span style={{ color: 'var(--emaus-text-muted)' }}>Taxa de entrega</span>
              <span style={{ color: 'var(--emaus-cream)' }}>R$ {deliveryFee.toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between mt-2 pt-2 font-bold" style={{ borderTop: '1px solid var(--emaus-border)' }}>
            <span style={{ color: 'var(--emaus-gold)' }}>Total</span>
            <span style={{ color: 'var(--emaus-gold)' }}>R$ {total.toFixed(2)}</span>
          </div>
        </div>

        {error && (
          <div className="rounded-lg p-3 text-sm font-semibold" style={{ background: '#3b1111', color: '#ef4444' }} data-testid="checkout-error">
            {error}
          </div>
        )}

        <button
          type="submit"
          className="emaus-btn emaus-btn-primary w-full text-base"
          disabled={sending}
          data-testid="submit-order"
        >
          {sending ? <Loader2 size={20} className="animate-spin" /> : 'Confirmar Pedido'}
        </button>
      </form>

      <FooterTecnoDias />
    </>
  );
}
