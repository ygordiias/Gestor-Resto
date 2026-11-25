import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { nostfoodAPI, productsAPI } from '../lib/api';
import { formatDate } from '../lib/utils';

// Mesma regra do servidor: ignora maiúsculas, acentos e espaços extras.
const plain = v => String(v || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();

// Ligações vêm em pares (chave por id e por nome): uma linha por item da NostFood.
function groupLinks(rows) {
  const byItem = new Map();
  for (const r of rows || []) {
    const id = r.nostfood_id ? `id:${r.nostfood_id}` : `name:${plain(r.nostfood_name)}`;
    if (!byItem.has(id)) byItem.set(id, { ...r, nostfood_key: id });
  }
  return [...byItem.values()].sort((a, b) => String(a.nostfood_name).localeCompare(String(b.nostfood_name)));
}

function errorText(error, fallback) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** Configurações › NostFood: estado da integração, produtos sem ligação e simulação. */
export default function NostfoodPanel() {
  const [status, setStatus] = useState(null);
  const [unlinked, setUnlinked] = useState([]);
  const [links, setLinks] = useState([]);
  const [products, setProducts] = useState([]);
  const [choice, setChoice] = useState({});
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const [st, un, pr, ln] = await Promise.all([
        nostfoodAPI.status(),
        nostfoodAPI.unlinked(),
        productsAPI.getAll(),
        nostfoodAPI.links(),
      ]);
      setStatus(st.data);
      setUnlinked(un.data || []);
      setLinks(groupLinks(ln.data));
      setProducts((pr.data || []).slice().sort((a, b) => a.name.localeCompare(b.name)));
    } catch (error) {
      toast.error(errorText(error, 'Erro ao carregar a integração NostFood'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Sugestão: produto do Gestor com o mesmo nome do item da NostFood.
  const suggested = row => products.find(p => plain(p.name) === plain(row.nostfood_name));
  const chosenId = row => choice[row.nostfood_key] || suggested(row)?.id || '';

  const link = async (row, uiKey = row.nostfood_key) => {
    const productId = choice[uiKey] || (uiKey === row.nostfood_key ? suggested(row)?.id : '');
    if (!productId) {
      toast.error('Escolha o produto do Gestor');
      return;
    }
    const product = products.find(p => p.id === productId);
    if (product && plain(product.name) !== plain(row.nostfood_name) && !window.confirm(
      `Ligar o item da NostFood "${row.nostfood_name}" ao produto "${product.name}"?\n` +
      'Os nomes são diferentes: confira antes de confirmar.'
    )) return;
    setBusy(uiKey);
    try {
      const res = await nostfoodAPI.link({
        nostfood_id: row.nostfood_id,
        nostfood_name: row.nostfood_name,
        product_id: productId,
      });
      const kept = res.data.kept_stock_deducted
        ? ` · ${res.data.kept_stock_deducted} item(ns) que já baixaram estoque não foram alterados`
        : '';
      toast.success(`Produto ligado (${res.data.open_orders_updated} pedido(s) aberto(s) atualizado(s))${kept}`);
      setChoice(prev => {
        const next = { ...prev };
        delete next[uiKey];
        return next;
      });
      await load();
    } catch (error) {
      toast.error(errorText(error, 'Erro ao ligar o produto'));
    } finally {
      setBusy(null);
    }
  };

  const deleteTests = async () => {
    if (!window.confirm('Apagar TODOS os pedidos de teste (simulados)?')) return;
    setBusy('delete');
    try {
      const res = await nostfoodAPI.deleteTests();
      toast.success(`${res.data.deleted} pedido(s) de teste apagado(s)`);
    } catch (error) {
      toast.error(errorText(error, 'Erro ao apagar pedidos de teste'));
    } finally {
      setBusy(null);
    }
  };

  const simulate = async (paymentMethod) => {
    setBusy('simulate');
    try {
      const res = await nostfoodAPI.simulate({ payment_method: paymentMethod });
      toast.success(`Pedido de teste ${res.data.order?.external_order_number} criado (só no Gestor)`);
      await load();
    } catch (error) {
      toast.error(errorText(error, 'Erro ao simular pedido'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="nostfood-panel">
      <Card>
        <CardHeader>
          <CardTitle className="font-heading">Integração NostFood (iFood / 99)</CardTitle>
          <CardDescription>
            Os pedidos entram sozinhos e vão para cozinha, bar e caixa. A configuração fica nas
            variáveis de ambiente do servidor.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {status ? (
            <>
              <p>
                Situação: <strong>{status.enabled ? 'LIGADA' : 'DESLIGADA'}</strong>
                {' · '}Chave da API: {status.has_api_key ? 'configurada' : 'faltando'}
                {' · '}Segredo do webhook: {status.has_webhook_secret ? 'configurado' : 'faltando'}
                {' · '}Envio de status para a NostFood:{' '}
                {status.send_status ? 'LIGADO' : 'desligado (só registra no log)'}
              </p>
              <p>
                Polling a cada {status.poll_seconds} s · Última consulta:{' '}
                {status.last_poll_at ? formatDate(status.last_poll_at) : '—'}
                {status.last_poll_error && (
                  <span className="text-destructive"> · Erro: {status.last_poll_error}</span>
                )}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">Carregando...</p>
          )}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button variant="outline" disabled={busy !== null} onClick={() => simulate('pix_online')}
              data-testid="nostfood-simulate-online">
              Simular pedido pago online
            </Button>
            <Button variant="outline" disabled={busy !== null} onClick={() => simulate('dinheiro')}
              data-testid="nostfood-simulate-collect">
              Simular pedido a cobrar na entrega
            </Button>
            <Button variant="destructive" disabled={busy !== null} onClick={deleteTests}
              data-testid="nostfood-delete-tests">
              Apagar pedidos de teste
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            A simulação cria 1 Sansão “sem picles” + 2 Coca-Cola lata só no Gestor, com a faixa TESTE: não envia
            nada para a NostFood, não mexe em estoque e fica fora do caixa, das vendas e do CMV.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-heading">Produtos sem ligação</CardTitle>
          <CardDescription>
            Itens da NostFood que ainda não correspondem a um produto do Gestor. Eles vão para a
            cozinha por padrão e não baixam estoque até serem ligados.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {unlinked.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum produto sem ligação.</p>
          )}
          {unlinked.map(row => (
            <div key={row.nostfood_key} className="flex flex-col sm:flex-row sm:items-center gap-2 border rounded p-3"
              data-testid="nostfood-unlinked-row">
              <div className="flex-1 min-w-0">
                <p className="font-bold truncate">{row.nostfood_name || row.nostfood_key}</p>
                <p className="text-xs text-muted-foreground">
                  {row.nostfood_id ? `ID NostFood ${row.nostfood_id} · ` : ''}
                  {row.occurrences || 1} ocorrência(s) · último pedido {row.last_order_number || '—'}
                </p>
              </div>
              <Select
                value={chosenId(row)}
                onValueChange={value => setChoice(prev => ({ ...prev, [row.nostfood_key]: value }))}
              >
                <SelectTrigger className="w-full sm:w-64">
                  <SelectValue placeholder="Produto do Gestor" />
                </SelectTrigger>
                <SelectContent>
                  {products.map(p => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name} ({p.type === 'drink' ? 'bar' : 'cozinha'})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button disabled={busy !== null} onClick={() => link(row)}>
                {busy === row.nostfood_key ? 'Ligando...' : 'Ligar'}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-heading">Produtos ligados</CardTitle>
          <CardDescription>
            Para corrigir uma ligação errada, escolha o produto certo e clique em Refazer. Os pedidos
            abertos são corrigidos (itens que já baixaram estoque não mudam).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {links.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum produto ligado.</p>
          )}
          {links.map(row => {
            const uiKey = `relink:${row.nostfood_key}`;
            const mismatch = plain(row.product_name) !== plain(row.nostfood_name);
            return (
              <div key={uiKey} className="flex flex-col sm:flex-row sm:items-center gap-2 border rounded p-3"
                data-testid="nostfood-link-row">
                <div className="flex-1 min-w-0">
                  <p className="font-bold truncate">{row.nostfood_name || row.nostfood_key}</p>
                  <p className={`text-xs ${mismatch ? 'text-destructive font-bold' : 'text-muted-foreground'}`}>
                    → {row.product_name}{mismatch ? ' (nome diferente: confira)' : ''}
                  </p>
                </div>
                <Select
                  value={choice[uiKey] || ''}
                  onValueChange={value => setChoice(prev => ({ ...prev, [uiKey]: value }))}
                >
                  <SelectTrigger className="w-full sm:w-64">
                    <SelectValue placeholder="Trocar para..." />
                  </SelectTrigger>
                  <SelectContent>
                    {products.map(p => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name} ({p.type === 'drink' ? 'bar' : 'cozinha'})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant="outline" disabled={busy !== null || !choice[uiKey]} onClick={() => link(row, uiKey)}>
                  {busy === uiKey ? 'Refazendo...' : 'Refazer'}
                </Button>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
