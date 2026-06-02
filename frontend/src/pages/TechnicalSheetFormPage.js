import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Trash2, Save, Loader2, GripVertical, Upload, X } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const MAX_IMG_BYTES = 2 * 1024 * 1024; // 2MB

export default function TechnicalSheetFormPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isEdit = !!id;
  const fileInputRef = useRef(null);
  const [products, setProducts] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    product_id: '',
    product_name: '',
    image_url: '',
    ingredients: [{ name: '', quantity: '' }],
    assembly_steps: [''],
    notes: '',
  });

  useEffect(() => {
    const token = localStorage.getItem('token');
    const loads = [
      fetch(`${API}/api/products`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
    ];
    if (isEdit) {
      loads.push(fetch(`${API}/api/technical-sheets/${id}`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()));
    }
    Promise.all(loads)
      .then(([prods, sheet]) => {
        setProducts(prods);
        if (sheet && sheet.id) {
          setForm({
            product_id: sheet.product_id,
            product_name: sheet.product_name,
            image_url: sheet.image_url || '',
            ingredients: sheet.ingredients?.length ? sheet.ingredients : [{ name: '', quantity: '' }],
            assembly_steps: sheet.assembly_steps?.length ? sheet.assembly_steps : [''],
            notes: sheet.notes || '',
          });
        } else if (!isEdit) {
          // Pre-preenchimento via query params quando vier do Cardapio
          const qpId = searchParams.get('product_id');
          if (qpId) {
            const p = prods.find(pr => pr.id === qpId);
            if (p) {
              setForm(f => ({
                ...f,
                product_id: p.id,
                product_name: p.name,
                image_url: p.image_url || '',
              }));
            }
          }
        }
      })
      .catch(() => toast.error('Erro ao carregar dados'))
      .finally(() => setLoading(false));
  }, [id, isEdit, searchParams]);

  const handleProductChange = (productId) => {
    const p = products.find(pr => pr.id === productId);
    setForm(f => ({ ...f, product_id: productId, product_name: p?.name || '', image_url: p?.image_url || f.image_url }));
  };

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Selecione um arquivo de imagem');
      return;
    }
    if (file.size > MAX_IMG_BYTES) {
      toast.error('Imagem muito grande (max 2MB)');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setForm(f => ({ ...f, image_url: reader.result }));
      toast.success('Imagem carregada');
    };
    reader.onerror = () => toast.error('Erro ao ler arquivo');
    reader.readAsDataURL(file);
  };

  const updateIngredient = (idx, field, value) => {
    setForm(f => {
      const ing = [...f.ingredients];
      ing[idx] = { ...ing[idx], [field]: value };
      return { ...f, ingredients: ing };
    });
  };
  const addIngredient = () => setForm(f => ({ ...f, ingredients: [...f.ingredients, { name: '', quantity: '' }] }));
  const removeIngredient = (idx) => setForm(f => ({ ...f, ingredients: f.ingredients.filter((_, i) => i !== idx) }));

  const updateStep = (idx, value) => {
    setForm(f => {
      const steps = [...f.assembly_steps];
      steps[idx] = value;
      return { ...f, assembly_steps: steps };
    });
  };
  const addStep = () => setForm(f => ({ ...f, assembly_steps: [...f.assembly_steps, ''] }));
  const removeStep = (idx) => setForm(f => ({ ...f, assembly_steps: f.assembly_steps.filter((_, i) => i !== idx) }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.product_id) { toast.error('Selecione um produto'); return; }
    if (!form.ingredients.some(i => i.name.trim())) { toast.error('Adicione pelo menos 1 ingrediente'); return; }

    const body = {
      ...form,
      ingredients: form.ingredients.filter(i => i.name.trim()),
      assembly_steps: form.assembly_steps.filter(s => s.trim()),
    };

    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const url = isEdit ? `${API}/api/technical-sheets/${id}` : `${API}/api/technical-sheets`;
      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Erro');
      }
      const saved = await res.json();
      toast.success(isEdit ? 'Ficha atualizada!' : 'Ficha criada!');
      navigate(`/technical-sheets/${saved.id}`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <Layout title="Ficha Tecnica"><div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div></Layout>;
  }

  return (
    <Layout title={isEdit ? 'Editar Ficha Tecnica' : 'Nova Ficha Tecnica'}>
      <form onSubmit={handleSubmit} className="space-y-6 max-w-3xl" data-testid="sheet-form">
        <Button type="button" variant="ghost" onClick={() => navigate('/technical-sheets')} className="mb-2" data-testid="back-btn">
          <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
        </Button>

        {/* Produto */}
        <Card>
          <CardHeader><CardTitle className="font-heading">Produto</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Selecionar Produto</Label>
              <Select value={form.product_id} onValueChange={handleProductChange} disabled={isEdit}>
                <SelectTrigger data-testid="select-product"><SelectValue placeholder="Escolha um produto" /></SelectTrigger>
                <SelectContent>
                  {products.map(p => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Foto do Prato</Label>
              <div className="flex gap-2">
                <Input
                  value={form.image_url?.startsWith('data:') ? '' : form.image_url}
                  onChange={e => setForm(f => ({ ...f, image_url: e.target.value }))}
                  placeholder="https://... ou faca upload"
                  data-testid="image-url"
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleFileUpload}
                  data-testid="image-file-input"
                />
                <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()} data-testid="upload-image-btn">
                  <Upload className="h-4 w-4 mr-2" /> Upload
                </Button>
              </div>
              {form.image_url && (
                <div className="relative inline-block mt-2">
                  <img src={form.image_url} alt="Preview" className="h-32 rounded-lg object-cover" data-testid="image-preview" />
                  <Button
                    type="button"
                    size="icon"
                    variant="destructive"
                    className="absolute -top-2 -right-2 h-6 w-6 rounded-full"
                    onClick={() => setForm(f => ({ ...f, image_url: '' }))}
                    data-testid="remove-image-btn"
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              )}
              <p className="text-xs text-muted-foreground">Cole uma URL ou envie do dispositivo (max 2MB)</p>
            </div>
          </CardContent>
        </Card>

        {/* Ingredientes */}
        <Card>
          <CardHeader><CardTitle className="font-heading">Ingredientes</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {form.ingredients.map((ing, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />
                <Input placeholder="Nome" value={ing.name} onChange={e => updateIngredient(idx, 'name', e.target.value)} className="flex-1" data-testid={`ing-name-${idx}`} />
                <Input placeholder="Quantidade" value={ing.quantity} onChange={e => updateIngredient(idx, 'quantity', e.target.value)} className="w-36" data-testid={`ing-qty-${idx}`} />
                {form.ingredients.length > 1 && (
                  <Button type="button" size="icon" variant="ghost" onClick={() => removeIngredient(idx)} data-testid={`remove-ing-${idx}`}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                )}
              </div>
            ))}
            <Button type="button" variant="outline" onClick={addIngredient} className="w-full" data-testid="add-ingredient">
              <Plus className="h-4 w-4 mr-2" /> Adicionar Ingrediente
            </Button>
          </CardContent>
        </Card>

        {/* Montagem */}
        <Card>
          <CardHeader><CardTitle className="font-heading">Passo a Passo de Montagem</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {form.assembly_steps.map((step, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <span className="text-sm font-bold text-primary w-6 shrink-0">{idx + 1}.</span>
                <Input value={step} onChange={e => updateStep(idx, e.target.value)} placeholder={`Passo ${idx + 1}`} className="flex-1" data-testid={`step-${idx}`} />
                {form.assembly_steps.length > 1 && (
                  <Button type="button" size="icon" variant="ghost" onClick={() => removeStep(idx)} data-testid={`remove-step-${idx}`}>
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                )}
              </div>
            ))}
            <Button type="button" variant="outline" onClick={addStep} className="w-full" data-testid="add-step">
              <Plus className="h-4 w-4 mr-2" /> Adicionar Passo
            </Button>
          </CardContent>
        </Card>

        {/* Observações */}
        <Card>
          <CardHeader><CardTitle className="font-heading">Observacoes</CardTitle></CardHeader>
          <CardContent>
            <Textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} rows={4} placeholder="Observacoes adicionais..." data-testid="notes-input" />
          </CardContent>
        </Card>

        <Button type="submit" disabled={saving} className="w-full font-heading uppercase tracking-widest" data-testid="save-sheet">
          {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
          {isEdit ? 'Atualizar Ficha' : 'Criar Ficha Tecnica'}
        </Button>
      </form>
    </Layout>
  );
}
