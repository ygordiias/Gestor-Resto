import React from 'react';
import { Plus } from 'lucide-react';

export default function ProdutoCard({ product, onAdd }) {
  return (
    <div className="emaus-product-card emaus-fade-in" data-testid={`product-${product.id}`}>
      {product.image_url ? (
        <img
          src={product.image_url}
          alt={product.name}
          className="emaus-product-img"
          loading="lazy"
        />
      ) : (
        <div className="emaus-product-img flex items-center justify-center text-3xl">
          🍽
        </div>
      )}
      <div className="p-3">
        <h3 className="font-semibold text-sm" style={{ color: 'var(--emaus-cream)' }}>
          {product.name}
        </h3>
        {product.description && (
          <p className="text-xs mt-0.5" style={{ color: 'var(--emaus-text-muted)' }}>
            {product.description}
          </p>
        )}
        <div className="flex items-center justify-between mt-2">
          <span className="font-bold" style={{ color: 'var(--emaus-gold)' }}>
            R$ {product.price.toFixed(2)}
          </span>
          <button
            className="emaus-btn-primary"
            style={{ padding: '0.4rem 0.65rem', borderRadius: '8px', fontSize: '0.8rem' }}
            onClick={() => onAdd(product)}
            data-testid={`add-${product.id}`}
          >
            <Plus size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
