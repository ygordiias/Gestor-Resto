import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { tablesAPI, ordersAPI } from '../lib/api';
import { cn, getTableStatusColor, getTableStatusLabel, formatCurrency } from '../lib/utils';
import { useAuth } from '../contexts/AuthContext';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import { Users, Clock, Plus } from 'lucide-react';

export default function TablesPage() {
  const [tables, setTables] = useState([]);
  const [orders, setOrders] = useState({});
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    let isMounted = true;
    
    const handleTablesUpdate = (updatedTables) => {
      if (isMounted) setTables(updatedTables);
    };

    const fetchDataSafe = async () => {
      if (!isMounted) return;
      try {
        const [tablesRes, ordersRes] = await Promise.all([
          tablesAPI.getAll(),
          ordersAPI.getOpen(),
        ]);

        if (isMounted) {
          setTables(tablesRes.data);
          const ordersMap = {};
          ordersRes.data.forEach(order => {
            ordersMap[order.table_id] = order;
          });
          setOrders(ordersMap);
        }
      } catch (error) {
        if (isMounted) toast.error('Erro ao carregar mesas');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchDataSafe();
    socketService.connect();
    socketService.on('tables_updated', handleTablesUpdate);

    return () => {
      isMounted = false;
      socketService.off('tables_updated');
    };
  }, []);

  const handleTableClick = (table) => {
    navigate(`/order/${table.id}`, { state: { table } });
  };

  const getTableOrder = (tableId) => orders[tableId];

  if (loading) {
    return (
      <Layout title="Mesas">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando mesas...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Mesas">
      <div className="space-y-6" data-testid="tables-page">
        {/* Legend */}
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-green-500/20 border border-green-500" />
            <span className="text-sm">Disponível</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-red-500/20 border border-red-500" />
            <span className="text-sm">Ocupada</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-amber-500/20 border border-amber-500" />
            <span className="text-sm">Reservada</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-blue-500/20 border border-blue-500" />
            <span className="text-sm">Limpeza</span>
          </div>
        </div>

        {/* Tables Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {tables.map((table) => {
            const order = getTableOrder(table.id);
            const statusClass = getTableStatusColor(table.status);
            
            return (
              <Card
                key={table.id}
                className={cn(
                  'cursor-pointer transition-all duration-300 hover:scale-105 hover:shadow-lg border-2',
                  statusClass
                )}
                onClick={() => handleTableClick(table)}
                data-testid={`table-${table.number}`}
              >
                <CardContent className="p-4">
                  <div className="text-center">
                    <h3 className="font-heading text-2xl mb-1">
                      Mesa {table.number}
                    </h3>
                    <div className="flex items-center justify-center gap-1 text-sm mb-2">
                      <Users className="h-4 w-4" />
                      <span>{table.capacity} lugares</span>
                    </div>
                    <Badge variant="outline" className={cn('mb-2', statusClass)}>
                      {getTableStatusLabel(table.status)}
                    </Badge>
                    
                    {order && (
                      <div className="mt-2 pt-2 border-t border-current/20">
                        <div className="flex items-center justify-center gap-1 text-xs mb-1">
                          <Clock className="h-3 w-3" />
                          <span>{order.items?.length || 0} itens</span>
                        </div>
                        <p className="font-bold text-sm">
                          {formatCurrency(order.total || 0)}
                        </p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {tables.length === 0 && (
          <div className="text-center py-12">
            <p className="text-muted-foreground">Nenhuma mesa cadastrada</p>
          </div>
        )}
      </div>
    </Layout>
  );
}
