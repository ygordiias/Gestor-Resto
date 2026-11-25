import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Label } from './ui/label';
import { ordersAPI } from '../lib/api';

// Itens que ainda aparecem no KDS: só eles podem receber observação.
const KDS_STATUSES = ['pending', 'preparing', 'ready'];
const MAX_TEXT = 500;

export function observableItems(order) {
  return (order?.items || []).filter(item =>
    KDS_STATUSES.includes(item.status) && (item.type === 'food' || item.type === 'drink'));
}

/**
 * Observação nova para a cozinha/bar em qualquer pedido aberto (mesa, comanda,
 * balcão, online, NostFood). Escolhe um item ou o pedido inteiro.
 */
export default function AddObservationDialog({ order, open, onOpenChange, onSent }) {
  const [text, setText] = useState('');
  const [target, setTarget] = useState('');
  const [sending, setSending] = useState(false);
  const items = observableItems(order);

  useEffect(() => {
    if (open) {
      setText('');
      setTarget('');
    }
  }, [open]);

  const send = async () => {
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    try {
      await ordersAPI.addObservation(order.id, value, target || null);
      const item = items.find(i => i.id === target);
      toast.success(item
        ? `Observação enviada (${item.product_name})`
        : 'Observação enviada para a cozinha e o bar');
      onOpenChange(false);
      onSent?.();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Erro ao enviar observação');
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="add-observation-dialog">
        <DialogHeader>
          <DialogTitle>Adicionar observação</DialogTitle>
          <DialogDescription>
            Aparece em destaque no KDS, com som, até a cozinha ou o bar tocar em “Ciente”.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="observation-target">Para</Label>
            <select
              id="observation-target"
              className="w-full min-h-10 rounded-md border bg-background px-3 text-sm"
              value={target}
              onChange={event => setTarget(event.target.value)}
              data-testid="observation-target"
            >
              <option value="">Pedido inteiro</option>
              {items.map(item => (
                <option key={item.id} value={item.id}>
                  {item.quantity}× {item.product_name} ({item.type === 'drink' ? 'bar' : 'cozinha'})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="observation-text">Observação</Label>
            <Textarea
              id="observation-text"
              rows={3}
              maxLength={MAX_TEXT}
              value={text}
              onChange={event => setText(event.target.value)}
              placeholder="Ex.: tirar picles do Sansão"
              data-testid="observation-text"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={send} disabled={!text.trim() || sending} data-testid="observation-send">
            {sending ? 'Enviando...' : 'Enviar observação'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
