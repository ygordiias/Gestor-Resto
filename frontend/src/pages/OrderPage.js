import React, { useState, useEffect } from 'react';
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
  Wine
} from 'lucide-react';

export default function OrderPage() {
  const { tableId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  
  const [table, setTable] = useState(location.state?.table || null);
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [currentOrder, setCurrentOrder] = useState(null);
  const [cart, setCart] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    fetchData();
  }, [tableId]);

  const fetchData = async () => {
    try {
      const [productsRes, categoriesRes, tableRes] = await Promise.all([
        productsAPI.getAll(),
        categoriesAPI.getAll(),
        !table ? tablesAPI.getAll() : Promise.resolve({ data: [table] }),
      ]);

      setProducts(productsRes.data.filter(p => p.is_available));
      setCategories(categoriesRes.data);
      
      if (!table) {
        const foundTable = tableRes.data.find(t => t.id === tableId);
        setTable(foundTable);
      }

      // Get current order if exists
      try {
        const orderRes = await ordersAPI.getByTable(tableId);
        if (orderRes.data) {
          setCurrentOrder(orderRes.data);
        }
      } catch (e) {
        // No current order
      }
    } catch (error) {
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  const addToCart = (product) => {
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
        product_id: product.id,
        product_name: product.name,
        quantity: 1,
        unit_price: product.price,
        type: product.type,
        notes: '',
      }];
    });
    toast.success(`${product.name} adicionado`);
  };

  const updateCartQuantity = (productId, delta) => {
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
  };

  const updateCartNotes = (productId, notes) => {
    setCart(prev =>
      prev.map(item =>
        item.product_id === productId ? { ...item, notes } : item
      )
    );
  };

  const removeFromCart = (productId) => {
    setCart(prev => prev.filter(item => item.product_id !== productId));
  };

  const handleSendOrder = async () => {
    if (cart.length === 0) {
      toast.error('Adicione itens ao pedido');
      return;
    }

    setSending(true);
    try {
      await ordersAPI.create({
        table_id: tableId,
        table_number: table.number,
        items: cart,
        waiter_id: user.id,
        waiter_name: user.name,
      });

      toast.success('Pedido enviado com sucesso!');
      setCart([]);
      fetchData();
    } catch (error) {
      toast.error('Erro ao enviar pedido');
    } finally {
      setSending(false);
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
      <div className="space-y-4" data-testid="order-page">
        {/* Back Button */}
        <Button
          variant="ghost"
          onClick={() => navigate('/tables')}
          className="gap-2"
          data-testid="back-btn"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar para Mesas
        </Button>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Products Section */}
          <div className="lg:col-span-2 space-y-4">
            {/* Search and Filter */}
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Buscar produto..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                  data-testid="search-input"
                />
              </div>
            </div>

            {/* Category Tabs */}
            <Tabs defaultValue="all" onValueChange={setSelectedCategory}>
              <TabsList className="w-full flex-wrap h-auto gap-2 bg-transparent p-0">
                <TabsTrigger value="all" className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  Todos
                </TabsTrigger>
                {categories.map(cat => (
                  <TabsTrigger 
                    key={cat.id} 
                    value={cat.id}
                    className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                  >
                    {cat.icon} {cat.name}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {/* Products by Type */}
            <div className="space-y-6">
              {/* Food */}
              {foodProducts.length > 0 && (
                <div>
                  <h3 className="font-heading text-lg flex items-center gap-2 mb-4">
                    <UtensilsCrossed className="h-5 w-5 text-primary" />
                    Comidas
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {foodProducts.map(product => (
                      <Card 
                        key={product.id} 
                        className="card-hover cursor-pointer"
                        onClick={() => addToCart(product)}
                        data-testid={`product-${product.id}`}
                      >
                        <CardContent className="p-4 flex gap-4">
                          {product.image_url && (
                            <img
                              src={product.image_url}
                              alt={product.name}
                              className="w-20 h-20 object-cover rounded-lg sepia-[.15]"
                            />
                          )}
                          <div className="flex-1">
                            <h4 className="font-medium">{product.name}</h4>
                            <p className="text-sm text-muted-foreground line-clamp-2">
                              {product.description}
                            </p>
                            <p className="text-lg font-bold text-primary mt-1">
                              {formatCurrency(product.price)}
                            </p>
                          </div>
                          <Button size="icon" variant="outline" className="shrink-0">
                            <Plus className="h-4 w-4" />
                          </Button>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* Drinks */}
              {drinkProducts.length > 0 && (
                <div>
                  <h3 className="font-heading text-lg flex items-center gap-2 mb-4">
                    <Wine className="h-5 w-5 text-primary" />
                    Bebidas
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {drinkProducts.map(product => (
                      <Card 
                        key={product.id} 
                        className="card-hover cursor-pointer"
                        onClick={() => addToCart(product)}
                        data-testid={`product-${product.id}`}
                      >
                        <CardContent className="p-4 flex gap-4">
                          {product.image_url && (
                            <img
                              src={product.image_url}
                              alt={product.name}
                              className="w-20 h-20 object-cover rounded-lg sepia-[.15]"
                            />
                          )}
                          <div className="flex-1">
                            <h4 className="font-medium">{product.name}</h4>
                            <p className="text-sm text-muted-foreground line-clamp-2">
                              {product.description}
                            </p>
                            <p className="text-lg font-bold text-primary mt-1">
                              {formatCurrency(product.price)}
                            </p>
                          </div>
                          <Button size="icon" variant="outline" className="shrink-0">
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

          {/* Cart Section */}
          <div className="lg:col-span-1">
            <Card className="sticky top-24">
              <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                  <ShoppingCart className="h-5 w-5" />
                  Pedido
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Current Order Items */}
                {currentOrder && currentOrder.items.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-medium text-muted-foreground">
                      Itens já pedidos
                    </h4>
                    <ScrollArea className="h-32 rounded border p-2">
                      {currentOrder.items.map((item, idx) => (
                        <div key={idx} className="flex justify-between text-sm py-1">
                          <span>{item.quantity}x {item.product_name}</span>
                          <Badge className={getStatusColor(item.status)} variant="outline">
                            {getStatusLabel(item.status)}
                          </Badge>
                        </div>
                      ))}
                    </ScrollArea>
                    <div className="text-right text-sm">
                      <span className="text-muted-foreground">Total atual: </span>
                      <span className="font-bold">{formatCurrency(currentOrder.total)}</span>
                    </div>
                  </div>
                )}

                {/* New Cart Items */}
                <div className="space-y-2">
                  <h4 className="text-sm font-medium">Novos itens</h4>
                  {cart.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      Selecione itens do cardápio
                    </p>
                  ) : (
                    <ScrollArea className="h-64">
                      <div className="space-y-3">
                        {cart.map((item) => (
                          <div key={item.product_id} className="border rounded-lg p-3 space-y-2">
                            <div className="flex justify-between items-start">
                              <div>
                                <p className="font-medium text-sm">{item.product_name}</p>
                                <p className="text-primary font-bold">
                                  {formatCurrency(item.unit_price * item.quantity)}
                                </p>
                              </div>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-destructive"
                                onClick={() => removeFromCart(item.product_id)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                            <div className="flex items-center gap-2">
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => updateCartQuantity(item.product_id, -1)}
                              >
                                <Minus className="h-4 w-4" />
                              </Button>
                              <span className="w-8 text-center font-bold">{item.quantity}</span>
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => updateCartQuantity(item.product_id, 1)}
                              >
                                <Plus className="h-4 w-4" />
                              </Button>
                            </div>
                            <Textarea
                              placeholder="Observações..."
                              value={item.notes}
                              onChange={(e) => updateCartNotes(item.product_id, e.target.value)}
                              className="h-16 text-sm"
                            />
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  )}
                </div>

                {/* Cart Total and Send Button */}
                {cart.length > 0 && (
                  <div className="pt-4 border-t space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="font-medium">Total do pedido:</span>
                      <span className="text-xl font-heading font-bold text-primary">
                        {formatCurrency(cartTotal)}
                      </span>
                    </div>
                    <Button
                      className="w-full font-heading uppercase tracking-widest"
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
