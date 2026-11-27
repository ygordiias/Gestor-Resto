import { bestPromoFor, fullPrice, orderSummary, promoActive } from './billing';

const drink = { id: 'p-caipi', category_id: 'c-drinks', price: 20 };
const burger = { id: 'p-burger', category_id: 'c-lanches', price: 30 };
const drinks50 = { id: 'a', name: 'Drinks 50%', discount_type: 'percent', discount_value: 50,
  category_ids: ['c-drinks'], product_ids: [] };

test('prévia da promoção: drink sai com 50%, lanche não', () => {
  expect(bestPromoFor([drinks50], drink, 20)).toEqual({ promo: drinks50, price: 10 });
  expect(bestPromoFor([drinks50], burger, 30)).toBeNull();
  expect(bestPromoFor([], drink, 20)).toBeNull();
});

test('vale a promoção de maior desconto', () => {
  const off12 = { id: 'b', name: 'R$ 12', discount_type: 'value', discount_value: 12,
    category_ids: [], product_ids: ['p-caipi'] };
  expect(bestPromoFor([drinks50, off12], drink, 20).promo.name).toBe('R$ 12');
});

test('desconto que zera o item não é promoção', () => {
  const off20 = { ...drinks50, discount_type: 'value', discount_value: 20 };
  expect(bestPromoFor([off20], drink, 20)).toBeNull();
});

test('Pago e Falta pagar', () => {
  const s = orderSummary({ total: 125.4, paid_amount: 50, subtotal: 114, service_fee: 11.4 });
  expect(s.paid).toBe(50);
  expect(s.remaining).toBe(75.4);
  expect(orderSummary({ total: 10 }).remaining).toBe(10);
});

test('preço cheio do item com promoção, desconto ou cortesia', () => {
  const promo = { promo_id: 'a', promo_price: 10, promo_original_price: 20, unit_price: 10 };
  expect(fullPrice(promo)).toBe(20);
  expect(promoActive(promo)).toBe(true);
  expect(promoActive({ ...promo, discount_original_price: 20, unit_price: 8 })).toBe(false);
  expect(fullPrice({ unit_price: 10.8, discount_original_price: 12 })).toBe(12);
  expect(fullPrice({ unit_price: 0, is_courtesy: true, courtesy_original_price: 30 })).toBe(30);
});
