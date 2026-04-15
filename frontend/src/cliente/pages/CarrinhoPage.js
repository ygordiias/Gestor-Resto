import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Minus, Plus, Trash2 } from 'lucide-react';
import FooterTecnoDias from '../components/FooterTecnoDias';

export default function CarrinhoPage({ cart, cartTotal, updateQuantity, clearCart }) {
  const navigate = useNavigate();

  return (
    <>
      <header className="emaus-header flex items-center gap-3">
        <button onClick={() => navigate('/cliente')} data-testid="back-to-menu">
          <ArrowLeft size={22} style={{ color: 'var(--emaus-gold)' }} />
        </button>
        <h1 className="emaus-title text-lg font-bold">Carrinho</h1>
      </header>

      <main className="px-4 py-4 pb-32">
        {cart.length === 0 ? (
          <div className="text-center py-16 emaus-fade-in">
            <p className="text-lg mb-2" style={{ color: 'var(--emaus-text-muted)' }}>Carrinho vazio</p>
            <button
              className="emaus-btn emaus-btn-outline"
              onClick={() => navigate('/cliente')}
            >
              Ver cardapio
            </button>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {cart.map(item => (
                <div
                  key={item.product_id}
                  className="flex items-center gap-3 p-3 rounded-xl emaus-fade-in"
                  style={{ background: 'var(--emaus-bg-card)', border: '1px solid var(--emaus-border)' }}
                  data-testid={`cart-item-${item.product_id}`}
                >
                  {item.image_url ? (
                    <img src={item.image_url} alt={item.name} className="w-16 h-16 rounded-lg object-cover" />
                  ) : (
                    <div className="w-16 h-16 rounded-lg flex items-center justify-center text-2xl"
                      style={{ background: 'var(--emaus-bg-elevated)' }}>
                      🍽
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate" style={{ color: 'var(--emaus-cream)' }}>
                      {item.name}
                    </p>
                    <p className="text-sm font-bold" style={{ color: 'var(--emaus-gold)' }}>
                      R$ {(item.price * item.quantity).toFixed(2)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="w-8 h-8 rounded-lg flex items-center justify-center"
                      style={{ background: 'var(--emaus-bg-elevated)', color: 'var(--emaus-gold)' }}
                      onClick={() => updateQuantity(item.product_id, -1)}
                      data-testid={`minus-${item.product_id}`}
                    >
                      {item.quantity === 1 ? <Trash2 size={14} /> : <Minus size={14} />}
                    </button>
                    <span className="w-6 text-center font-bold text-sm">{item.quantity}</span>
                    <button
                      className="w-8 h-8 rounded-lg flex items-center justify-center"
                      style={{ background: 'var(--emaus-gold)', color: '#1a1510' }}
                      onClick={() => updateQuantity(item.product_id, 1)}
                      data-testid={`plus-${item.product_id}`}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <button
              className="emaus-btn emaus-btn-outline w-full mt-4"
              onClick={clearCart}
              data-testid="clear-cart"
            >
              Limpar carrinho
            </button>
          </>
        )}
      </main>

      {cart.length > 0 && (
        <div
          className="fixed bottom-0 left-0 right-0 p-4"
          style={{ background: 'var(--emaus-bg-card)', borderTop: '1px solid var(--emaus-border)' }}
        >
          <div className="flex justify-between mb-3">
            <span style={{ color: 'var(--emaus-text-muted)' }}>Total</span>
            <span className="text-lg font-bold" style={{ color: 'var(--emaus-gold)' }}>
              R$ {cartTotal.toFixed(2)}
            </span>
          </div>
          <button
            className="emaus-btn emaus-btn-primary w-full text-base"
            onClick={() => navigate('/cliente/checkout')}
            data-testid="go-checkout"
          >
            Finalizar pedido
          </button>
        </div>
      )}

      <FooterTecnoDias />
    </>
  );
}
