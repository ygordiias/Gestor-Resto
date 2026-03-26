import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { setupAPI } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Logo } from '../components/Logo';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const { login, user } = useAuth();
  const navigate = useNavigate();

  // Redirect if already logged in
  React.useEffect(() => {
    if (user) {
      const roleRoutes = {
        admin: '/dashboard',
        waiter: '/tables',
        cashier: '/cashier',
        kitchen: '/kitchen',
        bar: '/bar',
      };
      navigate(roleRoutes[user.role] || '/dashboard');
    }
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const userData = await login(email, password);
      toast.success(`Bem-vindo, ${userData.name}!`);
      
      const roleRoutes = {
        admin: '/dashboard',
        waiter: '/tables',
        cashier: '/cashier',
        kitchen: '/kitchen',
        bar: '/bar',
      };
      navigate(roleRoutes[userData.role] || '/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao fazer login');
    } finally {
      setLoading(false);
    }
  };

  const handleSeedDatabase = async () => {
    setSeeding(true);
    try {
      await setupAPI.seed();
      toast.success('Banco de dados inicializado com sucesso!');
      toast.info('Use admin@digitalcodex.com / admin123 para entrar');
    } catch (error) {
      if (error.response?.data?.message === 'Database already seeded') {
        toast.info('Banco de dados já foi inicializado');
      } else {
        toast.error('Erro ao inicializar banco de dados');
      }
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="min-h-screen parchment-bg flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-8 animate-fade-in">
        {/* Logo */}
        <div className="text-center flex flex-col items-center">
          <Logo size="xl" className="mb-4" />
          <p className="text-muted-foreground mt-2 text-base">
            Sistema de Gestão para Restaurante
          </p>
        </div>

        {/* Login Card */}
        <Card className="border-2 border-border shadow-lg">
          <CardHeader className="space-y-1">
            <CardTitle className="font-heading text-2xl text-center">
              Entrar
            </CardTitle>
            <CardDescription className="text-center">
              Digite suas credenciais para acessar o sistema
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">E-mail</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="seu@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  data-testid="login-email"
                  className="border-2 focus:border-primary"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Senha</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  data-testid="login-password"
                  className="border-2 focus:border-primary"
                />
              </div>
              <Button
                type="submit"
                className="w-full font-heading uppercase tracking-widest"
                disabled={loading}
                data-testid="login-submit"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Entrando...
                  </>
                ) : (
                  'Entrar'
                )}
              </Button>
            </form>

            <div className="mt-6 pt-6 border-t border-border">
              <p className="text-sm text-muted-foreground text-center mb-4">
                Primeira vez? Inicialize o banco de dados com dados de exemplo.
              </p>
              <Button
                variant="outline"
                className="w-full"
                onClick={handleSeedDatabase}
                disabled={seeding}
                data-testid="seed-database-btn"
              >
                {seeding ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Inicializando...
                  </>
                ) : (
                  'Inicializar Banco de Dados'
                )}
              </Button>
            </div>

            <div className="mt-4 p-4 bg-muted rounded-lg">
              <p className="text-xs text-muted-foreground text-center font-medium mb-2">
                Credenciais de teste:
              </p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="text-muted-foreground">Admin:</div>
                <div>admin@digitalcodex.com / admin123</div>
                <div className="text-muted-foreground">Garçom:</div>
                <div>garcom@digitalcodex.com / garcom123</div>
                <div className="text-muted-foreground">Caixa:</div>
                <div>caixa@digitalcodex.com / caixa123</div>
                <div className="text-muted-foreground">Cozinha:</div>
                <div>cozinha@digitalcodex.com / cozinha123</div>
                <div className="text-muted-foreground">Bar:</div>
                <div>bar@digitalcodex.com / bar123</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
