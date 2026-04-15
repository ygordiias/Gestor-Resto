import React, { useState, useEffect } from 'react';
import { Search } from 'lucide-react';
import ProdutoCard from '../components/ProdutoCard';
import CategoriaNav from '../components/CategoriaNav';
import CarrinhoFlutuante from '../components/CarrinhoFlutuante';
import FooterTecnoDias from '../components/FooterTecnoDias';

const API = process.env.REACT_APP_BACKEND_URL;

export default function CardapioPage({ cart, cartCount, addToCart }) {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedCat, setSelectedCat] = useState(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/public/cardapio`)
      .then(r => r.json())
      .then(data => {
        setProducts(data.products || []);
        setCategories(data.categories || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = products.filter(p => {
    const matchCat = !selectedCat || p.category_id === selectedCat;
    const matchSearch = !search || p.name.toLowerCase().includes(search.toLowerCase());
    return matchCat && matchSearch;
  });

  return (
    <>
      <header className="emaus-header">
        <h1 className="emaus-title text-xl font-bold text-center">Gestor Resto</h1>
        <p className="text-center text-xs mt-0.5" style={{ color: 'var(--emaus-text-muted)' }}>
          Cardapio Digital
        </p>
      </header>

      <div className="px-4 py-3">
        <div className="relative mb-3">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--emaus-text-muted)' }} />
          <input
            className="emaus-input pl-10"
            placeholder="Buscar no cardapio..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            data-testid="search-input"
          />
        </div>

        <CategoriaNav categories={categories} selected={selectedCat} onSelect={setSelectedCat} />
      </div>

      <main className="px-4 pb-24">
        {loading ? (
          <div className="text-center py-12" style={{ color: 'var(--emaus-text-muted)' }}>
            Carregando cardapio...
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-12" style={{ color: 'var(--emaus-text-muted)' }}>
            Nenhum produto encontrado
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {filtered.map(p => (
              <ProdutoCard key={p.id} product={p} onAdd={addToCart} />
            ))}
          </div>
        )}
      </main>

      <CarrinhoFlutuante count={cartCount} />
      <FooterTecnoDias />
    </>
  );
}
