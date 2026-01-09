import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from './components/ui/sonner';
import { AuthProvider, useAuth } from './contexts/AuthContext';

// Pages
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import TablesPage from './pages/TablesPage';
import OrderPage from './pages/OrderPage';
import KitchenPage from './pages/KitchenPage';
import BarPage from './pages/BarPage';
import CashierPage from './pages/CashierPage';
import MenuPage from './pages/MenuPage';
import StockPage from './pages/StockPage';
import ReportsPage from './pages/ReportsPage';
import UsersPage from './pages/UsersPage';
import InvoicesPage from './pages/InvoicesPage';
import SettingsPage from './pages/SettingsPage';

// Protected Route Component
function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center parchment-bg">
        <div className="animate-pulse text-primary font-heading text-2xl">
          Carregando...
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    // Redirect to appropriate page based on role
    const roleRoutes = {
      admin: '/dashboard',
      waiter: '/tables',
      cashier: '/cashier',
      kitchen: '/kitchen',
      bar: '/bar',
    };
    return <Navigate to={roleRoutes[user.role] || '/login'} replace />;
  }

  return children;
}

function AppRoutes() {
  const { user } = useAuth();

  // Redirect authenticated users based on role
  const getDefaultRoute = () => {
    if (!user) return '/login';
    const roleRoutes = {
      admin: '/dashboard',
      waiter: '/tables',
      cashier: '/cashier',
      kitchen: '/kitchen',
      bar: '/bar',
    };
    return roleRoutes[user.role] || '/dashboard';
  };

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute allowedRoles={['admin']}>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/tables"
        element={
          <ProtectedRoute allowedRoles={['admin', 'waiter']}>
            <TablesPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/order/:tableId"
        element={
          <ProtectedRoute allowedRoles={['admin', 'waiter']}>
            <OrderPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/kitchen"
        element={
          <ProtectedRoute allowedRoles={['admin', 'kitchen']}>
            <KitchenPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/bar"
        element={
          <ProtectedRoute allowedRoles={['admin', 'bar']}>
            <BarPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/cashier"
        element={
          <ProtectedRoute allowedRoles={['admin', 'cashier']}>
            <CashierPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/menu"
        element={
          <ProtectedRoute allowedRoles={['admin']}>
            <MenuPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/stock"
        element={
          <ProtectedRoute allowedRoles={['admin']}>
            <StockPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/reports"
        element={
          <ProtectedRoute allowedRoles={['admin']}>
            <ReportsPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/users"
        element={
          <ProtectedRoute allowedRoles={['admin']}>
            <UsersPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/invoices"
        element={
          <ProtectedRoute allowedRoles={['admin', 'cashier']}>
            <InvoicesPage />
          </ProtectedRoute>
        }
      />
      
      <Route
        path="/settings"
        element={
          <ProtectedRoute allowedRoles={['admin']}>
            <SettingsPage />
          </ProtectedRoute>
        }
      />
      
      <Route path="/" element={<Navigate to={getDefaultRoute()} replace />} />
      <Route path="*" element={<Navigate to={getDefaultRoute()} replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
