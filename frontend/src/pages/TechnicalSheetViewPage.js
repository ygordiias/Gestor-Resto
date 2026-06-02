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
  const [restaurant, setRestaurant] = useState(null);
  const [loading, setLoading] = useState(true);
  const canEdit = ['superadmin', 'admin'].includes(user?.role);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const loads = [
      fetch(`${API}/api/technical-sheets/${id}`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()),
      fetch(`${API}/api/public/config`).then(r => r.ok ? r.json() : null).catch(() => null),
    ];
    Promise.all(loads)
      .then(([data, cfg]) => {
        setSheet(data);
        setRestaurant(cfg || null);
        if (searchParams.get('print') === '1') {
          setTimeout(() => window.print(), 700);
        }
      })
      .catch(() => toast.error('Erro ao carregar ficha'))
      .finally(() => setLoading(false));
  }, [id, searchParams]);

  if (loading) {
    return <Layout title="Ficha Tecnica"><div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div></Layout>;
  }

  if (!sheet || !sheet.id) {
    return <Layout title="Ficha Tecnica"><p className="text-center py-12 text-muted-foreground">Ficha nao encontrada</p></Layout>;
  }

  const today = new Date().toLocaleDateString('pt-BR');

  return (
    <Layout title="Ficha Tecnica">
      <div className="max-w-3xl mx-auto space-y-4" data-testid="sheet-view">
        {/* Toolbar - hidden on print */}
        <div className="flex gap-2 no-print">
          <Button variant="ghost" onClick={() => navigate('/technical-sheets')} data-testid="back-btn">
            <ArrowLeft className="h-4 w-4 mr-2" /> Voltar
          </Button>
          <div className="flex-1" />
          {canEdit && (
            <Button variant="outline" onClick={() => navigate(`/technical-sheets/${id}/edit`)} data-testid="edit-sheet-btn">
              <Pencil className="h-4 w-4 mr-2" /> Editar
            </Button>
          )}
          <Button onClick={() => window.print()} data-testid="print-btn">
            <Printer className="h-4 w-4 mr-2" /> Imprimir Ficha
          </Button>
        </div>

        {/* Print area - only visible block on print */}
        <div className="print-area space-y-4">
          {/* Cabecalho de impressao */}
          <div className="hidden print:flex items-center justify-between border-b-2 border-black pb-3 mb-4">
            <div className="flex flex-col">
              <Logo size="sm" />
              {restaurant?.restaurant_name && (
                <span className="text-xs mt-1">{restaurant.restaurant_name}</span>
              )}
            </div>
            <div className="text-right">
              <p className="text-xs font-bold uppercase tracking-widest">Ficha Tecnica</p>
              <p className="text-[10px]">Emitida em {today}</p>
            </div>
          </div>

          {/* Cabecalho visivel apenas na tela */}
          <Card className="overflow-hidden print:hidden print-avoid-break">
            {sheet.image_url && (
              <img src={sheet.image_url} alt={sheet.product_name} className="w-full h-56 object-cover" />
            )}
            <CardContent className="p-6">
              <h1 className="font-heading text-2xl font-bold" data-testid="sheet-product-name">{sheet.product_name}</h1>
            </CardContent>
          </Card>

          {/* Versao para impressao: foto + nome lado a lado */}
          <div className="hidden print:flex gap-4 items-start print-avoid-break">
            {sheet.image_url && (
              <img src={sheet.image_url} alt={sheet.product_name} className="w-40 h-40 object-cover border border-black/30" />
            )}
            <div className="flex-1">
              <h1 className="font-heading text-xl font-bold">{sheet.product_name}</h1>
              <p className="text-xs text-muted-foreground mt-1">
                {sheet.ingredients?.length || 0} ingredientes  ·  {sheet.assembly_steps?.length || 0} passos de montagem
              </p>
            </div>
          </div>

          {/* Ingredientes */}
          <Card className="print:shadow-none print:border print:border-black/30 print-avoid-break">
            <CardContent className="p-6 print:p-3">
              <h2 className="font-heading text-lg font-bold mb-4 print:mb-2 print:text-base">Ingredientes</h2>
              <table className="w-full text-sm print:text-xs">
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
                  {(!sheet.ingredients || sheet.ingredients.length === 0) && (
                    <tr><td colSpan={2} className="py-2 text-muted-foreground text-center">Sem ingredientes cadastrados</td></tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Montagem */}
          {sheet.assembly_steps?.length > 0 && (
            <Card className="print:shadow-none print:border print:border-black/30 print-avoid-break">
              <CardContent className="p-6 print:p-3">
                <h2 className="font-heading text-lg font-bold mb-4 print:mb-2 print:text-base">Passo a Passo de Montagem</h2>
                <ol className="space-y-2 print:text-xs">
                  {sheet.assembly_steps.map((step, idx) => (
                    <li key={idx} className="flex gap-3">
                      <span className="font-bold text-primary print:text-black shrink-0">{idx + 1}.</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          )}

          {/* Observações */}
          {sheet.notes && (
            <Card className="print:shadow-none print:border print:border-black/30 print-avoid-break">
              <CardContent className="p-6 print:p-3">
                <h2 className="font-heading text-lg font-bold mb-2 print:text-base">Observacoes</h2>
                <p className="text-muted-foreground whitespace-pre-wrap print:text-black print:text-xs">{sheet.notes}</p>
              </CardContent>
            </Card>
          )}

          {/* Rodape de impressao */}
          <div className="hidden print:block text-center text-[10px] text-muted-foreground border-t border-black/30 pt-2 mt-4">
            Gestor Resto - Ficha Tecnica gerada em {today}
          </div>
        </div>
      </div>
    </Layout>
  );
}
