import React, { useState, useEffect } from 'react';
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
import { productsAPI, categoriesAPI } from '../lib/api';
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
  DollarSign
} from 'lucide-react';

export default function MenuPage() {
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

  useEffect(() => {
    fetchData();
  }, []);

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
      </div>
    </Layout>
  );
}
