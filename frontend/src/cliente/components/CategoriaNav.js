import React from 'react';

export default function CategoriaNav({ categories, selected, onSelect }) {
  return (
    <div
      className="flex gap-2 overflow-x-auto pb-2 px-1 no-scrollbar"
      style={{ WebkitOverflowScrolling: 'touch' }}
      data-testid="category-nav"
    >
      <button
        className={`emaus-cat-pill ${!selected ? 'active' : ''}`}
        onClick={() => onSelect(null)}
      >
        Todos
      </button>
      {categories.map(cat => (
        <button
          key={cat.id}
          className={`emaus-cat-pill ${selected === cat.id ? 'active' : ''}`}
          onClick={() => onSelect(cat.id)}
        >
          {cat.icon} {cat.name}
        </button>
      ))}
    </div>
  );
}
