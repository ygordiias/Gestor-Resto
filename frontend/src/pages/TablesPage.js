import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { tablesAPI, ordersAPI } from '../lib/api';
import { cn, getTableStatusColor, getTableStatusLabel, formatCurrency } from '../lib/utils';
import { useAuth } from '../contexts/AuthContext';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import { Users, Clock, Sparkles, CalendarX, CheckCircle } from 'lucide-react';

export default function TablesPage() {
  const [tables, setTables] = useState([]);
  const [orders, setOrders] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedTable, setSelectedTable] = useState(null);
  const [showActionDialog, setShowActionDialog] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const isMountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const [tablesRes, ordersRes] = await Promise.all([
        tablesAPI.getAll(),
        ordersAPI.getOpen(),
      ]);

      if (isMountedRef.current) {
        setTables(tablesRes.data);
        const ordersMap = {};
        ordersRes.data.forEach(order => {
          ordersMap[order.table_id] = order;
        });
        setOrders(ordersMap);
        setLoading(false);
      }
    } catch (error) {
      if (isMountedRef.current) {
        toast.error('Erro ao carregar mesas');
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    
    const handleTablesUpdate = (updatedTables) => {
      if (isMountedRef.current) {
        setTables(updatedTables);
      }
    };

    fetchData();
    socketService.connect();
    socketService.on('tables_updated', handleTablesUpdate);

    return () => {
      isMountedRef.current = false;
      socketService.off('tables_updated');
    };
  }, [fetchData]);

  const handleTableClick = (table) => {
    if (table.status === 'reserved') {
      setSelectedTable(table);
      setShowActionDialog(true);
      return;
    }
    if (table.status === 'cleaning') {
      setSelectedTable(table);
      setShowActionDialog(true);
      return;
    }
    // Mesa disponível ou ocupada: ir para pedido
    navigate(`/order/${table.id}`, { state: { table } });
  };

  const handleTableAction = async (action) => {
    if (!selectedTable) return;
    
    try {
      let newStatus = selectedTable.status;
      
      switch (action) {
        case 'available':
          newStatus = 'available';
          break;
        case 'reserve':
          newStatus = 'reserved';
          break;
        case 'cleaning':
          newStatus = 'cleaning';
          break;
        case 'cancel_reserve':
          newStatus = 'available';
          break;
        default:
          break;
      }
      
      await tablesAPI.update(selectedTable.id, { status: newStatus });
      toast.success(`Mesa ${selectedTable.number} atualizada para: ${getTableStatusLabel(newStatus)}`);
      setShowActionDialog(false);
      setSelectedTable(null);
      fetchData();
    } catch (error) {
      toast.error('Erro ao atualizar mesa');
    }
  };

  const requestCleaning = async (table) => {
    try {
      await tablesAPI.update(table.id, { status: 'cleaning' });
      toast.success(`Limpeza solicitada para Mesa ${table.number}`);
      fetchData();
    } catch (error) {
      toast.error('Erro ao solicitar limpeza');
    }
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
      <div className="space-y-4 sm:space-y-6" data-testid="tables-page">
        {/* Legend - Responsivo */}
        <div className="flex flex-wrap gap-2 sm:gap-4 text-xs sm:text-sm">
          <div className="flex items-center gap-1 sm:gap-2">
            <div className="w-3 h-3 sm:w-4 sm:h-4 rounded bg-green-500/20 border border-green-500" />
            <span>Disponível</span>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            <div className="w-3 h-3 sm:w-4 sm:h-4 rounded bg-red-500/20 border border-red-500" />
            <span>Ocupada</span>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            <div className="w-3 h-3 sm:w-4 sm:h-4 rounded bg-amber-500/20 border border-amber-500" />
            <span>Reservada</span>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            <div className="w-3 h-3 sm:w-4 sm:h-4 rounded bg-blue-500/20 border border-blue-500" />
            <span>Limpeza</span>
          </div>
        </div>

        {/* Tables Grid - Responsivo */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2 sm:gap-4">
          {tables.map((table) => {
            const order = getTableOrder(table.id);
            const statusClass = getTableStatusColor(table.status);
            
            return (
              <Card
                key={table.id}
                className={cn(
                  'cursor-pointer transition-all duration-300 hover:scale-105 hover:shadow-lg border-2 touch-target',
                  statusClass
                )}
                onClick={() => handleTableClick(table)}
                data-testid={`table-${table.number}`}
              >
                <CardContent className="p-2 sm:p-4">
                  <div className="text-center">
                    <h3 className="font-heading text-lg sm:text-2xl mb-1">
                      Mesa {table.number}
                    </h3>
                    <div className="flex items-center justify-center gap-1 text-xs sm:text-sm mb-1 sm:mb-2">
                      <Users className="h-3 w-3 sm:h-4 sm:w-4" />
                      <span>{table.capacity}</span>
                    </div>
                    <Badge variant="outline" className={cn('text-xs sm:text-sm mb-1 sm:mb-2', statusClass)}>
                      {getTableStatusLabel(table.status)}
                    </Badge>
                    
                    {order && (
                      <div className="mt-1 sm:mt-2 pt-1 sm:pt-2 border-t border-current/20">
                        <div className="flex items-center justify-center gap-1 text-xs mb-1">
                          <Clock className="h-3 w-3" />
                          <span>{order.items?.length || 0} itens</span>
                        </div>
                        <p className="font-bold text-xs sm:text-sm">
                          {formatCurrency(order.total || 0)}
                        </p>
                      </div>
                    )}

                    {/* Botão de solicitar limpeza para mesas disponíveis */}
                    {table.status === 'available' && (user?.role === 'waiter' || user?.role === 'admin') && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-2 text-xs w-full"
                        onClick={(e) => {
                          e.stopPropagation();
                          requestCleaning(table);
                        }}
                      >
                        <Sparkles className="h-3 w-3 mr-1" />
                        Reservar
                      </Button>
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

        {/* Dialog de Ações da Mesa */}
        <Dialog open={showActionDialog} onOpenChange={setShowActionDialog}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle className="font-heading">
                Mesa {selectedTable?.number}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-4">
              <p className="text-sm text-muted-foreground text-center">
                Status atual: <strong>{getTableStatusLabel(selectedTable?.status)}</strong>
              </p>
              
              {selectedTable?.status === 'cleaning' && (
                <Button
                  className="w-full"
                  onClick={() => handleTableAction('available')}
                  data-testid="mark-available-btn"
                >
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Marcar como Disponível
                </Button>
              )}
              
              {selectedTable?.status === 'reserved' && (
                <>
                  <Button
                    className="w-full"
                    onClick={() => {
                      setShowActionDialog(false);
                      navigate(`/order/${selectedTable.id}`, { state: { table: selectedTable } });
                    }}
                    data-testid="open-order-btn"
                  >
                    Abrir Comanda
                  </Button>
                  <Button
                    variant="outline"
                    className="w-full text-red-600"
                    onClick={() => handleTableAction('cancel_reserve')}
                    data-testid="cancel-reserve-btn"
                  >
                    <CalendarX className="h-4 w-4 mr-2" />
                    Cancelar Reserva
                  </Button>
                </>
              )}
              
              {selectedTable?.status === 'available' && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => handleTableAction('reserve')}
                  data-testid="reserve-btn"
                >
                  Reservar Mesa
                </Button>
              )}
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setShowActionDialog(false)}>
                Fechar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
