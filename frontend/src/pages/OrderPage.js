import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { ScrollArea } from '../components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { productsAPI, categoriesAPI, ordersAPI, tablesAPI } from '../lib/api';
import { cn, formatCurrency, getStatusLabel, getStatusColor } from '../lib/utils';
import { useAuth } from '../contexts/AuthContext';
import socketService, { playNotificationSound } from '../lib/socket';
import { toast } from 'sonner';
import { 
  Plus, 
  Minus, 
  ShoppingCart, 
  Trash2, 
  Send, 
  ArrowLeft,
  Search,
  UtensilsCrossed,
  Wine,
  Bell,
  Sparkles
} from 'lucide-react';

export default function OrderPage() {
  const { tableId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isMountedRef = useRef(true);
  
  const [table, setTable] = useState(location.state?.table || null);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [currentOrder, setCurrentOrder] = useState(null);
  const [cart, setCart] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const [productsRes, categoriesRes, tableRes] = await Promise.all([
        productsAPI.getAll(),
        categoriesAPI.getAll(),
        !table ? tablesAPI.getAll() : Promise.resolve({ data: [table] }),
      ]);

      if (isMountedRef.current) {
        setProducts(productsRes.data.filter(p => p.is_available));
        setCategories(categoriesRes.data);
        
        if (!table) {
          const foundTable = tableRes.data.find(t => t.id === tableId);
          setTable(foundTable);
        }

        // Get current order if exists
        try {
          const orderRes = await ordersAPI.getByTable(tableId);
          if (orderRes.data && isMountedRef.current) {
            setCurrentOrder(orderRes.data);
          }
        } catch (e) {
          // No current order
        }
        
        setLoading(false);
      }
    } catch (error) {
      if (isMountedRef.current) {
        toast.error('Erro ao carregar dados');
        setLoading(false);
      }
    }
  }, [tableId, table]);

  useEffect(() => {
    isMountedRef.current = true;
    
    // Handler para notificação de item pronto
    const handleWaiterNotification = (data) => {
      if (!isMountedRef.current) return;
      if (data.tableNumber === table?.number) {
        playNotificationSound();
        toast.success(`${data.productName} está PRONTO!`, {
          icon: <Bell className="h-4 w-4" />,
          duration: 5000,
        });
      }
    };

    fetchData();
    socketService.connect();
    socketService.on('waiter_notification', handleWaiterNotification);
    socketService.on('order_updated', (order) => {
      if (isMountedRef.current && order.table_id === tableId) {
        setCurrentOrder(order);
      }
    });

    return () => {
      isMountedRef.current = false;
      socketService.off('waiter_notification');
      socketService.off('order_updated');
    };
  }, [fetchData, tableId, table?.number]);

  const addToCart = useCallback((product) => {
    setCart(prev => {
      const existing = prev.find(item => item.product_id === product.id);
      if (existing) {
        return prev.map(item =>
          item.product_id === product.id
            ? { ...item, quantity: item.quantity + 1 }
            : item
        );
      }
      return [...prev, {
        id: `cart-${product.id}-${Date.now()}`,
        product_id: product.id,
        product_name: product.name,
        quantity: 1,
        unit_price: product.price,
        type: product.type,
        notes: '',
      }];
    });
    toast.success(`${product.name} adicionado`);
  }, []);

  const updateCartQuantity = useCallback((productId, delta) => {
    setCart(prev => {
      return prev.map(item => {
        if (item.product_id === productId) {
          const newQty = item.quantity + delta;
          if (newQty <= 0) return null;
          return { ...item, quantity: newQty };
        }
        return item;
      }).filter(Boolean);
    });
  }, []);

  const updateCartNotes = useCallback((productId, notes) => {
    setCart(prev =>
      prev.map(item =>
        item.product_id === productId ? { ...item, notes } : item
      )
    );
  }, []);

  const removeFromCart = useCallback((productId) => {
    setCart(prev => prev.filter(item => item.product_id !== productId));
  }, []);

  const handleSendOrder = async () => {
    if (cart.length === 0) {
      toast.error('Adicione itens ao pedido');
      return;
    }

    // Verifica se mesa está reservada
    if (table?.status === 'reserved') {
      // Mesa reservada pode abrir comanda
    }

    setSending(true);
    try {
      const orderData = {
        table_id: tableId,
        table_number: table.number,
        items: cart.map(item => ({
          product_id: item.product_id,
          product_name: item.product_name,
          quantity: item.quantity,
          unit_price: item.unit_price,
          type: item.type,
          notes: item.notes,
        })),
        waiter_id: user.id,
        waiter_name: user.name,
      };

      await ordersAPI.create(orderData);
      toast.success('Pedido enviado com sucesso!');
      setCart([]);
      fetchData();
    } catch (error) {
      toast.error('Erro ao enviar pedido');
    } finally {
      setSending(false);
    }
  };

  const handleRequestCleaning = async () => {
    try {
      await tablesAPI.update(tableId, { status: 'cleaning' });
      toast.success('Limpeza solicitada!');
      navigate('/tables');
    } catch (error) {
      toast.error('Erro ao solicitar limpeza');
    }
  };

  const filteredProducts = products.filter(product => {
    const matchesSearch = product.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || product.category_id === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const foodProducts = filteredProducts.filter(p => p.type === 'food');
  const drinkProducts = filteredProducts.filter(p => p.type === 'drink');

  const cartTotal = cart.reduce((sum, item) => sum + item.unit_price * item.quantity, 0);

  if (loading) {
    return (
      <Layout title={`Mesa ${table?.number || ''}`}>
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title={`Mesa ${table?.number || ''}`}>
      <div className="space-y-3 sm:space-y-4" data-testid="order-page">
        {/* Header com botões */}
        <div className="flex flex-wrap gap-2 items-center justify-between">
          <Button
            variant="ghost"
            onClick={() => navigate('/tables')}
            className="gap-2"
            data-testid="back-btn"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">Voltar</span>
          </Button>
          
          {/* Botão de solicitar limpeza (para tablet do cliente) */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleRequestCleaning}
            className="gap-2"
            data-testid="request-cleaning-btn"
          >
            <Sparkles className="h-4 w-4" />
            <span className="hidden sm:inline">Solicitar Limpeza</span>
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
          {/* Produtos */}
          <div className="lg:col-span-2 space-y-3 sm:space-y-4">
            {/* Busca */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
                data-testid="search-input"
              />
            </div>

            {/* Categorias */}
            <ScrollArea className="w-full">
              <div className="flex gap-2 pb-2">
                <Button
                  variant={selectedCategory === 'all' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedCategory('all')}
                  className="shrink-0"
                >
                  Todos
                </Button>
                {categories.map(cat => (
                  <Button
                    key={cat.id}
                    variant={selectedCategory === cat.id ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setSelectedCategory(cat.id)}
                    className="shrink-0"
                  >
                    {cat.icon} {cat.name}
                  </Button>
                ))}
              </div>
            </ScrollArea>

            {/* Produtos por tipo */}
            <div className="space-y-4 sm:space-y-6">
              {/* Comidas */}
              {foodProducts.length > 0 && (
                <div>
                  <h3 className="font-heading text-base sm:text-lg flex items-center gap-2 mb-3 sm:mb-4">
                    <UtensilsCrossed className="h-4 w-4 sm:h-5 sm:w-5 text-primary" />
                    Comidas
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-4">
                    {foodProducts.map(product => (
                      <Card 
                        key={product.id} 
                        className="card-hover cursor-pointer"
                        onClick={() => addToCart(product)}
                        data-testid={`product-${product.id}`}
                      >
                        <CardContent className="p-3 sm:p-4 flex gap-3 sm:gap-4">
                          {product.image_url && (
                            <img
                              src={product.image_url}
                              alt={product.name}
                              className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-lg"
                            />
                          )}
                          <div className="flex-1 min-w-0">
                            <h4 className="font-medium text-sm sm:text-base truncate">{product.name}</h4>
                            <p className="text-xs sm:text-sm text-muted-foreground line-clamp-1">
                              {product.description}
                            </p>
                            <p className="text-base sm:text-lg font-bold text-primary mt-1">
                              {formatCurrency(product.price)}
                            </p>
                          </div>
                          <Button size="icon" variant="outline" className="shrink-0 h-8 w-8 sm:h-10 sm:w-10">
                            <Plus className="h-4 w-4" />
                          </Button>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* Bebidas */}
              {drinkProducts.length > 0 && (
                <div>
                  <h3 className="font-heading text-base sm:text-lg flex items-center gap-2 mb-3 sm:mb-4">
                    <Wine className="h-4 w-4 sm:h-5 sm:w-5 text-primary" />
                    Bebidas
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-4">
                    {drinkProducts.map(product => (
                      <Card 
                        key={product.id} 
                        className="card-hover cursor-pointer"
                        onClick={() => addToCart(product)}
                        data-testid={`product-${product.id}`}
                      >
                        <CardContent className="p-3 sm:p-4 flex gap-3 sm:gap-4">
                          {product.image_url && (
                            <img
                              src={product.image_url}
                              alt={product.name}
                              className="w-16 h-16 sm:w-20 sm:h-20 object-cover rounded-lg"
                            />
                          )}
                          <div className="flex-1 min-w-0">
                            <h4 className="font-medium text-sm sm:text-base truncate">{product.name}</h4>
                            <p className="text-xs sm:text-sm text-muted-foreground line-clamp-1">
                              {product.description}
                            </p>
                            <p className="text-base sm:text-lg font-bold text-primary mt-1">
                              {formatCurrency(product.price)}
                            </p>
                          </div>
                          <Button size="icon" variant="outline" className="shrink-0 h-8 w-8 sm:h-10 sm:w-10">
                            <Plus className="h-4 w-4" />
                          </Button>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Carrinho */}
          <div className="lg:col-span-1">
            <Card className="sticky top-20">
              <CardHeader className="pb-2">
                <CardTitle className="font-heading flex items-center gap-2 text-base sm:text-lg">
                  <ShoppingCart className="h-4 w-4 sm:h-5 sm:w-5" />
                  Pedido
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 sm:space-y-4">
                {/* Itens já pedidos */}
                {currentOrder && currentOrder.items.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs sm:text-sm font-medium text-muted-foreground">
                      Itens já pedidos
                    </h4>
                    <ScrollArea className="h-24 sm:h-32 rounded border p-2">
                      {currentOrder.items.map((item) => (
                        <div key={item.id} className="flex justify-between text-xs sm:text-sm py-1">
                          <span className="truncate">{item.quantity}x {item.product_name}</span>
                          <Badge className={cn('text-xs ml-2', getStatusColor(item.status))} variant="outline">
                            {getStatusLabel(item.status)}
                          </Badge>
                        </div>
                      ))}
                    </ScrollArea>
                    <div className="text-right text-xs sm:text-sm">
                      <span className="text-muted-foreground">Total: </span>
                      <span className="font-bold">{formatCurrency(currentOrder.total)}</span>
                    </div>
                  </div>
                )}

                {/* Novos itens */}
                <div className="space-y-2">
                  <h4 className="text-xs sm:text-sm font-medium">Novos itens</h4>
                  {cart.length === 0 ? (
                    <p className="text-xs sm:text-sm text-muted-foreground text-center py-4">
                      Selecione itens do cardápio
                    </p>
                  ) : (
                    <ScrollArea className="h-48 sm:h-64">
                      <div className="space-y-2 sm:space-y-3">
                        {cart.map((item) => (
                          <div key={item.id} className="border rounded-lg p-2 sm:p-3 space-y-2">
                            <div className="flex justify-between items-start">
                              <div className="min-w-0">
                                <p className="font-medium text-xs sm:text-sm truncate">{item.product_name}</p>
                                <p className="text-primary font-bold text-sm">
                                  {formatCurrency(item.unit_price * item.quantity)}
                                </p>
                              </div>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 sm:h-8 sm:w-8 text-destructive shrink-0"
                                onClick={() => removeFromCart(item.product_id)}
                              >
                                <Trash2 className="h-3 w-3 sm:h-4 sm:w-4" />
                              </Button>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 sm:h-8 sm:w-8"
                                onClick={() => updateCartQuantity(item.product_id, -1)}
                              >
                                <Minus className="h-3 w-3 sm:h-4 sm:w-4" />
                              </Button>
                              <span className="w-6 sm:w-8 text-center font-bold text-sm">{item.quantity}</span>
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 sm:h-8 sm:w-8"
                                onClick={() => updateCartQuantity(item.product_id, 1)}
                              >
                                <Plus className="h-3 w-3 sm:h-4 sm:w-4" />
                              </Button>
                            </div>
                            <Textarea
                              placeholder="Observações..."
                              value={item.notes}
                              onChange={(e) => updateCartNotes(item.product_id, e.target.value)}
                              className="h-12 sm:h-16 text-xs sm:text-sm"
                            />
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  )}
                </div>

                {/* Total e botão enviar */}
                {cart.length > 0 && (
                  <div className="pt-3 sm:pt-4 border-t space-y-3 sm:space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-sm">Total:</span>
                      <span className="text-lg sm:text-xl font-heading font-bold text-primary">
                        {formatCurrency(cartTotal)}
                      </span>
                    </div>
                    <Button
                      className="w-full font-heading uppercase tracking-widest text-sm"
                      onClick={handleSendOrder}
                      disabled={sending}
                      data-testid="send-order-btn"
                    >
                      {sending ? (
                        'Enviando...'
                      ) : (
                        <>
                          <Send className="h-4 w-4 mr-2" />
                          Enviar Pedido
                        </>
                      )}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </Layout>
  );
}
