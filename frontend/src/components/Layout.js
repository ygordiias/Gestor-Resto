import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { cn, getRoleLabel } from '../lib/utils';
import { Button } from './ui/button';
import {
  LayoutDashboard,
  UtensilsCrossed,
  ClipboardList,
  ChefHat,
  Wine,
  CreditCard,
  Package,
  BarChart3,
  Users,
  FileText,
  Settings,
  LogOut,
  Menu,
  X,
  BookOpen,
} from 'lucide-react';

const navigation = {
  admin: [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Mesas', href: '/tables', icon: UtensilsCrossed },
    { name: 'Cozinha', href: '/kitchen', icon: ChefHat },
    { name: 'Bar', href: '/bar', icon: Wine },
    { name: 'Caixa', href: '/cashier', icon: CreditCard },
    { name: 'Cardápio', href: '/menu', icon: BookOpen },
    { name: 'Estoque', href: '/stock', icon: Package },
    { name: 'Relatórios', href: '/reports', icon: BarChart3 },
    { name: 'Usuários', href: '/users', icon: Users },
    { name: 'Notas Fiscais', href: '/invoices', icon: FileText },
    { name: 'Configurações', href: '/settings', icon: Settings },
  ],
  waiter: [
    { name: 'Mesas', href: '/tables', icon: UtensilsCrossed },
  ],
  cashier: [
    { name: 'Caixa', href: '/cashier', icon: CreditCard },
    { name: 'Notas Fiscais', href: '/invoices', icon: FileText },
  ],
  kitchen: [
    { name: 'Cozinha', href: '/kitchen', icon: ChefHat },
  ],
  bar: [
    { name: 'Bar', href: '/bar', icon: Wine },
  ],
};

export default function Layout({ children, title }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);

  const userNavigation = navigation[user?.role] || [];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen parchment-bg">
      {/* Mobile sidebar */}
      <div
        className={cn(
          'fixed inset-0 z-50 lg:hidden',
          sidebarOpen ? 'block' : 'hidden'
        )}
      >
        <div
          className="fixed inset-0 bg-black/50"
          onClick={() => setSidebarOpen(false)}
        />
        <div className="fixed inset-y-0 left-0 w-72 bg-card border-r border-border animate-slide-in">
          <div className="flex items-center justify-between p-4 border-b border-border">
            <h1 className="font-heading text-xl text-primary">Digital Codex</h1>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(false)}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
          <nav className="p-4 space-y-2">
            {userNavigation.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  'flex items-center gap-3 px-4 py-3 rounded-lg transition-colors touch-target',
                  location.pathname === item.href
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                )}
              >
                <item.icon className="h-5 w-5" />
                <span className="font-medium">{item.name}</span>
              </Link>
            ))}
          </nav>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-40 lg:flex lg:w-72 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-card border-r border-border px-6 pb-4">
          <div className="flex h-16 shrink-0 items-center border-b border-border -mx-6 px-6">
            <h1 className="font-heading text-2xl text-primary tracking-wide">
              Digital Codex
            </h1>
          </div>
          <nav className="flex flex-1 flex-col">
            <ul className="flex flex-1 flex-col gap-y-2">
              {userNavigation.map((item) => (
                <li key={item.href}>
                  <Link
                    to={item.href}
                    className={cn(
                      'group flex gap-x-3 rounded-lg p-3 text-sm font-medium transition-all duration-200',
                      location.pathname === item.href
                        ? 'bg-primary text-primary-foreground shadow-md'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                  >
                    <item.icon className="h-5 w-5 shrink-0" />
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="border-t border-border pt-4 -mx-6 px-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
                <span className="font-heading text-primary text-lg">
                  {user?.name?.charAt(0)}
                </span>
              </div>
              <div>
                <p className="text-sm font-medium">{user?.name}</p>
                <p className="text-xs text-muted-foreground">
                  {getRoleLabel(user?.role)}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              className="w-full justify-start gap-2"
              onClick={handleLogout}
              data-testid="logout-btn"
            >
              <LogOut className="h-4 w-4" />
              Sair
            </Button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-72">
        {/* Top bar */}
        <div className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-x-4 border-b border-border bg-card/95 backdrop-blur px-4 sm:gap-x-6 sm:px-6 lg:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </Button>
          <div className="flex flex-1 items-center gap-x-4 self-stretch">
            <h2 className="font-heading text-xl md:text-2xl text-foreground">
              {title}
            </h2>
          </div>
          <div className="flex items-center gap-x-4 lg:hidden">
            <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
              <span className="font-heading text-primary text-sm">
                {user?.name?.charAt(0)}
              </span>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
