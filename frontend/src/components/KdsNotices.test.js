import { cancelNeedsAck, cancelledItemsFor, pendingCancelKeys } from './KdsNotices';

const isFood = item => item.type === 'food';
const isDrink = item => item.type === 'drink';

const tableOrder = {
  id: 'o1',
  status: 'pending',
  table_number: 5,
  items: [
    { id: 'a', type: 'food', status: 'preparing' },
    {
      id: 'b', type: 'food', status: 'cancelled', status_before_cancel: 'pending',
      kds_item_cancel: true, kds_ack_pending: true, cancel_acks: {},
      cancellation_reason: 'desistiu', cancelled_by_name: 'Admin',
    },
    { id: 'c', type: 'drink', status: 'pending' },
  ],
};

test('item cancelado de mesa aparece só na tela do item', () => {
  const kitchen = cancelledItemsFor(tableOrder, isFood, 'kitchen');
  expect(kitchen.wholeOrder).toBe(false);
  expect(kitchen.items.map(i => i.id)).toEqual(['b']);
  expect(cancelNeedsAck(tableOrder, 'bar', isDrink)).toBe(false);
  expect(pendingCancelKeys([tableOrder], 'kitchen', isFood)).toEqual(['o1:b']);
});

test('item sai da tela depois do Ciente dela', () => {
  const acked = {
    ...tableOrder,
    items: tableOrder.items.map(i => (i.id === 'b' ? { ...i, cancel_acks: { kitchen: {} } } : i)),
  };
  expect(cancelNeedsAck(acked, 'kitchen', isFood)).toBe(false);
});

test('pedido de salão cancelado: card inteiro com os itens de cada tela', () => {
  const cancelled = {
    ...tableOrder,
    status: 'cancelled',
    cancel_acks: {},
    items: [
      { id: 'a', type: 'food', status: 'pending' },
      { id: 'c', type: 'drink', status: 'pending' },
      { id: 'old', type: 'drink', status: 'cancelled' },
    ],
  };
  const bar = cancelledItemsFor(cancelled, isDrink, 'bar');
  expect(bar.wholeOrder).toBe(true);
  expect(bar.items.map(i => i.id)).toEqual(['c']);
  expect(pendingCancelKeys([cancelled], 'kitchen', isFood)).toEqual(['o1']);
  const kitchenAcked = { ...cancelled, cancel_acks: { kitchen: {} } };
  expect(cancelNeedsAck(kitchenAcked, 'kitchen', isFood)).toBe(false);
  expect(cancelNeedsAck(kitchenAcked, 'bar', isDrink)).toBe(true);
});

test('pedido NostFood cancelado usa o status de antes do cancelamento', () => {
  const nostfood = {
    id: 'n1', status: 'cancelled', cancel_acks: {}, external_order_number: '99-1',
    items: [{ id: 'x', type: 'food', status: 'cancelled', status_before_cancel: 'preparing' }],
  };
  expect(cancelledItemsFor(nostfood, isFood, 'grill').items.map(i => i.id)).toEqual(['x']);
});
