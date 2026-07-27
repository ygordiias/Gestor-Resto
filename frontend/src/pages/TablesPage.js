import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { tablesAPI, ordersAPI } from '../lib/api';
import {
  cn,
  getTableStatusColor,
  getTableStatusLabel,
  formatCurrency
} from '../lib/utils';
import { useAuth } from '../contexts/AuthContext';
import socketService from '../lib/socket';
import { toast } from 'sonner';
import {
  Users,
  Clock,
  Sparkles,
  CalendarX,
  CheckCircle,
  Plus,
  Trash2
} from 'lucide-react';

export default function TablesPage() {
  const [tables, setTables] = useState([]);
  const [orders, setOrders] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedTable, setSelectedTable] = useState(null);
  const [showActionDialog, setShowActionDialog] = useState(false);

  // Cadastro de mesa
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [newTableNumber, setNewTableNumber] = useState('');
  const [newTableCapacity, setNewTableCapacity] = useState(4);
  const [addingTable, setAddingTable] = useState(false);

  const navigate = useNavigate();
  const { user } = useAuth();
  const isMountedRef = useRef(true);

  const canManage =
    user?.role === 'admin' ||
    user?.role === 'superadmin';

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

        ordersRes.data.forEach((order) => {
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

  // ==================== CADASTRAR MESA ====================

  const handleAddTable = async () => {
    const number = parseInt(newTableNumber, 10);
    const capacity = parseInt(newTableCapacity, 10);

    if (!number || number <= 0) {
      toast.error('Informe um número de mesa válido');
      return;
    }

    if (!capacity || capacity <= 0) {
      toast.error('Informe uma capacidade válida');
      return;
    }

    setAddingTable(true);

    try {
      await tablesAPI.create({
        number,
        capacity,
      });

      toast.success(`Mesa ${number} adicionada com sucesso`);

      setShowAddDialog(false);
      setNewTableNumber('');
      setNewTableCapacity(4);

      await fetchData();
    } catch (error) {
      toast.error(
        error.response?.data?.detail ||
        'Erro ao adicionar mesa'
      );
    } finally {
      setAddingTable(false);
    }
  };

  // ==================== EXCLUIR MESA ====================

  const handleDeleteTable = async (table, event) => {
    event.stopPropagation();

    if (
      !window.confirm(
        `Excluir a Mesa ${table.number}? Essa ação não pode ser desfeita.`
      )
    ) {
      return;
    }

    try {
      await tablesAPI.delete(table.id);

      toast.success(`Mesa ${table.number} excluída`);

      await fetchData();
    } catch (error) {
      toast.error(
        error.response?.data?.detail ||
        'Erro ao excluir mesa'
      );
    }
  };

  // ==================== CLIQUE NA MESA ====================

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

    // Mesa disponível ou ocupada:
    // mantém a lógica existente de abrir a comanda
    navigate(`/order/${table.id}`, {
      state: { table }
    });
  };

  // ==================== AÇÕES DA MESA ====================

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

      await tablesAPI.update(
        selectedTable.id,
        {
          status: newStatus
        }
      );

      toast.success(
        `Mesa ${selectedTable.number} atualizada para: ${getTableStatusLabel(newStatus)}`
      );

      setShowActionDialog(false);
      setSelectedTable(null);

      await fetchData();
    } catch (error) {
      toast.error(
        error.response?.data?.detail ||
        'Erro ao atualizar mesa'
      );
    }
  };

  // ==================== SOLICITAR LIMPEZA ====================

  const requestCleaning = async (table) => {
    try {
      await tablesAPI.update(
        table.id,
        {
          status: 'cleaning'
        }
      );

      toast.success(
        `Limpeza solicitada para Mesa ${table.number}`
      );

      await fetchData();
    } catch (error) {
      toast.error(
        error.response?.data?.detail ||
        'Erro ao solicitar limpeza'
      );
    }
  };

  const getTableOrder = (tableId) => {
    return orders[tableId];
  };

  // ==================== LOADING ====================

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

  // ==================== TELA PRINCIPAL ====================

  return (
    <Layout title="Mesas">
      <div
        className="space-y-4 sm:space-y-6"
        data-testid="tables-page"
      >

        {/* ==================== CABEÇALHO ==================== */}

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">

          <div>
            <h2 className="text-xl sm:text-2xl font-heading font-bold">
              Mesas
            </h2>

            <p className="text-sm text-muted-foreground">
              Gerencie as mesas do restaurante
            </p>
          </div>

          {canManage && (
            <Button
              onClick={() => setShowAddDialog(true)}
              data-testid="new-table-btn"
              size="sm"
            >
              <Plus className="h-4 w-4 mr-2" />
              Nova Mesa
            </Button>
          )}

        </div>

        {/* ==================== LEGENDA ==================== */}

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

        {/* ==================== GRID DE MESAS ==================== */}

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

                {/* Botão excluir mesa */}
                {canManage &&
                  table.status === 'available' && (
                    <button
                      onClick={(event) =>
                        handleDeleteTable(
                          table,
                          event
                        )
                      }
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
                      <span>
                        {table.capacity}
                      </span>
                    </div>

                    <Badge
                      variant="outline"
                      className={cn(
                        'text-xs sm:text-sm mb-1 sm:mb-2',
                        statusClass
                      )}
                    >
                      {getTableStatusLabel(
                        table.status
                      )}
                    </Badge>

                    {/* Informações da comanda */}
                    {order && (
                      <div className="mt-1 sm:mt-2 pt-1 sm:pt-2 border-t border-current/20">

                        <div className="flex items-center justify-center gap-1 text-xs mb-1">
                          <Clock className="h-3 w-3" />
                          <span>
                            {order.items?.length || 0} itens
                          </span>
                        </div>

                        <p className="font-bold text-xs sm:text-sm">
                          {formatCurrency(
                            order.total || 0
                          )}
                        </p>

                      </div>
                    )}

                    {/* Solicitar limpeza */}
                    {table.status === 'available' &&
                      (
                        user?.role === 'waiter' ||
                        user?.role === 'admin' ||
                        user?.role === 'superadmin'
                      ) && (

                        <Button
                          variant="outline"
                          size="sm"
                          className="mt-2 text-xs w-full"
                          onClick={(event) => {
                            event.stopPropagation();
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

        {/* Nenhuma mesa */}
        {tables.length === 0 && (
          <div className="text-center py-12">
            <p className="text-muted-foreground">
              Nenhuma mesa cadastrada
            </p>
          </div>
        )}

        {/* ==================== DIALOG NOVA MESA ==================== */}

        <Dialog
          open={showAddDialog}
          onOpenChange={setShowAddDialog}
        >
          <DialogContent
            className="max-w-sm"
            data-testid="new-table-dialog"
          >

            <DialogHeader>
              <DialogTitle className="font-heading flex items-center gap-2">
                <Plus className="h-5 w-5 text-primary" />
                Nova Mesa
              </DialogTitle>
            </DialogHeader>

            <div className="space-y-4 py-2">

              <div className="space-y-2">
                <Label htmlFor="new-table-number">
                  Número da mesa *
                </Label>

                <Input
                  id="new-table-number"
                  type="number"
                  min="1"
                  placeholder="Ex: 15"
                  value={newTableNumber}
                  onChange={(event) =>
                    setNewTableNumber(
                      event.target.value
                    )
                  }
                  data-testid="new-table-number-input"
                  autoFocus
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="new-table-capacity">
                  Lugares *
                </Label>

                <Input
                  id="new-table-capacity"
                  type="number"
                  min="1"
                  value={newTableCapacity}
                  onChange={(event) =>
                    setNewTableCapacity(
                      event.target.value
                    )
                  }
                  data-testid="new-table-capacity-input"
                />
              </div>

            </div>

            <DialogFooter>

              <Button
                variant="outline"
                onClick={() =>
                  setShowAddDialog(false)
                }
                disabled={addingTable}
              >
                Cancelar
              </Button>

              <Button
                onClick={handleAddTable}
                disabled={addingTable}
                data-testid="save-new-table-btn"
              >
                {addingTable
                  ? 'Salvando...'
                  : 'Criar Mesa'}
              </Button>

            </DialogFooter>

          </DialogContent>
        </Dialog>

        {/* ==================== DIALOG DE AÇÕES ==================== */}

        <Dialog
          open={showActionDialog}
          onOpenChange={setShowActionDialog}
        >
          <DialogContent className="max-w-sm">

            <DialogHeader>
              <DialogTitle className="font-heading">
                Mesa {selectedTable?.number}
              </DialogTitle>
            </DialogHeader>

            <div className="space-y-3 py-4">

              <p className="text-sm text-muted-foreground text-center">
                Status atual:{' '}
                <strong>
                  {getTableStatusLabel(
                    selectedTable?.status
                  )}
                </strong>
              </p>

              {/* Mesa em limpeza */}
              {selectedTable?.status === 'cleaning' && (
                <Button
                  className="w-full"
                  onClick={() =>
                    handleTableAction('available')
                  }
                  data-testid="mark-available-btn"
                >
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Marcar como Disponível
                </Button>
              )}

              {/* Mesa reservada */}
              {selectedTable?.status === 'reserved' && (
                <>
                  <Button
                    className="w-full"
                    onClick={() => {
                      setShowActionDialog(false);

                      navigate(
                        `/order/${selectedTable.id}`,
                        {
                          state: {
                            table: selectedTable
                          }
                        }
                      );
                    }}
                    data-testid="open-order-btn"
                  >
                    Abrir Comanda
                  </Button>

                  <Button
                    variant="outline"
                    className="w-full text-red-600"
                    onClick={() =>
                      handleTableAction(
                        'cancel_reserve'
                      )
                    }
                    data-testid="cancel-reserve-btn"
                  >
                    <CalendarX className="h-4 w-4 mr-2" />
                    Cancelar Reserva
                  </Button>
                </>
              )}

              {/* Mesa disponível */}
              {selectedTable?.status === 'available' && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    handleTableAction('reserve')
                  }
                  data-testid="reserve-btn"
                >
                  Reservar Mesa
                </Button>
              )}

            </div>

            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() =>
                  setShowActionDialog(false)
                }
              >
                Fechar
              </Button>
            </DialogFooter>

          </DialogContent>
        </Dialog>

      </div>
    </Layout>
  );
}