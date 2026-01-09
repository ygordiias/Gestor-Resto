import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { reportsAPI } from '../lib/api';
import { formatCurrency } from '../lib/utils';
import { toast } from 'sonner';
import { 
  TrendingUp, 
  DollarSign, 
  ShoppingCart,
  BarChart3,
  Download,
  Calendar
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell, Legend } from 'recharts';

const COLORS = ['#D4AF37', '#CD7F32', '#3E2723', '#8D6E63', '#A1887F', '#6D4C41', '#5D4037', '#4E342E'];

export default function ReportsPage() {
  const [salesData, setSalesData] = useState({ summary: {}, top_products: [] });
  const [profitData, setProfitData] = useState({});
  const [period, setPeriod] = useState('daily');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [period]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [salesRes, profitRes] = await Promise.all([
        reportsAPI.getSales(period),
        reportsAPI.getProfit(period),
      ]);
      setSalesData(salesRes.data);
      setProfitData(profitRes.data);
    } catch (error) {
      toast.error('Erro ao carregar relatórios');
    } finally {
      setLoading(false);
    }
  };

  const getPeriodLabel = () => {
    const labels = {
      daily: 'Hoje',
      weekly: 'Últimos 7 dias',
      monthly: 'Últimos 30 dias',
    };
    return labels[period];
  };

  const statCards = [
    {
      title: 'Total de Vendas',
      value: formatCurrency(salesData.summary?.total_sales || 0),
      icon: DollarSign,
      color: 'text-green-600',
      bg: 'bg-green-100 dark:bg-green-900/30',
    },
    {
      title: 'Pedidos',
      value: salesData.summary?.total_orders || 0,
      icon: ShoppingCart,
      color: 'text-blue-600',
      bg: 'bg-blue-100 dark:bg-blue-900/30',
    },
    {
      title: 'Ticket Médio',
      value: formatCurrency(salesData.summary?.avg_ticket || 0),
      icon: TrendingUp,
      color: 'text-primary',
      bg: 'bg-primary/10',
    },
    {
      title: 'Lucro Estimado',
      value: formatCurrency(profitData.profit || 0),
      icon: BarChart3,
      color: 'text-amber-600',
      bg: 'bg-amber-100 dark:bg-amber-900/30',
    },
  ];

  if (loading) {
    return (
      <Layout title="Relatórios">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Relatórios">
      <div className="space-y-6" data-testid="reports-page">
        {/* Period Selector */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <Tabs value={period} onValueChange={setPeriod}>
            <TabsList>
              <TabsTrigger value="daily" data-testid="period-daily">Diário</TabsTrigger>
              <TabsTrigger value="weekly" data-testid="period-weekly">Semanal</TabsTrigger>
              <TabsTrigger value="monthly" data-testid="period-monthly">Mensal</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Calendar className="h-4 w-4" />
            Período: {getPeriodLabel()}
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {statCards.map((stat, index) => (
            <Card key={index} className="card-hover">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">{stat.title}</p>
                    <p className="text-2xl font-heading font-bold mt-1">
                      {stat.value}
                    </p>
                  </div>
                  <div className={`p-3 rounded-full ${stat.bg}`}>
                    <stat.icon className={`h-6 w-6 ${stat.color}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Profit Details */}
        <Card>
          <CardHeader>
            <CardTitle className="font-heading">Análise de Lucro</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Receita Total</p>
                <p className="text-2xl font-bold text-green-600">
                  {formatCurrency(profitData.total_sales || 0)}
                </p>
              </div>
              <div className="text-center p-4 bg-muted rounded-lg">
                <p className="text-sm text-muted-foreground">Custo Estimado</p>
                <p className="text-2xl font-bold text-red-600">
                  {formatCurrency(profitData.estimated_cost || 0)}
                </p>
              </div>
              <div className="text-center p-4 bg-primary/10 rounded-lg">
                <p className="text-sm text-muted-foreground">Margem de Lucro</p>
                <p className="text-2xl font-bold text-primary">
                  {(profitData.margin_percentage || 0).toFixed(1)}%
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Top Products Bar Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="font-heading text-lg">
                Produtos Mais Vendidos
              </CardTitle>
            </CardHeader>
            <CardContent>
              {salesData.top_products?.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={salesData.top_products}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis 
                      dataKey="_id" 
                      tick={{ fontSize: 11 }}
                      angle={-45}
                      textAnchor="end"
                      height={100}
                    />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px'
                      }}
                    />
                    <Bar dataKey="quantity" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[350px] flex items-center justify-center text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </CardContent>
          </Card>

          {/* Revenue by Product Pie Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="font-heading text-lg">
                Receita por Produto
              </CardTitle>
            </CardHeader>
            <CardContent>
              {salesData.top_products?.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <PieChart>
                    <Pie
                      data={salesData.top_products.slice(0, 8)}
                      dataKey="revenue"
                      nameKey="_id"
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      label={({ _id, percent }) => 
                        percent > 0.05 ? `${(percent * 100).toFixed(0)}%` : ''
                      }
                    >
                      {salesData.top_products.slice(0, 8).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip 
                      formatter={(value) => formatCurrency(value)}
                      contentStyle={{ 
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px'
                      }}
                    />
                    <Legend 
                      layout="horizontal"
                      verticalAlign="bottom"
                      align="center"
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[350px] flex items-center justify-center text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Top Products Table */}
        <Card>
          <CardHeader>
            <CardTitle className="font-heading">Detalhamento de Vendas</CardTitle>
          </CardHeader>
          <CardContent>
            {salesData.top_products?.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-3 font-heading">Produto</th>
                      <th className="text-right p-3 font-heading">Quantidade</th>
                      <th className="text-right p-3 font-heading">Receita</th>
                    </tr>
                  </thead>
                  <tbody>
                    {salesData.top_products.map((product, idx) => (
                      <tr key={idx} className="border-b hover:bg-muted/50">
                        <td className="p-3">{product._id}</td>
                        <td className="p-3 text-right">{product.quantity}</td>
                        <td className="p-3 text-right font-bold text-primary">
                          {formatCurrency(product.revenue)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-center text-muted-foreground py-8">
                Nenhum dado disponível para o período selecionado
              </p>
            )}
          </CardContent>
        </Card>

        {/* Export Note */}
        <Card className="bg-muted/50">
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground text-center">
              📊 Exportação de relatórios (PDF/Excel) será implementada em versão futura
            </p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
