import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { invoicesAPI } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/utils';
import { toast } from 'sonner';
import { FileText, AlertTriangle, Download } from 'lucide-react';

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchInvoices();
  }, []);

  const fetchInvoices = async () => {
    try {
      const response = await invoicesAPI.getAll();
      setInvoices(response.data);
    } catch (error) {
      toast.error('Erro ao carregar notas fiscais');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const config = {
      mock: { label: 'MOCK', variant: 'secondary' },
      pending: { label: 'Pendente', variant: 'outline' },
      issued: { label: 'Emitida', variant: 'default' },
      cancelled: { label: 'Cancelada', variant: 'destructive' },
    };
    return config[status] || { label: status, variant: 'secondary' };
  };

  if (loading) {
    return (
      <Layout title="Notas Fiscais">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Notas Fiscais">
      <div className="space-y-6" data-testid="invoices-page">
        {/* Info Card */}
        <Card className="bg-amber-50 dark:bg-amber-900/20 border-amber-400">
          <CardContent className="p-4 flex items-start gap-4">
            <AlertTriangle className="h-6 w-6 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="font-medium text-amber-800 dark:text-amber-200">
                Módulo de NF-e (MOCK)
              </h3>
              <p className="text-sm text-amber-700 dark:text-amber-300">
                Este módulo está preparado para integração futura com APIs de emissão de 
                Nota Fiscal Eletrônica (Focus NFe, Webmania, etc.). 
                Atualmente as notas são registradas como MOCK para fins de demonstração.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Invoices List */}
        <div className="space-y-4">
          {invoices.length > 0 ? (
            invoices.map(invoice => {
              const statusConfig = getStatusBadge(invoice.status);
              
              return (
                <Card key={invoice.id} className="card-hover" data-testid={`invoice-${invoice.id}`}>
                  <CardContent className="p-4">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="flex items-center gap-4">
                        <div className="p-3 bg-muted rounded-lg">
                          <FileText className="h-6 w-6 text-primary" />
                        </div>
                        <div>
                          <h3 className="font-heading text-lg">{invoice.number}</h3>
                          <p className="text-sm text-muted-foreground">
                            Pedido: {invoice.order_id.slice(0, 8)}...
                          </p>
                        </div>
                      </div>
                      
                      <div className="flex flex-wrap items-center gap-4">
                        {invoice.customer_name && (
                          <div className="text-sm">
                            <span className="text-muted-foreground">Cliente: </span>
                            <span>{invoice.customer_name}</span>
                          </div>
                        )}
                        {invoice.customer_cpf && (
                          <div className="text-sm">
                            <span className="text-muted-foreground">CPF: </span>
                            <span>{invoice.customer_cpf}</span>
                          </div>
                        )}
                        <div className="text-lg font-bold text-primary">
                          {formatCurrency(invoice.total)}
                        </div>
                        <Badge variant={statusConfig.variant}>
                          {statusConfig.label}
                        </Badge>
                      </div>
                    </div>
                    
                    <div className="mt-4 pt-4 border-t flex justify-between items-center">
                      <span className="text-sm text-muted-foreground">
                        Emitido em {formatDate(invoice.created_at)}
                      </span>
                      <Button variant="outline" size="sm" disabled>
                        <Download className="h-4 w-4 mr-2" />
                        Baixar XML
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          ) : (
            <Card>
              <CardContent className="p-12 text-center">
                <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-muted-foreground">
                  Nenhuma nota fiscal emitida
                </p>
                <p className="text-sm text-muted-foreground mt-2">
                  As notas são geradas automaticamente ao fechar comandas no caixa
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Integration Info */}
        <Card>
          <CardHeader>
            <CardTitle className="font-heading">Integração Futura</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Para ativar a emissão real de NF-e, será necessário:
            </p>
            <ul className="list-disc list-inside space-y-2 text-sm text-muted-foreground">
              <li>Contratar um serviço de emissão de NF-e (Focus NFe, Webmania, etc.)</li>
              <li>Cadastrar os dados fiscais do estabelecimento (CNPJ, IE, etc.)</li>
              <li>Obter certificado digital A1</li>
              <li>Configurar as credenciais da API no sistema</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
