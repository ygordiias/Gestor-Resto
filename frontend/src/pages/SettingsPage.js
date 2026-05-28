import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { Settings, Store, Receipt, Database, Save, Loader2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [restaurant, setRestaurant] = useState({
    name: '',
    cnpj: '',
    address: '',
  });
  const [operations, setOperations] = useState({
    serviceFeePercentage: 10,
    autoCloseKitchenItems: true,
    enableNotifications: true,
  });
  const [fiscal, setFiscal] = useState({
    taxEnabled: false,
    taxApiKey: '',
  });

  useEffect(() => {
    const token = localStorage.getItem('token');
    fetch(`${API}/api/settings`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => {
        if (data.restaurant) setRestaurant(prev => ({ ...prev, ...data.restaurant }));
        if (data.operations) setOperations(prev => ({ ...prev, ...data.operations }));
        if (data.fiscal) setFiscal(prev => ({ ...prev, ...data.fiscal }));
      })
      .catch(() => toast.error('Erro ao carregar configurações'))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ restaurant, operations, fiscal }),
      });
      if (!res.ok) throw new Error();
      toast.success('Configurações salvas!');
    } catch {
      toast.error('Erro ao salvar');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Layout title="Configurações">
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Configurações">
      <div className="space-y-6 max-w-4xl" data-testid="settings-page">
        <Tabs defaultValue="restaurant">
          <TabsList className="mb-6">
            <TabsTrigger value="restaurant">
              <Store className="h-4 w-4 mr-2" />
              Estabelecimento
            </TabsTrigger>
            <TabsTrigger value="operation">
              <Settings className="h-4 w-4 mr-2" />
              Operação
            </TabsTrigger>
            <TabsTrigger value="fiscal">
              <Receipt className="h-4 w-4 mr-2" />
              Fiscal
            </TabsTrigger>
          </TabsList>

          <TabsContent value="restaurant">
            <Card>
              <CardHeader>
                <CardTitle className="font-heading">Dados do Estabelecimento</CardTitle>
                <CardDescription>Informações básicas do seu restaurante</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Nome do Restaurante</Label>
                    <Input
                      value={restaurant.name}
                      onChange={e => setRestaurant({ ...restaurant, name: e.target.value })}
                      data-testid="restaurant-name-input"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>CNPJ</Label>
                    <Input
                      value={restaurant.cnpj}
                      onChange={e => setRestaurant({ ...restaurant, cnpj: e.target.value })}
                      placeholder="00.000.000/0000-00"
                      data-testid="cnpj-input"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label>Endereço</Label>
                    <Input
                      value={restaurant.address}
                      onChange={e => setRestaurant({ ...restaurant, address: e.target.value })}
                      placeholder="Rua, número, bairro, cidade - UF"
                      data-testid="address-input"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="operation">
            <Card>
              <CardHeader>
                <CardTitle className="font-heading">Configurações de Operação</CardTitle>
                <CardDescription>Ajuste o funcionamento do sistema</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <Label>Taxa de Serviço (%)</Label>
                  <Input
                    type="number"
                    value={operations.serviceFeePercentage}
                    onChange={e => setOperations({ ...operations, serviceFeePercentage: parseFloat(e.target.value) || 0 })}
                    data-testid="service-fee-input"
                  />
                  <p className="text-sm text-muted-foreground">
                    Porcentagem aplicada automaticamente nas comandas
                  </p>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Fechar itens automaticamente</Label>
                    <p className="text-sm text-muted-foreground">
                      Marcar itens como entregues automaticamente após "Pronto"
                    </p>
                  </div>
                  <Switch
                    checked={operations.autoCloseKitchenItems}
                    onCheckedChange={v => setOperations({ ...operations, autoCloseKitchenItems: v })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Notificações sonoras</Label>
                    <p className="text-sm text-muted-foreground">
                      Alertas sonoros para novos pedidos na cozinha/bar
                    </p>
                  </div>
                  <Switch
                    checked={operations.enableNotifications}
                    onCheckedChange={v => setOperations({ ...operations, enableNotifications: v })}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="fiscal">
            <Card>
              <CardHeader>
                <CardTitle className="font-heading">Configurações Fiscais</CardTitle>
                <CardDescription>Integração com sistemas de NF-e (em desenvolvimento)</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Emissão de NF-e</Label>
                    <p className="text-sm text-muted-foreground">
                      Habilitar emissão automática de notas fiscais
                    </p>
                  </div>
                  <Switch
                    checked={fiscal.taxEnabled}
                    onCheckedChange={v => setFiscal({ ...fiscal, taxEnabled: v })}
                  />
                </div>
                {fiscal.taxEnabled && (
                  <div className="space-y-2">
                    <Label>Chave da API (NF-e)</Label>
                    <Input
                      type="password"
                      value={fiscal.taxApiKey}
                      onChange={e => setFiscal({ ...fiscal, taxApiKey: e.target.value })}
                      placeholder="Sua chave de API do serviço de NF-e"
                    />
                  </div>
                )}
                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground">
                    A integração com NF-e requer contratação de serviço de emissão e certificado digital.
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving} className="font-heading uppercase tracking-widest" data-testid="save-settings-btn">
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
            Salvar Configurações
          </Button>
        </div>

        <Card className="bg-muted/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-4">
              <Database className="h-8 w-8 text-primary" />
              <div>
                <p className="font-heading">Gestor Restô v1.0</p>
                <p className="text-sm text-muted-foreground">Sistema de Gestão para Restaurante</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
