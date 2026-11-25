import { cancelNeedsAck, cancelledItemsFor, pendingCancelKeys, pendingObservations } from './KdsNotices';

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

const obsOrder = {
  id: 'o2',
  items: [
    { id: 's', type: 'food', status: 'preparing' },
    { id: 'k', type: 'drink', status: 'pending' },
  ],
  observations: [
    { id: 'o-item-food', item_id: 's', stations: ['kitchen', 'grill'], acks: {} },
    { id: 'o-item-drink', item_id: 'k', stations: ['bar'], acks: {} },
    { id: 'o-all', item_id: null, stations: ['kitchen', 'bar', 'grill'], acks: { kitchen: {} } },
    { id: 'o-old', text: 'sem telas', acks: {} },
  ],
};

test('observação de item só aparece na tela do item', () => {
  expect(pendingObservations(obsOrder, 'kitchen', isFood).map(o => o.id)).toEqual(['o-item-food', 'o-old']);
  expect(pendingObservations(obsOrder, 'bar', isDrink).map(o => o.id)).toEqual(['o-item-drink', 'o-all', 'o-old']);
});

test('Ciente da cozinha não tira o aviso do bar', () => {
  expect(pendingObservations(obsOrder, 'kitchen', isFood).some(o => o.id === 'o-all')).toBe(false);
  expect(pendingObservations(obsOrder, 'bar', isDrink).some(o => o.id === 'o-all')).toBe(true);
});

test('observação de pedido sem itens da tela não aparece nela', () => {
  const onlyDrinks = { ...obsOrder, items: [obsOrder.items[1]] };
  expect(pendingObservations(onlyDrinks, 'kitchen', isFood)).toEqual([]);
});
