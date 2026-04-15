import React, { useState, useCallback } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import CardapioPage from './pages/CardapioPage';
import CarrinhoPage from './pages/CarrinhoPage';
import CheckoutPage from './pages/CheckoutPage';
import ConfirmacaoPage from './pages/ConfirmacaoPage';
import AcompanharPage from './pages/AcompanharPage';
import './emaus-theme.css';

export default function ClienteApp() {
  const [cart, setCart] = useState([]);

  const addToCart = useCallback((product) => {
    setCart(prev => {
      const existing = prev.find(i => i.product_id === product.id);
      if (existing) {
        return prev.map(i =>
          i.product_id === product.id ? { ...i, quantity: i.quantity + 1 } : i
        );
      }
      return [...prev, {
        product_id: product.id,
        name: product.name,
        price: product.price,
        quantity: 1,
        image_url: product.image_url,
      }];
    });
  }, []);

  const updateQuantity = useCallback((product_id, delta) => {
    setCart(prev =>
      prev
        .map(i => i.product_id === product_id ? { ...i, quantity: i.quantity + delta } : i)
        .filter(i => i.quantity > 0)
    );
  }, []);

  const clearCart = useCallback(() => setCart([]), []);
  const cartCount = cart.reduce((sum, i) => sum + i.quantity, 0);
  const cartTotal = cart.reduce((sum, i) => sum + i.price * i.quantity, 0);

  return (
    <div className="emaus-app">
      <Routes>
        <Route
          path="/"
          element={
            <CardapioPage
              cart={cart}
              cartCount={cartCount}
              addToCart={addToCart}
            />
          }
        />
        <Route
          path="/carrinho"
          element={
            <CarrinhoPage
              cart={cart}
              cartTotal={cartTotal}
              updateQuantity={updateQuantity}
              clearCart={clearCart}
            />
          }
        />
        <Route
          path="/checkout"
          element={
            <CheckoutPage
              cart={cart}
              cartTotal={cartTotal}
              clearCart={clearCart}
            />
          }
        />
        <Route path="/confirmacao/:codigo" element={<ConfirmacaoPage />} />
        <Route path="/acompanhar/:codigo" element={<AcompanharPage />} />
      </Routes>
    </div>
  );
}
