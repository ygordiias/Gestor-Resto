
import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { cn, getRoleLabel } from '../lib/utils';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import socketService, { playNotificationSound } from '../lib/socket';
import { toast } from 'sonner';

import {
  LayoutDashboard,
  UtensilsCrossed,
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
  Bell,
  ClipboardList,
  Calculator,
  Factory,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';

import { Logo } from './Logo';

const adminNavigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Mesas', href: '/tables', icon: UtensilsCrossed },
  { name: 'Cozinha', href: '/kitchen', icon: ChefHat },
  { name: 'Bar', href: '/bar', icon: Wine },
  { name: 'Caixa', href: '/cashier', icon: CreditCard },
  { name: 'Cardápio', href: '/menu', icon: BookOpen },
  { name: 'Estoque', href: '/stock', icon: Package },
  { name: 'Produção', href: '/production', icon: Factory },
  { name: 'CMV', href: '/cmv', icon: Calculator },
  { name: 'Relatórios', href: '/reports', icon: BarChart3 },
  { name: 'Usuários', href: '/users', icon: Users },
  { name: 'Notas Fiscais', href: '/invoices', icon: FileText },
  {
    name: 'Fichas Tecnicas',
    href: '/technical-sheets',
    icon: ClipboardList,
  },
  { name: 'Configurações', href: '/settings', icon: Settings },
];

const navigation = {
  superadmin: adminNavigation,
  admin: adminNavigation,

  waiter: [
    { name: 'Mesas', href: '/tables', icon: UtensilsCrossed },
    {
      name: 'Fichas Tecnicas',
      href: '/technical-sheets',
      icon: ClipboardList,
    },
  ],

  cashier: [
    { name: 'Caixa', href: '/cashier', icon: CreditCard },
    { name: 'Mesas', href: '/tables', icon: UtensilsCrossed },
    { name: 'Notas Fiscais', href: '/invoices', icon: FileText },
    {
      name: 'Fichas Tecnicas',
      href: '/technical-sheets',
      icon: ClipboardList,
    },
  ],

  kitchen: [
    { name: 'Cozinha', href: '/kitchen', icon: ChefHat },
    {
      name: 'Fichas Tecnicas',
      href: '/technical-sheets',
      icon: ClipboardList,
    },
  ],

  bar: [
    { name: 'Bar', href: '/bar', icon: Wine },
    {
      name: 'Fichas Tecnicas',
      href: '/technical-sheets',
      icon: ClipboardList,
    },
  ],
};

export default function Layout({ children, title }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Menu mobile
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Menu desktop retrátil
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('gestor-sidebar-collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const [notifications, setNotifications] = useState([]);
  const isMountedRef = useRef(true);

  const userNavigation = navigation[user?.role] || [];

  // Salva a preferência do menu no navegador
  useEffect(() => {
    try {
      localStorage.setItem(
        'gestor-sidebar-collapsed',
        String(sidebarCollapsed)
      );
    } catch {
      // O menu funciona mesmo se o armazenamento estiver indisponível
    }
  }, [sidebarCollapsed]);

  // Fecha o menu mobile quando muda de página
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Notificações em tempo real
  useEffect(() => {
    isMountedRef.current = true;

    const handleWaiterNotification = (data) => {
      if (!isMountedRef.current) return;

      if (
        user?.role === 'waiter' ||
        user?.role === 'admin' ||
        user?.role === 'superadmin'
      ) {
        playNotificationSound();

        const newNotification = {
          id: Date.now(),
          message: data.message,
          tableNumber: data.tableNumber,
          productName: data.productName,
          type: data.type,
          timestamp: new Date(),
        };

        setNotifications(prev => [
          newNotification,
          ...prev.slice(0, 4),
        ]);

        toast.success(data.message, {
          icon: <Bell className="h-4 w-4" />,
          duration: 5000,
        });
      }
    };

    socketService.connect();
    socketService.on(
      'waiter_notification',
      handleWaiterNotification
    );

    return () => {
      isMountedRef.current = false;
      socketService.off('waiter_notification');
    };
  }, [user?.role]);

  const handleLogout = () => {
    socketService.disconnect();
    logout();
    navigate('/login');
  };

  const clearNotifications = () => {
    setNotifications([]);
  };

  const toggleSidebar = () => {
    setSidebarCollapsed(previous => !previous);
  };

  return (
    <div className="min-h-screen parchment-bg">

      {/* ======================================
          MENU MOBILE
      ====================================== */}

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

        <div className="fixed inset-y-0 left-0 w-64 sm:w-72 bg-card border-r border-border animate-slide-in flex flex-col">

          <div className="flex items-center justify-between p-3 sm:p-4 border-b border-border shrink-0">
            <Logo size="sm" />

            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(false)}
              aria-label="Fechar menu"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>

          <nav className="p-3 sm:p-4 space-y-1 sm:space-y-2 flex-1 overflow-y-auto">

            {userNavigation.map(item => (
              <Link
                key={item.href}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  'flex items-center gap-3 px-3 sm:px-4 py-2 sm:py-3 rounded-lg transition-colors touch-target text-sm sm:text-base',
                  location.pathname === item.href
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                )}
              >
                <item.icon className="h-4 w-4 sm:h-5 sm:w-5 shrink-0" />

                <span className="font-medium">
                  {item.name}
                </span>
              </Link>
            ))}

          </nav>

          {/* Usuário mobile */}
          <div className="border-t border-border p-3 sm:p-4 shrink-0 bg-card">

            <div className="flex items-center gap-3 mb-3">

              <div className="h-9 w-9 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                <span className="font-heading text-primary text-base">
                  {user?.name?.charAt(0)}
                </span>
              </div>

              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">
                  {user?.name}
                </p>

                <p className="text-xs text-muted-foreground truncate">
                  {getRoleLabel(user?.role)}
                </p>
              </div>

            </div>

            <Button
              variant="outline"
              className="w-full justify-start gap-2 text-sm"
              onClick={() => {
                setSidebarOpen(false);
                handleLogout();
              }}
              data-testid="mobile-logout-btn"
            >
              <LogOut className="h-4 w-4" />
              Sair
            </Button>

          </div>
        </div>
      </div>

      {/* ======================================
          MENU DESKTOP RETRÁTIL
      ====================================== */}

      <div
        className={cn(
          'hidden lg:fixed lg:inset-y-0 lg:z-40 lg:flex lg:flex-col transition-[width] duration-300 ease-in-out',
          sidebarCollapsed
            ? 'lg:w-20'
            : 'lg:w-64 xl:w-72'
        )}
      >
        <div
          className={cn(
            'flex grow flex-col gap-y-5 overflow-y-auto bg-card border-r border-border pb-4 transition-all duration-300',
            sidebarCollapsed
              ? 'px-2'
              : 'px-4 xl:px-6'
          )}
        >

          {/* Logo e botão de recolher */}
          <div
            className={cn(
              'flex h-14 xl:h-16 shrink-0 items-center border-b border-border',
              sidebarCollapsed
                ? 'justify-center'
                : 'justify-between gap-2 -mx-4 xl:-mx-6 px-4 xl:px-6'
            )}
          >
            {!sidebarCollapsed && (
              <div className="min-w-0 overflow-hidden">
                <Logo size="md" />
              </div>
            )}

            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="shrink-0"
              title={
                sidebarCollapsed
                  ? 'Expandir menu'
                  : 'Recolher menu'
              }
              aria-label={
                sidebarCollapsed
                  ? 'Expandir menu'
                  : 'Recolher menu'
              }
              aria-expanded={!sidebarCollapsed}
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen className="h-5 w-5" />
              ) : (
                <PanelLeftClose className="h-5 w-5" />
              )}
            </Button>
          </div>

          {/* Navegação desktop */}
          <nav className="flex flex-1 flex-col">

            <ul className="flex flex-1 flex-col gap-y-1 xl:gap-y-2">

              {userNavigation.map(item => (
                <li key={item.href}>

                  <Link
                    to={item.href}
                    title={sidebarCollapsed ? item.name : undefined}
                    aria-label={item.name}
                    className={cn(
                      'group flex items-center rounded-lg text-sm font-medium transition-colors duration-200',
                      sidebarCollapsed
                        ? 'justify-center p-3'
                        : 'gap-x-3 p-2 xl:p-3',
                      location.pathname === item.href
                        ? 'bg-primary text-primary-foreground shadow-md'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                  >
                    <item.icon className="h-5 w-5 shrink-0" />

                    {!sidebarCollapsed && (
                      <span className="truncate">
                        {item.name}
                      </span>
                    )}
                  </Link>

                </li>
              ))}

            </ul>
          </nav>

          {/* Usuário desktop */}
          <div className="border-t border-border pt-4">

            <div
              className={cn(
                'flex items-center mb-4',
                sidebarCollapsed
                  ? 'justify-center'
                  : 'gap-3'
              )}
            >

              <div className="h-9 w-9 xl:h-10 xl:w-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                <span className="font-heading text-primary text-base xl:text-lg">
                  {user?.name?.charAt(0)}
                </span>
              </div>

              {!sidebarCollapsed && (
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {user?.name}
                  </p>

                  <p className="text-xs text-muted-foreground truncate">
                    {getRoleLabel(user?.role)}
                  </p>
                </div>
              )}

            </div>

            <Button
              variant="outline"
              className={cn(
                'w-full text-sm',
                sidebarCollapsed
                  ? 'justify-center px-2'
                  : 'justify-start gap-2'
              )}
              onClick={handleLogout}
              title={sidebarCollapsed ? 'Sair' : undefined}
              aria-label="Sair"
              data-testid="logout-btn"
            >
              <LogOut className="h-4 w-4 shrink-0" />

              {!sidebarCollapsed && 'Sair'}
            </Button>

          </div>
        </div>
      </div>

      {/* ======================================
          CONTEÚDO PRINCIPAL
      ====================================== */}

      <div
        className={cn(
          'transition-[padding] duration-300 ease-in-out',
          sidebarCollapsed
            ? 'lg:pl-20'
            : 'lg:pl-64 xl:pl-72'
        )}
      >

        {/* Barra superior */}
        <div className="sticky top-0 z-30 flex h-14 sm:h-16 shrink-0 items-center gap-x-2 sm:gap-x-4 border-b border-border bg-card/95 backdrop-blur px-3 sm:px-4 lg:px-6 xl:px-8">

          {/* Abrir menu mobile */}
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
            aria-label="Abrir menu"
          >
            <Menu className="h-5 w-5 sm:h-6 sm:w-6" />
          </Button>

          {/* Título da página */}
          <div className="flex flex-1 items-center gap-x-2 sm:gap-x-4 self-stretch min-w-0">

            <h2 className="font-heading text-lg sm:text-xl md:text-2xl text-foreground truncate">
              {title}
            </h2>

          </div>

          {/* Notificações */}
          {(
            user?.role === 'waiter' ||
            user?.role === 'admin' ||
            user?.role === 'superadmin'
          ) && notifications.length > 0 && (

            <div className="relative">

              <Button
                variant="ghost"
                size="icon"
                className="relative"
                onClick={clearNotifications}
                aria-label="Limpar notificações"
              >
                <Bell className="h-5 w-5" />

                <Badge className="absolute -top-1 -right-1 h-5 w-5 p-0 flex items-center justify-center text-xs">
                  {notifications.length}
                </Badge>
              </Button>

            </div>
          )}

          {/* Avatar mobile */}
          <div className="flex items-center gap-x-2 sm:gap-x-4 lg:hidden">

            <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-full bg-primary/20 flex items-center justify-center">

              <span className="font-heading text-primary text-xs sm:text-sm">
                {user?.name?.charAt(0)}
              </span>

            </div>
          </div>

        </div>

        {/* Conteúdo das páginas */}
        <main className="p-3 sm:p-4 lg:p-6 xl:p-8">
          {children}
        </main>

      </div>
    </div>
  );
}

