// Gestor Restô · criado e desenvolvido por Ygor Dias · Tecno Dias.
import React from 'react';

export default function Assinatura({ className = '' }) {
  return (
    <footer
      className={`text-center text-xs text-muted-foreground/70 ${className}`}
      data-testid="assinatura-autoria"
    >
      Gestor Restô · criado e desenvolvido por Ygor Dias · Tecno Dias
    </footer>
  );
}
