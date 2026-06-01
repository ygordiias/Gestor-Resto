import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';
import { ArrowLeft, Pencil, Printer, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { Logo } from '../components/Logo';

const API = process.env.REACT_APP_BACKEND_URL;

export default function TechnicalSheetViewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const [sheet, setSheet] = useState(null);
  const [loading, setLoading] = useState(true);
  const canEdit = ['superadmin', 'admin'].includes(user?.role);

  useEffect(() => {
    const token = localStorage.getItem('token');
    fetch(`${API}/api/technical-sheets/${id}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(data => {
        setSheet(data);
        if (searchParams.get('print') === '1') {
          setTimeout(() => window.print(), 600);
        }
      })
      .catch(() => toast.error('Erro ao carregar ficha'))
      .finally(() => setLoading(false));
  }, [id, searchParams]);

  if (loading) {
    return <Layout title="Ficha Tecnica"><div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div></Layout>;
  }

  if (!sheet) {
    return <Layout title="Ficha Tecnica"><p className="text-center py-12 text-muted-foreground">Ficha nao encontrada</p></Layout>;
  }

  return (
    <Layout title="Ficha Tecnica">
      <div className="max-w-3xl space-y-4" data-testid="sheet-view">
        {/* Toolbar - hidden on print */}
        <div className="flex gap-2 no-print">
          <Button variant="ghost" onClick={() => navigate('/technical-sheets')}>
            <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
          </Button>
          <div className="flex-1" />
          {canEdit && (
            <Button variant="outline" onClick={() => navigate(`/technical-sheets/${id}/edit`)}>
              <Pencil className="h-4 w-4 mr-2" /> Editar
            </Button>
          )}
          <Button onClick={() => window.print()} data-testid="print-btn">
            <Printer className="h-4 w-4 mr-2" /> Imprimir Ficha
          </Button>
        </div>

        {/* Print header - visible only on print */}
        <div className="hidden print:block text-center mb-6">
          <Logo size="md" className="justify-center mb-2" />
          <p className="text-xs text-muted-foreground">Ficha Tecnica</p>
        </div>

        {/* Foto + Nome */}
        <Card className="overflow-hidden">
          {sheet.image_url && (
            <img src={sheet.image_url} alt={sheet.product_name} className="w-full h-56 object-cover print:h-40" />
          )}
          <CardContent className="p-6">
            <h1 className="font-heading text-2xl font-bold">{sheet.product_name}</h1>
          </CardContent>
        </Card>

        {/* Ingredientes */}
        <Card>
          <CardContent className="p-6">
            <h2 className="font-heading text-lg font-bold mb-4">Ingredientes</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 font-semibold">Ingrediente</th>
                  <th className="text-right py-2 font-semibold">Quantidade</th>
                </tr>
              </thead>
              <tbody>
                {sheet.ingredients?.map((ing, idx) => (
                  <tr key={idx} className="border-b border-border/50">
                    <td className="py-2">{ing.name}</td>
                    <td className="py-2 text-right text-muted-foreground">{ing.quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Montagem */}
        {sheet.assembly_steps?.length > 0 && (
          <Card>
            <CardContent className="p-6">
              <h2 className="font-heading text-lg font-bold mb-4">Montagem</h2>
              <ol className="space-y-2">
                {sheet.assembly_steps.map((step, idx) => (
                  <li key={idx} className="flex gap-3">
                    <span className="font-bold text-primary shrink-0">{idx + 1}.</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        )}

        {/* Observações */}
        {sheet.notes && (
          <Card>
            <CardContent className="p-6">
              <h2 className="font-heading text-lg font-bold mb-2">Observacoes</h2>
              <p className="text-muted-foreground whitespace-pre-wrap">{sheet.notes}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
