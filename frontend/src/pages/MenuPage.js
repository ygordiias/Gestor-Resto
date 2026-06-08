import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { productsAPI, categoriesAPI, recipesAPI, cmvAPI, stockAPI } from '../lib/api';
import { cn, formatCurrency } from '../lib/utils';
import { toast } from 'sonner';
import { 
  Plus, 
  Pencil, 
  Trash2, 
  Search,
  UtensilsCrossed,
  Wine,
  Image,
  DollarSign,
  FileText,
  Calculator,
  TrendingUp
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

function RecipeSummary({ recipeItems, stockOptions, salePrice }) {
  let cost = 0;
  for (const item of recipeItems) {
    const stock = stockOptions.find(s => s.id === item.stock_item_id);
    const qty = parseFloat(item.quantity) || 0;
    if (stock && qty > 0) cost += qty * stock.unit_cost;
  }
  const profit = salePrice - cost;
  const margin = salePrice > 0 ? (profit / salePrice) * 100 : 0;
  return (
    <div className="grid grid-cols-4 gap-2 p-3 rounded-lg bg-muted/40 border border-border" data-testid="recipe-summary">
      <div className="text-center">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Venda</p>
        <p className="text-sm font-bold">{formatCurrency(salePrice)}</p>
      </div>
      <div className="text-center">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">CMV</p>
        <p className="text-sm font-bold text-foreground" data-testid="recipe-cost">{formatCurrency(cost)}</p>
      </div>
      <div className="text-center">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Lucro</p>
        <p className={cn("text-sm font-bold", profit >= 0 ? "text-emerald-500" : "text-destructive")} data-testid="recipe-profit">
          {formatCurrency(profit)}
        </p>
      </div>
      <div className="text-center">
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Margem</p>
        <p className={cn("text-sm font-bold",
          margin >= 50 ? "text-emerald-500" : margin >= 20 ? "text-amber-400" : "text-destructive"
        )} data-testid="recipe-margin">
          {margin.toFixed(1)}%
        </p>
      </div>
    </div>
  );
}

export default function MenuPage() {
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(true);
  
  // Product Form State
  const [isProductDialogOpen, setIsProductDialogOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [productForm, setProductForm] = useState({
    name: '',
    description: '',
    category_id: '',
    price: '',
    cost: '',
    image_url: '',
    type: 'food',
    is_available: true,
    preparation_time: 10,
  });

  // Category Form State
  const [isCategoryDialogOpen, setIsCategoryDialogOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null);
  const [categoryForm, setCategoryForm] = useState({
    name: '',
    type: 'food',
    description: '',
    icon: '',
  });

  // Recipe / CMV State
  const [isRecipeDialogOpen, setIsRecipeDialogOpen] = useState(false);
  const [recipeProduct, setRecipeProduct] = useState(null);
  const [recipeId, setRecipeId] = useState(null);
  const [recipeItems, setRecipeItems] = useState([]); // [{stock_item_id, quantity}]
  const [stockOptions, setStockOptions] = useState([]); // [{id, product_id, unit, unit_cost, name}]
  const [recipeLoading, setRecipeLoading] = useState(false);
  const [recipeSaving, setRecipeSaving] = useState(false);
  // Map de CMV por product_id: {cost, profit, margin, has_recipe}
  const [cmvMap, setCmvMap] = useState({});

  useEffect(() => {
    fetchData();
  }, []);

  // Recarrega CMV report quando produtos sao carregados
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!products || products.length === 0) return;
    cmvAPI.getReport()
      .then(res => {
        const m = {};
        res.data.forEach(row => { m[row.product_id] = row; });
        setCmvMap(m);
      })
      .catch(() => {});
  }, [products.length]);

  const fetchData = async () => {
    try {
      const [productsRes, categoriesRes] = await Promise.all([
        productsAPI.getAll(),
        categoriesAPI.getAll(),
      ]);
      setProducts(productsRes.data);
      setCategories(categoriesRes.data);
    } catch (error) {
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  // Product Functions
  const openProductDialog = (product = null) => {
    if (product) {
      setEditingProduct(product);
      setProductForm({
        name: product.name,
        description: product.description || '',
        category_id: product.category_id,
        price: product.price.toString(),
        cost: product.cost.toString(),
        image_url: product.image_url || '',
        type: product.type,
        is_available: product.is_available,
        preparation_time: product.preparation_time,
      });
    } else {
      setEditingProduct(null);
      setProductForm({
        name: '',
        description: '',
        category_id: categories[0]?.id || '',
        price: '',
        cost: '',
        image_url: '',
        type: 'food',
        is_available: true,
        preparation_time: 10,
      });
    }
    setIsProductDialogOpen(true);
  };

  const handleSaveProduct = async () => {
    if (!productForm.name || !productForm.price || !productForm.category_id) {
      toast.error('Preencha os campos obrigatórios');
      return;
    }

    const data = {
      ...productForm,
      price: parseFloat(productForm.price),
      cost: parseFloat(productForm.cost) || 0,
    };

    try {
      if (editingProduct) {
        await productsAPI.update(editingProduct.id, data);
        toast.success('Produto atualizado!');
      } else {
        await productsAPI.create(data);
        toast.success('Produto criado!');
      }
      setIsProductDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error('Erro ao salvar produto');
    }
  };

  const handleDeleteProduct = async (id) => {
    if (!window.confirm('Deseja excluir este produto?')) return;
    
    try {
      await productsAPI.delete(id);
      toast.success('Produto excluído');
      fetchData();
    } catch (error) {
      toast.error('Erro ao excluir produto');
    }
  };

  // Category Functions
  const openCategoryDialog = (category = null) => {
    if (category) {
      setEditingCategory(category);
      setCategoryForm({
        name: category.name,
        type: category.type,
        description: category.description || '',
        icon: category.icon || '',
      });
    } else {
      setEditingCategory(null);
      setCategoryForm({
        name: '',
        type: 'food',
        description: '',
        icon: '',
      });
    }
    setIsCategoryDialogOpen(true);
  };

  const handleSaveCategory = async () => {
    if (!categoryForm.name) {
      toast.error('Informe o nome da categoria');
      return;
    }

    try {
      if (editingCategory) {
        await categoriesAPI.update(editingCategory.id, categoryForm);
        toast.success('Categoria atualizada!');
      } else {
        await categoriesAPI.create(categoryForm);
        toast.success('Categoria criada!');
      }
      setIsCategoryDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error('Erro ao salvar categoria');
    }
  };

  const handleDeleteCategory = async (id) => {
    if (!window.confirm('Deseja excluir esta categoria?')) return;
    
    try {
      await categoriesAPI.delete(id);
      toast.success('Categoria excluída');
      fetchData();
    } catch (error) {
      toast.error('Erro ao excluir categoria');
    }
  };

  // Filter Products
  const filteredProducts = products.filter(product => {
    const matchesSearch = product.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || product.category_id === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const getCategoryName = (categoryId) => {
    const category = categories.find(c => c.id === categoryId);
    return category?.name || 'Sem categoria';
  };

  const getProfitMargin = (price, cost) => {
    if (!cost || cost === 0) return 100;
    return ((price - cost) / price * 100).toFixed(1);
  };

  // Abre ficha tecnica existente ou cria uma nova ja vinculada ao produto
  const openTechnicalSheet = async (product) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API}/api/technical-sheets/by-product/${product.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const sheet = await res.json();
        navigate(`/technical-sheets/${sheet.id}`);
      } else if (res.status === 404) {
        toast.info('Criando nova ficha tecnica para ' + product.name);
        navigate(`/technical-sheets/new?product_id=${product.id}`);
      } else {
        toast.error('Erro ao verificar ficha tecnica');
      }
    } catch (e) {
      toast.error('Erro de conexao');
    }
  };

  // ============ RECEITA TECNICA / CMV ============
  const openRecipeDialog = async (product) => {
    setRecipeProduct(product);
    setRecipeId(null);
    setRecipeItems([]);
    setIsRecipeDialogOpen(true);
    setRecipeLoading(true);
    try {
      // Carrega itens de estoque (precisam ter unit_cost > 0 idealmente)
      const stockRes = await stockAPI.getAll();
      const allProds = products.length ? products : (await productsAPI.getAll()).data;
      const prodById = Object.fromEntries(allProds.map(p => [p.id, p]));
      const opts = stockRes.data.map(s => ({
        id: s.id,
        product_id: s.product_id,
        unit: s.unit,
        unit_cost: Number(s.unit_cost || 0),
        name: prodById[s.product_id]?.name || s.product_id,
      })).sort((a, b) => a.name.localeCompare(b.name));
      setStockOptions(opts);

      // Tenta carregar receita existente
      try {
        const recipeRes = await recipesAPI.getByProduct(product.id);
        setRecipeId(recipeRes.data.id);
        setRecipeItems(recipeRes.data.ingredients || []);
      } catch (e) {
        // 404 = nao existe ainda
        setRecipeItems([{ stock_item_id: '', quantity: '' }]);
      }
    } catch (e) {
      toast.error('Erro ao carregar receita');
    } finally {
      setRecipeLoading(false);
    }
  };

  const addRecipeItem = () => setRecipeItems(items => [...items, { stock_item_id: '', quantity: '' }]);
  const removeRecipeItem = (idx) => setRecipeItems(items => items.filter((_, i) => i !== idx));
  const updateRecipeItem = (idx, field, value) => {
    setRecipeItems(items => items.map((it, i) => i === idx ? { ...it, [field]: value } : it));
  };

  // Calculo em tempo real é feito pelo componente RecipeSummary

  const handleSaveRecipe = async () => {
    if (!recipeProduct) return;
    const cleanItems = recipeItems
      .filter(i => i.stock_item_id && parseFloat(i.quantity) > 0)
      .map(i => ({ stock_item_id: i.stock_item_id, quantity: parseFloat(i.quantity) }));

    setRecipeSaving(true);
    try {
      if (recipeId) {
        await recipesAPI.update(recipeId, { ingredients: cleanItems });
      } else {
        const created = await recipesAPI.create({
          product_id: recipeProduct.id,
          ingredients: cleanItems,
        });
        setRecipeId(created.data.id);
      }
      toast.success('Receita salva!');
      // Atualiza CMV map para refletir nos cards
      const reportRes = await cmvAPI.getReport();
      const map = {};
      for (const row of reportRes.data) map[row.product_id] = row;
      setCmvMap(map);
      setIsRecipeDialogOpen(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Erro ao salvar receita');
    } finally {
      setRecipeSaving(false);
    }
  };
  // ================================================

  if (loading) {
    return (
      <Layout title="Cardápio">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Cardápio">
      <div className="space-y-6" data-testid="menu-page">
        <Tabs defaultValue="products">
          <TabsList>
            <TabsTrigger value="products">Produtos</TabsTrigger>
            <TabsTrigger value="categories">Categorias</TabsTrigger>
          </TabsList>

          <TabsContent value="products" className="space-y-4">
            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-4 justify-between">
              <div className="flex gap-4 flex-1">
                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Buscar produto..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                    data-testid="search-product"
                  />
                </div>
                <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Categoria" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    {categories.map(cat => (
                      <SelectItem key={cat.id} value={cat.id}>
                        {cat.icon} {cat.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={() => openProductDialog()} data-testid="add-product-btn">
                <Plus className="h-4 w-4 mr-2" />
                Novo Produto
              </Button>
            </div>

            {/* Products Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredProducts.map(product => (
                <Card key={product.id} className="card-hover" data-testid={`product-card-${product.id}`}>
                  <CardContent className="p-4">
                    <div className="flex gap-4">
                      {product.image_url ? (
                        <img
                          src={product.image_url}
                          alt={product.name}
                          className="w-24 h-24 object-cover rounded-lg"
                        />
                      ) : (
                        <div className="w-24 h-24 bg-muted rounded-lg flex items-center justify-center">
                          <Image className="h-8 w-8 text-muted-foreground" />
                        </div>
                      )}
                      <div className="flex-1">
                        <div className="flex items-start justify-between">
                          <div>
                            <h3 className="font-medium">{product.name}</h3>
                            <p className="text-sm text-muted-foreground">
                              {getCategoryName(product.category_id)}
                            </p>
                          </div>
                          <Badge variant={product.type === 'food' ? 'default' : 'secondary'}>
                            {product.type === 'food' ? <UtensilsCrossed className="h-3 w-3" /> : <Wine className="h-3 w-3" />}
                          </Badge>
                        </div>
                        <div className="mt-2 flex items-center gap-2">
                          <span className="text-lg font-bold text-primary">
                            {formatCurrency(product.price)}
                          </span>
                          {product.cost > 0 && (
                            <Badge variant="outline" className="text-xs">
                              {getProfitMargin(product.price, product.cost)}% margem
                            </Badge>
                          )}
                        </div>
                        <div className="mt-2 flex items-center gap-2">
                          <Badge variant={product.is_available ? 'default' : 'destructive'}>
                            {product.is_available ? 'Disponível' : 'Indisponível'}
                          </Badge>
                        </div>
                      </div>
                    </div>

                    {/* CMV / Lucro / Margem */}
                    {cmvMap[product.id] && (
                      <div className="mt-3 grid grid-cols-3 gap-2 text-center" data-testid={`cmv-summary-${product.id}`}>
                        <div className="rounded-md border border-border bg-muted/40 p-2">
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Custo</p>
                          <p className="text-sm font-bold text-foreground">
                            {formatCurrency(cmvMap[product.id].cost)}
                          </p>
                        </div>
                        <div className="rounded-md border border-border bg-muted/40 p-2">
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Lucro</p>
                          <p className={cn(
                            "text-sm font-bold",
                            cmvMap[product.id].profit >= 0 ? "text-emerald-500" : "text-destructive"
                          )}>
                            {formatCurrency(cmvMap[product.id].profit)}
                          </p>
                        </div>
                        <div className="rounded-md border border-border bg-muted/40 p-2">
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Margem</p>
                          <p className={cn(
                            "text-sm font-bold",
                            cmvMap[product.id].margin >= 50 ? "text-emerald-500" :
                            cmvMap[product.id].margin >= 20 ? "text-amber-400" : "text-destructive"
                          )}>
                            {cmvMap[product.id].margin.toFixed(1)}%
                          </p>
                        </div>
                      </div>
                    )}
                    {!cmvMap[product.id]?.has_recipe && (
                      <p className="mt-2 text-[10px] text-muted-foreground italic" data-testid={`no-recipe-${product.id}`}>
                        Sem receita técnica · CMV não calculado
                      </p>
                    )}
                    <div className="flex gap-2 mt-4 pt-4 border-t">
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={() => openProductDialog(product)}
                        data-testid={`edit-product-${product.id}`}
                      >
                        <Pencil className="h-4 w-4 mr-2" />
                        Editar
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1 border-primary/40 text-primary hover:bg-primary/10"
                        onClick={() => openTechnicalSheet(product)}
                        data-testid={`technical-sheet-${product.id}`}
                        title="Abrir ou criar ficha tecnica"
                      >
                        <FileText className="h-4 w-4 mr-2" />
                        Ficha Tecnica
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
                        onClick={() => openRecipeDialog(product)}
                        data-testid={`recipe-btn-${product.id}`}
                        title="Receita tecnica para calculo de CMV"
                      >
                        <Calculator className="h-4 w-4 mr-2" />
                        Receita
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive"
                        onClick={() => handleDeleteProduct(product.id)}
                        data-testid={`delete-product-${product.id}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {filteredProducts.length === 0 && (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Nenhum produto encontrado</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="categories" className="space-y-4">
            <div className="flex justify-end">
              <Button onClick={() => openCategoryDialog()} data-testid="add-category-btn">
                <Plus className="h-4 w-4 mr-2" />
                Nova Categoria
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {categories.map(category => (
                <Card key={category.id} className="card-hover" data-testid={`category-card-${category.id}`}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl">{category.icon}</span>
                        <h3 className="font-heading text-lg">{category.name}</h3>
                      </div>
                      <Badge variant={category.type === 'food' ? 'default' : 'secondary'}>
                        {category.type === 'food' ? 'Comida' : 'Bebida'}
                      </Badge>
                    </div>
                    {category.description && (
                      <p className="text-sm text-muted-foreground mb-4">
                        {category.description}
                      </p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={() => openCategoryDialog(category)}
                      >
                        <Pencil className="h-4 w-4 mr-2" />
                        Editar
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive"
                        onClick={() => handleDeleteCategory(category.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        {/* Product Dialog */}
        <Dialog open={isProductDialogOpen} onOpenChange={setIsProductDialogOpen}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle className="font-heading">
                {editingProduct ? 'Editar Produto' : 'Novo Produto'}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2 space-y-2">
                  <Label>Nome *</Label>
                  <Input
                    value={productForm.name}
                    onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
                    data-testid="product-name-input"
                  />
                </div>
                <div className="col-span-2 space-y-2">
                  <Label>Descrição</Label>
                  <Textarea
                    value={productForm.description}
                    onChange={(e) => setProductForm({ ...productForm, description: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Categoria *</Label>
                  <Select
                    value={productForm.category_id}
                    onValueChange={(v) => setProductForm({ ...productForm, category_id: v })}
                  >
                    <SelectTrigger data-testid="product-category-select">
                      <SelectValue placeholder="Selecione" />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map(cat => (
                        <SelectItem key={cat.id} value={cat.id}>
                          {cat.icon} {cat.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Tipo</Label>
                  <Select
                    value={productForm.type}
                    onValueChange={(v) => setProductForm({ ...productForm, type: v })}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="food">Comida</SelectItem>
                      <SelectItem value="drink">Bebida</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Preço de Venda *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={productForm.price}
                    onChange={(e) => setProductForm({ ...productForm, price: e.target.value })}
                    data-testid="product-price-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Custo</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={productForm.cost}
                    onChange={(e) => setProductForm({ ...productForm, cost: e.target.value })}
                  />
                </div>
                <div className="col-span-2 space-y-2">
                  <Label>URL da Imagem</Label>
                  <Input
                    value={productForm.image_url}
                    onChange={(e) => setProductForm({ ...productForm, image_url: e.target.value })}
                    placeholder="https://..."
                  />
                </div>
                <div className="space-y-2">
                  <Label>Tempo de Preparo (min)</Label>
                  <Input
                    type="number"
                    value={productForm.preparation_time}
                    onChange={(e) => setProductForm({ ...productForm, preparation_time: parseInt(e.target.value) })}
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={productForm.is_available}
                    onCheckedChange={(v) => setProductForm({ ...productForm, is_available: v })}
                  />
                  <Label>Disponível</Label>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsProductDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleSaveProduct} data-testid="save-product-btn">
                Salvar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Category Dialog */}
        <Dialog open={isCategoryDialogOpen} onOpenChange={setIsCategoryDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="font-heading">
                {editingCategory ? 'Editar Categoria' : 'Nova Categoria'}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Nome *</Label>
                <Input
                  value={categoryForm.name}
                  onChange={(e) => setCategoryForm({ ...categoryForm, name: e.target.value })}
                  data-testid="category-name-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select
                  value={categoryForm.type}
                  onValueChange={(v) => setCategoryForm({ ...categoryForm, type: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="food">Comida</SelectItem>
                    <SelectItem value="drink">Bebida</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Ícone (emoji)</Label>
                <Input
                  value={categoryForm.icon}
                  onChange={(e) => setCategoryForm({ ...categoryForm, icon: e.target.value })}
                  placeholder="🍔"
                />
              </div>
              <div className="space-y-2">
                <Label>Descrição</Label>
                <Textarea
                  value={categoryForm.description}
                  onChange={(e) => setCategoryForm({ ...categoryForm, description: e.target.value })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCategoryDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleSaveCategory} data-testid="save-category-btn">
                Salvar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Recipe / CMV Dialog */}
        <Dialog open={isRecipeDialogOpen} onOpenChange={setIsRecipeDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="recipe-dialog">
            <DialogHeader>
              <DialogTitle className="font-heading flex items-center gap-2">
                <Calculator className="h-5 w-5 text-emerald-500" />
                Receita Técnica · {recipeProduct?.name}
              </DialogTitle>
            </DialogHeader>

            {recipeLoading ? (
              <div className="py-12 text-center text-muted-foreground">Carregando...</div>
            ) : (
              <div className="space-y-4">
                {/* Painel de calculo em tempo real */}
                {recipeProduct && (
                  <RecipeSummary
                    recipeItems={recipeItems}
                    stockOptions={stockOptions}
                    salePrice={Number(recipeProduct.price || 0)}
                  />
                )}

                {/* Ingredientes */}
                <div className="space-y-2">
                  <Label className="flex items-center justify-between">
                    <span>Ingredientes (itens do estoque)</span>
                    {stockOptions.length === 0 && (
                      <span className="text-xs text-amber-500">Nenhum item de estoque cadastrado</span>
                    )}
                  </Label>

                  {recipeItems.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">
                      Clique em &quot;Adicionar Ingrediente&quot; para iniciar.
                    </p>
                  ) : (
                    recipeItems.map((item, idx) => {
                      const stock = stockOptions.find(s => s.id === item.stock_item_id);
                      const qty = parseFloat(item.quantity) || 0;
                      const line = stock ? qty * stock.unit_cost : 0;
                      return (
                        <div key={idx} className="flex gap-2 items-center" data-testid={`recipe-item-${idx}`}>
                          <Select
                            value={item.stock_item_id}
                            onValueChange={v => updateRecipeItem(idx, 'stock_item_id', v)}
                          >
                            <SelectTrigger className="flex-1" data-testid={`recipe-stock-select-${idx}`}>
                              <SelectValue placeholder="Selecione o item do estoque" />
                            </SelectTrigger>
                            <SelectContent>
                              {stockOptions.map(s => (
                                <SelectItem key={s.id} value={s.id}>
                                  {s.name} · R$ {s.unit_cost.toFixed(2)}/{s.unit}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Input
                            type="number"
                            step="0.01"
                            min="0"
                            placeholder="Qtd"
                            value={item.quantity}
                            onChange={e => updateRecipeItem(idx, 'quantity', e.target.value)}
                            className="w-24"
                            data-testid={`recipe-qty-${idx}`}
                          />
                          <div className="w-24 text-right text-xs text-muted-foreground">
                            {stock ? `= ${formatCurrency(line)}` : ''}
                          </div>
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            onClick={() => removeRecipeItem(idx)}
                            data-testid={`recipe-remove-${idx}`}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      );
                    })
                  )}

                  <Button
                    type="button"
                    variant="outline"
                    onClick={addRecipeItem}
                    className="w-full"
                    disabled={stockOptions.length === 0}
                    data-testid="recipe-add-item-btn"
                  >
                    <Plus className="h-4 w-4 mr-2" /> Adicionar Ingrediente
                  </Button>
                </div>

                <p className="text-xs text-muted-foreground">
                  <TrendingUp className="h-3 w-3 inline mr-1" />
                  O cálculo usa o custo unitário (R$/unidade) cadastrado em cada item do estoque.
                </p>
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => setIsRecipeDialogOpen(false)} data-testid="recipe-cancel-btn">
                Cancelar
              </Button>
              <Button
                onClick={handleSaveRecipe}
                disabled={recipeSaving || recipeLoading}
                data-testid="recipe-save-btn"
              >
                {recipeSaving ? 'Salvando...' : (recipeId ? 'Atualizar Receita' : 'Criar Receita')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
