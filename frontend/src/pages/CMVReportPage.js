import React, { useState, useEffect, useMemo } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { cmvAPI } from '../lib/api';
import { formatCurrency, cn } from '../lib/utils';
import { toast } from 'sonner';
import {
  Calculator,
  TrendingUp,
  TrendingDown,
  Award,
  Search,
  Loader2,
  CircleDollarSign,
  Percent,
  Package,
} from 'lucide-react';

const ORDERINGS = [
  { value: 'margin_desc', label: 'Maior margem' },
  { value: 'margin_asc', label: 'Menor margem' },
  { value: 'profit_desc', label: 'Maior lucro' },
  { value: 'profit_asc', label: 'Menor lucro' },
  { value: 'name_asc', label: 'Nome (A-Z)' },
];

function marginColor(margin) {
  if (margin > 60) return 'text-emerald-500';
  if (margin >= 40) return 'text-amber-400';
  return 'text-destructive';
}

function marginBadge(margin) {
  if (margin > 60) return 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30';
  if (margin >= 40) return 'bg-amber-400/10 text-amber-400 border-amber-400/30';
  return 'bg-destructive/10 text-destructive border-destructive/30';
}

export default function CMVReportPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [ordering, setOrdering] = useState('margin_desc');
  const [filter, setFilter] = useState('all'); // all | with_recipe | without_recipe

  useEffect(() => {
    let active = true;
    cmvAPI.getReport()
      .then(res => { if (active) setRows(res.data || []); })
      .catch(() => toast.error('Erro ao carregar relatorio de CMV'))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  // Estatisticas no topo (apenas produtos com receita e preco > 0)
  const stats = useMemo(() => {
    const withRecipe = rows.filter(r => r.has_recipe && r.sale_price > 0);
    if (withRecipe.length === 0) {
      return {
        countWithRecipe: 0,
        countTotal: rows.length,
        avgCost: 0,
        avgMargin: 0,
        mostProfitable: null,
      };
    }
    const avgCost = withRecipe.reduce((s, r) => s + (r.cost || 0), 0) / withRecipe.length;
    const avgMargin = withRecipe.reduce((s, r) => s + (r.margin || 0), 0) / withRecipe.length;
    const mostProfitable = [...withRecipe].sort((a, b) => b.profit - a.profit)[0];
    return {
      countWithRecipe: withRecipe.length,
      countTotal: rows.length,
      avgCost,
      avgMargin,
      mostProfitable,
    };
  }, [rows]);

  const displayed = useMemo(() => {
    let arr = [...rows];
    const term = search.trim().toLowerCase();
    if (term) arr = arr.filter(r => r.product_name.toLowerCase().includes(term));
    if (filter === 'with_recipe') arr = arr.filter(r => r.has_recipe);
    if (filter === 'without_recipe') arr = arr.filter(r => !r.has_recipe);
    switch (ordering) {
      case 'margin_desc': arr.sort((a, b) => b.margin - a.margin); break;
      case 'margin_asc': arr.sort((a, b) => a.margin - b.margin); break;
      case 'profit_desc': arr.sort((a, b) => b.profit - a.profit); break;
      case 'profit_asc': arr.sort((a, b) => a.profit - b.profit); break;
      case 'name_asc': arr.sort((a, b) => a.product_name.localeCompare(b.product_name)); break;
      default: break;
    }
    return arr;
  }, [rows, search, ordering, filter]);

  if (loading) {
    return (
      <Layout title="Relatorio CMV">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Relatorio CMV">
      <div className="space-y-6" data-testid="cmv-report-page">
        {/* Cards de estatisticas */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          <Card data-testid="stat-with-recipe">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/15 p-2.5">
                  <Package className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Com Receita</p>
                  <p className="text-xl font-bold font-heading">
                    {stats.countWithRecipe}
                    <span className="text-xs text-muted-foreground font-normal ml-1">
                      / {stats.countTotal}
                    </span>
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card data-testid="stat-avg-cost">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-amber-400/15 p-2.5">
                  <CircleDollarSign className="h-5 w-5 text-amber-400" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">CMV medio</p>
                  <p className="text-xl font-bold font-heading">{formatCurrency(stats.avgCost)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card data-testid="stat-avg-margin">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className={cn('rounded-lg p-2.5', stats.avgMargin > 60 ? 'bg-emerald-500/15' : stats.avgMargin >= 40 ? 'bg-amber-400/15' : 'bg-destructive/15')}>
                  <Percent className={cn('h-5 w-5', marginColor(stats.avgMargin))} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Margem media</p>
                  <p className={cn('text-xl font-bold font-heading', marginColor(stats.avgMargin))}>
                    {stats.avgMargin.toFixed(1)}%
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card data-testid="stat-top-product">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-emerald-500/15 p-2.5">
                  <Award className="h-5 w-5 text-emerald-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider">Mais lucrativo</p>
                  {stats.mostProfitable ? (
                    <>
                      <p className="text-sm font-bold font-heading truncate" title={stats.mostProfitable.product_name}>
                        {stats.mostProfitable.product_name}
                      </p>
                      <p className="text-xs text-emerald-500 font-semibold">
                        {formatCurrency(stats.mostProfitable.profit)} <span className="opacity-70">· {stats.mostProfitable.margin.toFixed(1)}%</span>
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">Cadastre receitas</p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filtros */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar produto..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              data-testid="cmv-search"
            />
          </div>
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-full sm:w-56" data-testid="cmv-filter">
              <SelectValue placeholder="Filtrar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os produtos</SelectItem>
              <SelectItem value="with_recipe">Apenas com receita</SelectItem>
              <SelectItem value="without_recipe">Sem receita</SelectItem>
            </SelectContent>
          </Select>
          <Select value={ordering} onValueChange={setOrdering}>
            <SelectTrigger className="w-full sm:w-56" data-testid="cmv-ordering">
              <SelectValue placeholder="Ordenar" />
            </SelectTrigger>
            <SelectContent>
              {ORDERINGS.map(o => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tabela */}
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm" data-testid="cmv-table">
              <thead className="bg-muted/40">
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 font-heading font-semibold">Produto</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Preco Venda</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Custo</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Lucro</th>
                  <th className="text-right px-4 py-3 font-heading font-semibold">Margem %</th>
                  <th className="text-center px-4 py-3 font-heading font-semibold">Receita</th>
                </tr>
              </thead>
              <tbody>
                {displayed.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-10 text-muted-foreground">
                      Nenhum produto encontrado
                    </td>
                  </tr>
                ) : (
                  displayed.map(r => (
                    <tr key={r.product_id} className="border-b border-border/50 hover:bg-muted/30 transition-colors" data-testid={`cmv-row-${r.product_id}`}>
                      <td className="px-4 py-3 font-medium">{r.product_name}</td>
                      <td className="px-4 py-3 text-right">{formatCurrency(r.sale_price)}</td>
                      <td className="px-4 py-3 text-right">
                        {r.has_recipe ? formatCurrency(r.cost) : <span className="text-muted-foreground italic">—</span>}
                      </td>
                      <td className={cn('px-4 py-3 text-right font-semibold', r.has_recipe ? (r.profit >= 0 ? 'text-emerald-500' : 'text-destructive') : 'text-muted-foreground')}>
                        {r.has_recipe ? formatCurrency(r.profit) : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {r.has_recipe ? (
                          <Badge variant="outline" className={cn('font-semibold', marginBadge(r.margin))}>
                            {r.margin > 60 ? <TrendingUp className="h-3 w-3 mr-1" /> : r.margin < 40 ? <TrendingDown className="h-3 w-3 mr-1" /> : null}
                            {r.margin.toFixed(1)}%
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground italic">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {r.has_recipe ? (
                          <span className="inline-flex items-center text-xs text-emerald-500">
                            <Calculator className="h-3 w-3 mr-1" /> Sim
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">Sem receita</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Legenda */}
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full bg-emerald-500" /> Margem &gt; 60%
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full bg-amber-400" /> 40% — 60%
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full bg-destructive" /> &lt; 40%
          </span>
        </div>
      </div>
    </Layout>
  );
}
