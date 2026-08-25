import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { tablesAPI, ordersAPI } from '../lib/api';
import { cn, getTableStatusColor, getTableStatusLabel, formatCurrency } from '../lib/utils';
import { useAuth } from '../contexts/AuthContext';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import { Users, Clock, Sparkles, CalendarX, CheckCircle, Plus, Trash2 } from 'lucide-react';

export default function TablesPage() {
  const [tables, setTables] = useState([]);
  const [orders, setOrders] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedTable, setSelectedTable] = useState(null);
  const [showActionDialog, setShowActionDialog] = useState(false);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newTable, setNewTable] = useState({ number: '', seats: '4', table_type: 'regular', note: '' });
  const navigate = useNavigate();
  const { user } = useAuth();
  const isMountedRef = useRef(true);

  const canManage = user?.role === 'admin' || user?.role === 'superadmin';

  const handleCreateTable = async () => {
    const num = parseInt(newTable.number);
    const seats = parseInt(newTable.seats);
    if (!num || num <= 0) { toast.error('Número da mesa inválido'); return; }
    if (!seats || seats <= 0) { toast.error('Número de lugares inválido'); return; }
    setSaving(true);
    try {
      await tablesAPI.create({ number: num, capacity: seats, table_type: newTable.table_type || 'regular', note: newTable.note?.trim() || null });
      toast.success(`Mesa ${num} criada`);
      setShowAddDialog(false);
      setNewTable({ number: '', seats: '4', table_type: 'regular', note: '' });
      fetchData();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao criar mesa');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTable = async (table, e) => {
    e.stopPropagation();
    if (!window.confirm(`Excluir a Mesa ${table.number}? Essa ação não pode ser desfeita.`)) return;
    try {
      await tablesAPI.delete(table.id);
      toast.success(`Mesa ${table.number} excluída`);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao excluir mesa');
    }
  };

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
        {/* Toolbar + Legend */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
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
          {canManage && (
            <Button
              onClick={() => setShowAddDialog(true)}
              data-testid="new-table-btn"
              size="sm"
            >
              <Plus className="h-4 w-4 mr-2" /> Nova Mesa
            </Button>
          )}
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
                  'relative cursor-pointer transition-all duration-300 hover:scale-105 hover:shadow-lg border-2 touch-target',
                  statusClass
                )}
                onClick={() => handleTableClick(table)}
                data-testid={`table-${table.number}`}
              >
                {canManage && table.status === 'available' && (
                  <button
                    onClick={(e) => handleDeleteTable(table, e)}
                    className="absolute -top-2 -right-2 z-10 p-1 rounded-full bg-destructive text-destructive-foreground hover:opacity-90 shadow-md"
                    title={`Excluir Mesa ${table.number}`}
                    data-testid={`delete-table-${table.number}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
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
                    {table.table_type && table.table_type !== 'regular' && (
                      <Badge variant="outline" className="text-[10px] mb-1 sm:mb-2 ml-1 border-purple-500 text-purple-700 bg-purple-500/10" title={table.note || ''}>
                        🎤 {table.table_type === 'artist' ? 'Artista' : table.table_type === 'singer' ? 'Cantor' : table.table_type === 'cover' ? 'Cover' : 'Evento'}
                      </Badge>
                    )}
                    
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
                    {table.status === 'available' && (user?.role === 'waiter' || user?.role === 'admin' || user?.role === 'superadmin') && (
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

        {/* Dialog Nova Mesa */}
        <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
          <DialogContent className="max-w-sm" data-testid="new-table-dialog">
            <DialogHeader>
              <DialogTitle className="font-heading flex items-center gap-2">
                <Plus className="h-5 w-5 text-primary" /> Nova Mesa
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>Número da mesa *</Label>
                <Input
                  type="number"
                  min="1"
                  placeholder="Ex: 15"
                  value={newTable.number}
                  onChange={(e) => setNewTable({ ...newTable, number: e.target.value })}
                  data-testid="new-table-number-input"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label>Lugares *</Label>
                <Input
                  type="number"
                  min="1"
                  value={newTable.seats}
                  onChange={(e) => setNewTable({ ...newTable, seats: e.target.value })}
                  data-testid="new-table-seats-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Tipo</Label>
                <select
                  value={newTable.table_type}
                  onChange={(e) => setNewTable({ ...newTable, table_type: e.target.value })}
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                  data-testid="new-table-type"
                >
                  <option value="regular">Normal</option>
                  <option value="artist">Artista</option>
                  <option value="singer">Cantor</option>
                  <option value="cover">Cover</option>
                  <option value="event">Evento</option>
                </select>
              </div>
              {newTable.table_type !== 'regular' && (
                <div className="space-y-2">
                  <Label>Nome do artista/evento (opcional)</Label>
                  <Input
                    value={newTable.note}
                    onChange={(e) => setNewTable({ ...newTable, note: e.target.value })}
                    placeholder="Ex: Banda XYZ, Cover do Roupa Nova..."
                    data-testid="new-table-note"
                  />
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowAddDialog(false)} disabled={saving}>
                Cancelar
              </Button>
              <Button onClick={handleCreateTable} disabled={saving} data-testid="save-new-table-btn">
                {saving ? 'Salvando...' : 'Criar Mesa'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

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
