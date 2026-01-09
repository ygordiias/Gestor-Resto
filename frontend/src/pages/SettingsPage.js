import React, { useState } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { 
  Settings,
  Store,
  Receipt,
  Bell,
  Palette,
  Database,
  Save
} from 'lucide-react';

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    // Restaurant Info
    restaurantName: 'Digital Codex',
    address: '',
    phone: '',
    cnpj: '',
    
    // Operation
    serviceFeePercentage: 10,
    autoCloseKitchenItems: true,
    enableNotifications: true,
    
    // Tax
    taxEnabled: false,
    taxApiKey: '',
    taxCertificate: '',
  });

  const handleSave = () => {
    // In a real app, this would save to backend
    localStorage.setItem('restaurantSettings', JSON.stringify(settings));
    toast.success('Configurações salvas!');
  };

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
                <CardDescription>
                  Informações básicas do seu restaurante
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Nome do Restaurante</Label>
                    <Input
                      value={settings.restaurantName}
                      onChange={(e) => setSettings({ ...settings, restaurantName: e.target.value })}
                      data-testid="restaurant-name-input"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>CNPJ</Label>
                    <Input
                      value={settings.cnpj}
                      onChange={(e) => setSettings({ ...settings, cnpj: e.target.value })}
                      placeholder="00.000.000/0000-00"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label>Endereço</Label>
                    <Input
                      value={settings.address}
                      onChange={(e) => setSettings({ ...settings, address: e.target.value })}
                      placeholder="Rua, número, bairro, cidade - UF"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Telefone</Label>
                    <Input
                      value={settings.phone}
                      onChange={(e) => setSettings({ ...settings, phone: e.target.value })}
                      placeholder="(00) 00000-0000"
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
                <CardDescription>
                  Ajuste o funcionamento do sistema
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-2">
                  <Label>Taxa de Serviço (%)</Label>
                  <Input
                    type="number"
                    value={settings.serviceFeePercentage}
                    onChange={(e) => setSettings({ ...settings, serviceFeePercentage: parseFloat(e.target.value) })}
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
                    checked={settings.autoCloseKitchenItems}
                    onCheckedChange={(v) => setSettings({ ...settings, autoCloseKitchenItems: v })}
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
                    checked={settings.enableNotifications}
                    onCheckedChange={(v) => setSettings({ ...settings, enableNotifications: v })}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="fiscal">
            <Card>
              <CardHeader>
                <CardTitle className="font-heading">Configurações Fiscais</CardTitle>
                <CardDescription>
                  Integração com sistemas de NF-e (em desenvolvimento)
                </CardDescription>
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
                    checked={settings.taxEnabled}
                    onCheckedChange={(v) => setSettings({ ...settings, taxEnabled: v })}
                  />
                </div>

                {settings.taxEnabled && (
                  <>
                    <div className="space-y-2">
                      <Label>Chave da API (NF-e)</Label>
                      <Input
                        type="password"
                        value={settings.taxApiKey}
                        onChange={(e) => setSettings({ ...settings, taxApiKey: e.target.value })}
                        placeholder="Sua chave de API do serviço de NF-e"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Certificado Digital (A1)</Label>
                      <Input
                        type="file"
                        accept=".pfx,.p12"
                        disabled
                      />
                      <p className="text-sm text-muted-foreground">
                        Upload de certificado disponível em versão futura
                      </p>
                    </div>
                  </>
                )}

                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm text-muted-foreground">
                    ⚠️ A integração com sistemas de NF-e requer contratação de um 
                    serviço de emissão (Focus NFe, Webmania, etc.) e certificado digital.
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        <div className="flex justify-end">
          <Button onClick={handleSave} className="font-heading uppercase tracking-widest" data-testid="save-settings-btn">
            <Save className="h-4 w-4 mr-2" />
            Salvar Configurações
          </Button>
        </div>

        {/* System Info */}
        <Card className="bg-muted/50">
          <CardContent className="p-4">
            <div className="flex items-center gap-4">
              <Database className="h-8 w-8 text-primary" />
              <div>
                <p className="font-heading">Digital Codex v1.0</p>
                <p className="text-sm text-muted-foreground">
                  Sistema de Gestão para Restaurante
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
