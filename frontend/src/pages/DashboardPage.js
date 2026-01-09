import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { ordersAPI, tablesAPI, reportsAPI, productsAPI } from '../lib/api';
import { formatCurrency } from '../lib/utils';
import { 
  DollarSign, 
  ShoppingCart, 
  UtensilsCrossed, 
  TrendingUp,
  Package,
  Users,
  Clock,
  AlertTriangle
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

const COLORS = ['#D4AF37', '#CD7F32', '#3E2723', '#8D6E63', '#A1887F'];

export default function DashboardPage() {
  const [stats, setStats] = useState({
    totalSales: 0,
    totalOrders: 0,
    avgTicket: 0,
    openTables: 0,
  });
  const [topProducts, setTopProducts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const [salesRes, tablesRes, ordersRes] = await Promise.all([
        reportsAPI.getSales('daily'),
        tablesAPI.getAll(),
        ordersAPI.getOpen(),
      ]);

      const summary = salesRes.data.summary || {};
      const tables = tablesRes.data || [];
      const openOrders = ordersRes.data || [];

      setStats({
        totalSales: summary.total_sales || 0,
        totalOrders: summary.total_orders || 0,
        avgTicket: summary.avg_ticket || 0,
        openTables: tables.filter(t => t.status === 'occupied').length,
      });

      setTopProducts(salesRes.data.top_products || []);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    {
      title: 'Vendas Hoje',
      value: formatCurrency(stats.totalSales),
      icon: DollarSign,
      color: 'text-green-600',
      bg: 'bg-green-100 dark:bg-green-900/30',
    },
    {
      title: 'Pedidos',
      value: stats.totalOrders,
      icon: ShoppingCart,
      color: 'text-blue-600',
      bg: 'bg-blue-100 dark:bg-blue-900/30',
    },
    {
      title: 'Ticket Médio',
      value: formatCurrency(stats.avgTicket),
      icon: TrendingUp,
      color: 'text-primary',
      bg: 'bg-primary/10',
    },
    {
      title: 'Mesas Ocupadas',
      value: stats.openTables,
      icon: UtensilsCrossed,
      color: 'text-orange-600',
      bg: 'bg-orange-100 dark:bg-orange-900/30',
    },
  ];

  return (
    <Layout title="Dashboard">
      <div className="space-y-6" data-testid="dashboard">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {statCards.map((stat, index) => (
            <Card key={index} className="card-hover" data-testid={`stat-card-${index}`}>
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
              {topProducts.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={topProducts}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis 
                      dataKey="_id" 
                      tick={{ fontSize: 12 }}
                      angle={-45}
                      textAnchor="end"
                      height={80}
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
                <div className="h-[300px] flex items-center justify-center text-muted-foreground">
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
              {topProducts.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={topProducts.slice(0, 5)}
                      dataKey="revenue"
                      nameKey="_id"
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      label={({ _id, percent }) => `${_id} (${(percent * 100).toFixed(0)}%)`}
                    >
                      {topProducts.slice(0, 5).map((entry, index) => (
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
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions */}
        <Card>
          <CardHeader>
            <CardTitle className="font-heading text-lg">
              Ações Rápidas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <a
                href="/tables"
                className="flex flex-col items-center p-4 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                data-testid="quick-action-tables"
              >
                <UtensilsCrossed className="h-8 w-8 text-primary mb-2" />
                <span className="text-sm font-medium">Ver Mesas</span>
              </a>
              <a
                href="/menu"
                className="flex flex-col items-center p-4 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                data-testid="quick-action-menu"
              >
                <Package className="h-8 w-8 text-primary mb-2" />
                <span className="text-sm font-medium">Cardápio</span>
              </a>
              <a
                href="/reports"
                className="flex flex-col items-center p-4 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                data-testid="quick-action-reports"
              >
                <TrendingUp className="h-8 w-8 text-primary mb-2" />
                <span className="text-sm font-medium">Relatórios</span>
              </a>
              <a
                href="/users"
                className="flex flex-col items-center p-4 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                data-testid="quick-action-users"
              >
                <Users className="h-8 w-8 text-primary mb-2" />
                <span className="text-sm font-medium">Usuários</span>
              </a>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
