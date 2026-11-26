// Relatórios › Promoções: total concedido por promoção e por dia, separado do
// desconto manual e da cortesia de item (GET /reports/promotions).
import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { reportsAPI } from '../lib/api';
import { apiError } from '../lib/billing';
import { formatCurrency } from '../lib/utils';
import { toast } from 'sonner';

const isoDay = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const br = (iso) => (iso || '').split('-').reverse().join('/');

export default function PromotionsReport({ summary }) {
  const [start, setStart] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return isoDay(d);
  });
  const [end, setEnd] = useState(() => isoDay(new Date()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await reportsAPI.getPromotions(start, end);
      setData(res.data);
    } catch (e) {
      toast.error(apiError(e, 'Erro ao carregar o relatório de promoções'));
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const cards = [
    ['Promoções', summary?.item_promo_total, 'text-emerald-700'],
    ['Descontos manuais', summary?.item_discount_total, 'text-amber-700'],
    ['Cortesias de item', summary?.item_courtesy_total, 'text-purple-700'],
  ];

  return (
    <div className="space-y-4" data-testid="promotions-report">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {cards.map(([label, value, color]) => (
          <Card key={label}>
            <CardContent className="p-4">
              <p className="text-sm text-muted-foreground">{label} (período acima)</p>
              <p className={`text-xl font-heading font-bold ${color}`}>{formatCurrency(value || 0)}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-heading">Promoções concedidas</CardTitle>
          <CardDescription>
            Quanto cada promoção deixou de cobrar nas vendas fechadas, separado do desconto manual e da cortesia.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="space-y-1">
              <Label>De</Label>
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Até</Label>
              <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
            <Button onClick={load} disabled={loading}>{loading ? 'Carregando...' : 'Atualizar'}</Button>
          </div>

          {data && (
            <>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <p>Promoções: <strong className="text-emerald-700">{formatCurrency(data.totals.promo)}</strong></p>
                <p>Descontos: <strong className="text-amber-700">{formatCurrency(data.totals.discount)}</strong></p>
                <p>Cortesias: <strong className="text-purple-700">{formatCurrency(data.totals.courtesy)}</strong></p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b">
                      <th className="py-2">Promoção</th>
                      <th className="py-2 text-right">Unidades</th>
                      <th className="py-2 text-right">Pedidos</th>
                      <th className="py-2 text-right">Concedido</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_promotion.length === 0 && (
                      <tr><td colSpan={4} className="py-3 text-muted-foreground">Nenhuma promoção no período.</td></tr>
                    )}
                    {data.by_promotion.map((row) => (
                      <tr key={row.promo_id} className="border-b">
                        <td className="py-2">{row.name}</td>
                        <td className="py-2 text-right">{row.units}</td>
                        <td className="py-2 text-right">{row.orders}</td>
                        <td className="py-2 text-right font-medium">{formatCurrency(row.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {data.by_day.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground border-b">
                        <th className="py-2">Dia</th>
                        <th className="py-2 text-right">Promoções</th>
                        <th className="py-2 text-right">Descontos</th>
                        <th className="py-2 text-right">Cortesias</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.by_day.map((row) => (
                        <tr key={row.date} className="border-b">
                          <td className="py-2">{br(row.date)}</td>
                          <td className="py-2 text-right">{formatCurrency(row.promo)}</td>
                          <td className="py-2 text-right">{formatCurrency(row.discount)}</td>
                          <td className="py-2 text-right">{formatCurrency(row.courtesy)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
