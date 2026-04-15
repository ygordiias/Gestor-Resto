import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ShoppingCart } from 'lucide-react';

export default function CarrinhoFlutuante({ count }) {
  const navigate = useNavigate();

  if (count === 0) return null;

  return (
    <div
      className="emaus-cart-float"
      onClick={() => navigate('/cliente/carrinho')}
      data-testid="cart-float-btn"
    >
      <ShoppingCart size={24} />
      <span className="emaus-cart-badge" data-testid="cart-badge">{count}</span>
    </div>
  );
}
