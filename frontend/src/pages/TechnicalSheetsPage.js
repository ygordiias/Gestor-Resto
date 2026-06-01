import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import Layout from '../components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import { Eye, Pencil, Printer, Search, Plus } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function TechnicalSheetsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sheets, setSheets] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const canEdit = ['superadmin', 'admin'].includes(user?.role);

  useEffect(() => {
    const token = localStorage.getItem('token');
    fetch(`${API}/api/technical-sheets`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(setSheets)
      .catch(() => toast.error('Erro ao carregar fichas'))
      .finally(() => setLoading(false));
  }, []);

  const filtered = sheets.filter(s =>
    s.product_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Layout title="Fichas Tecnicas">
      <div className="space-y-4" data-testid="technical-sheets-page">
        <div className="flex flex-col sm:flex-row gap-3 justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar ficha tecnica..."
              className="pl-9"
              value={search}
              onChange={e => setSearch(e.target.value)}
              data-testid="search-sheets"
            />
          </div>
          {canEdit && (
            <Button onClick={() => navigate('/technical-sheets/new')} data-testid="new-sheet-btn">
              <Plus className="h-4 w-4 mr-2" /> Nova Ficha
            </Button>
          )}
        </div>

        {loading ? (
          <p className="text-center py-12 text-muted-foreground">Carregando...</p>
        ) : filtered.length === 0 ? (
          <p className="text-center py-12 text-muted-foreground">
            {search ? 'Nenhuma ficha encontrada' : 'Nenhuma ficha tecnica cadastrada'}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map(sheet => (
              <Card key={sheet.id} className="overflow-hidden" data-testid={`sheet-${sheet.id}`}>
                <div className="h-40 bg-muted flex items-center justify-center overflow-hidden">
                  {sheet.image_url ? (
                    <img src={sheet.image_url} alt={sheet.product_name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-4xl">📋</span>
                  )}
                </div>
                <CardContent className="p-4">
                  <h3 className="font-heading font-bold text-lg mb-1">{sheet.product_name}</h3>
                  <p className="text-sm text-muted-foreground mb-3">
                    {sheet.ingredients?.length || 0} ingredientes · {sheet.assembly_steps?.length || 0} passos
                  </p>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => navigate(`/technical-sheets/${sheet.id}`)} data-testid={`view-${sheet.id}`}>
                      <Eye className="h-4 w-4 mr-1" /> Ver
                    </Button>
                    {canEdit && (
                      <Button size="sm" variant="outline" onClick={() => navigate(`/technical-sheets/${sheet.id}/edit`)} data-testid={`edit-${sheet.id}`}>
                        <Pencil className="h-4 w-4 mr-1" /> Editar
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => navigate(`/technical-sheets/${sheet.id}?print=1`)} data-testid={`print-${sheet.id}`}>
                      <Printer className="h-4 w-4 mr-1" /> Imprimir
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
