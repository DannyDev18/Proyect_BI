import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore } from '../store/authStore.ts';
import { canAccess, type RouteKey } from '../constants/permissions.ts';

// We will create these pages next
import { Layout } from '../components/layout/Layout.tsx';
import { Login } from '../pages/Login.tsx';
import { DashboardAdmin } from '../pages/DashboardAdmin.tsx';
import { DashboardGerencia } from '../pages/DashboardGerencia.tsx';
import { DashboardMetas } from '../pages/DashboardMetas.tsx';
import { DashboardBodega } from '../pages/DashboardBodega.tsx';
import { DashboardVentas } from '../pages/DashboardVentas.tsx';
import { DashboardMetasVendedor } from '../pages/DashboardMetasVendedor.tsx';
import { AccessDenied } from '../pages/AccessDenied.tsx';
import { Settings } from '../pages/Settings.tsx';
import { NotFound } from '../pages/NotFound.tsx';
import { UsersManagement } from '../pages/UsersManagement.tsx';

interface ProtectedRouteProps {
  children: ReactNode;
  routeKey: RouteKey;
}

const ProtectedRoute = ({ children, routeKey }: ProtectedRouteProps) => {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  if (!canAccess(user.role, routeKey)) {
    return <Navigate to="/access-denied" replace />;
  }

  return <>{children}</>;
};

// Route director based on role
const RoleBasedRedirect = () => {
  const { user, isAuthenticated } = useAuthStore();

  if (!isAuthenticated || !user) return <Navigate to="/login" replace />;

  switch (user.role) {
    case 'administrador': return <Navigate to="/admin" replace />;
    case 'gerencia': return <Navigate to="/gerencia" replace />;
    case 'bodega': return <Navigate to="/bodega" replace />;
    case 'ventas': return <Navigate to="/ventas" replace />;
    default: return <Navigate to="/login" replace />;
  }
};

export const AppRouter = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        
        <Route path="/" element={<Layout />}>
          <Route index element={<RoleBasedRedirect />} />
          
          <Route path="admin" element={
            <ProtectedRoute routeKey="admin">
              <DashboardAdmin />
            </ProtectedRoute>
          } />

          <Route path="users" element={
            <ProtectedRoute routeKey="users">
              <UsersManagement />
            </ProtectedRoute>
          } />

          <Route path="gerencia">
            <Route index element={
              <ProtectedRoute routeKey="gerencia">
                <DashboardGerencia />
              </ProtectedRoute>
            } />
            <Route path="metas" element={
              <ProtectedRoute routeKey="gerencia.metas">
                <DashboardMetas />
              </ProtectedRoute>
            } />
          </Route>

          <Route path="bodega" element={
            <ProtectedRoute routeKey="bodega">
              <DashboardBodega />
            </ProtectedRoute>
          } />

          <Route path="ventas">
            <Route index element={
              <ProtectedRoute routeKey="ventas">
                <DashboardVentas />
              </ProtectedRoute>
            } />
            <Route path="metas" element={
              <ProtectedRoute routeKey="ventas.metas">
                <DashboardMetasVendedor />
              </ProtectedRoute>
            } />
          </Route>

          <Route path="access-denied" element={<AccessDenied />} />

          <Route path="settings" element={
            <ProtectedRoute routeKey="settings">
              <Settings />
            </ProtectedRoute>
          } />
        </Route>
        
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
};
