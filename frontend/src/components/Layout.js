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
} from 'lucide-react';
import { Logo } from './Logo';

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
    { name: 'Mesas', href: '/tables', icon: UtensilsCrossed },
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const isMountedRef = useRef(true);

  const userNavigation = navigation[user?.role] || [];

  useEffect(() => {
    isMountedRef.current = true;

    // Listener para notificações de itens prontos (para garçons)
    const handleWaiterNotification = (data) => {
      if (!isMountedRef.current) return;
      
      // Só notifica garçons e admin
      if (user?.role === 'waiter' || user?.role === 'admin') {
        playNotificationSound();
        
        // Adiciona notificação
        const newNotification = {
          id: Date.now(),
          message: data.message,
          tableNumber: data.tableNumber,
          productName: data.productName,
          type: data.type,
          timestamp: new Date(),
        };
        
        setNotifications(prev => [newNotification, ...prev.slice(0, 4)]);
        
        toast.success(data.message, {
          icon: <Bell className="h-4 w-4" />,
          duration: 5000,
        });
      }
    };

    socketService.connect();
    socketService.on('waiter_notification', handleWaiterNotification);

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
        <div className="fixed inset-y-0 left-0 w-64 sm:w-72 bg-card border-r border-border animate-slide-in">
          <div className="flex items-center justify-between p-3 sm:p-4 border-b border-border">
            <Logo size="sm" />
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(false)}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
          <nav className="p-3 sm:p-4 space-y-1 sm:space-y-2">
            {userNavigation.map((item) => (
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
                <item.icon className="h-4 w-4 sm:h-5 sm:w-5" />
                <span className="font-medium">{item.name}</span>
              </Link>
            ))}
          </nav>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:z-40 lg:flex lg:w-64 xl:w-72 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-card border-r border-border px-4 xl:px-6 pb-4">
          <div className="flex h-14 xl:h-16 shrink-0 items-center border-b border-border -mx-4 xl:-mx-6 px-4 xl:px-6">
            <Logo size="md" />
          </div>
          <nav className="flex flex-1 flex-col">
            <ul className="flex flex-1 flex-col gap-y-1 xl:gap-y-2">
              {userNavigation.map((item) => (
                <li key={item.href}>
                  <Link
                    to={item.href}
                    className={cn(
                      'group flex gap-x-3 rounded-lg p-2 xl:p-3 text-sm font-medium transition-all duration-200',
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
          <div className="border-t border-border pt-4 -mx-4 xl:-mx-6 px-4 xl:px-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-9 w-9 xl:h-10 xl:w-10 rounded-full bg-primary/20 flex items-center justify-center">
                <span className="font-heading text-primary text-base xl:text-lg">
                  {user?.name?.charAt(0)}
                </span>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{user?.name}</p>
                <p className="text-xs text-muted-foreground">
                  {getRoleLabel(user?.role)}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              className="w-full justify-start gap-2 text-sm"
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
      <div className="lg:pl-64 xl:pl-72">
        {/* Top bar */}
        <div className="sticky top-0 z-30 flex h-14 sm:h-16 shrink-0 items-center gap-x-2 sm:gap-x-4 border-b border-border bg-card/95 backdrop-blur px-3 sm:px-4 lg:px-6 xl:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5 sm:h-6 sm:w-6" />
          </Button>
          <div className="flex flex-1 items-center gap-x-2 sm:gap-x-4 self-stretch">
            <h2 className="font-heading text-lg sm:text-xl md:text-2xl text-foreground truncate">
              {title}
            </h2>
          </div>
          
          {/* Notificações para garçons */}
          {(user?.role === 'waiter' || user?.role === 'admin') && notifications.length > 0 && (
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                className="relative"
                onClick={clearNotifications}
              >
                <Bell className="h-5 w-5" />
                <Badge className="absolute -top-1 -right-1 h-5 w-5 p-0 flex items-center justify-center text-xs">
                  {notifications.length}
                </Badge>
              </Button>
            </div>
          )}
          
          <div className="flex items-center gap-x-2 sm:gap-x-4 lg:hidden">
            <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-full bg-primary/20 flex items-center justify-center">
              <span className="font-heading text-primary text-xs sm:text-sm">
                {user?.name?.charAt(0)}
              </span>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="p-3 sm:p-4 lg:p-6 xl:p-8">{children}</main>
      </div>
    </div>
  );
}
