import React from 'react';
import { UtensilsCrossed } from 'lucide-react';
import { cn } from '../lib/utils';

export function Logo({ size = 'md', className }) {
  const sizes = {
    sm: { icon: 'h-4 w-4', text: 'text-base', gap: 'gap-1.5' },
    md: { icon: 'h-5 w-5', text: 'text-xl', gap: 'gap-2' },
    lg: { icon: 'h-8 w-8', text: 'text-3xl', gap: 'gap-3' },
    xl: { icon: 'h-10 w-10', text: 'text-4xl', gap: 'gap-3' },
  };

  const s = sizes[size] || sizes.md;

  return (
    <div className={cn('flex items-center', s.gap, className)} data-testid="app-logo">
      <div className="flex items-center justify-center rounded-lg bg-primary/15 p-1.5">
        <UtensilsCrossed className={cn(s.icon, 'text-primary')} />
      </div>
      <div className="flex flex-col leading-none">
        <span className={cn('font-heading font-bold tracking-tight text-foreground', s.text)}>
          Gestor <span className="text-primary">Restô</span>
        </span>
      </div>
    </div>
  );
}
