import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuthStore, type Role } from '../store/authStore.ts';

// We will create these pages next
import { Layout } from '../components/layout/Layout.tsx';
import { Login } from '../pages/Login.tsx';
import { DashboardAdmin } from '../pages/DashboardAdmin.tsx';
import { DashboardGerencia } from '../pages/DashboardGerencia.tsx';
import { DashboardMetas } from '../pages/DashboardMetas.tsx';
import { DashboardBodega } from '../pages/DashboardBodega.tsx';
import { DashboardVentas } from '../pages/DashboardVentas.tsx';
import { AccessDenied } from '../pages/AccessDenied.tsx';
import { Settings } from '../pages/Settings.tsx';
import { NotFound } from '../pages/NotFound.tsx';
import { UsersManagement } from '../pages/UsersManagement.tsx';

interface ProtectedRouteProps {
  children: ReactNode;
  allowedRoles?: Role[];
}

const ProtectedRoute = ({ children, allowedRoles }: ProtectedRouteProps) => {
  const { isAuthenticated, user } = useAuthStore();

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
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
            <ProtectedRoute allowedRoles={['administrador']}>
              <DashboardAdmin />
            </ProtectedRoute>
          } />
          
          <Route path="users" element={
            <ProtectedRoute allowedRoles={['administrador']}>
              <UsersManagement />
            </ProtectedRoute>
          } />
          
          <Route path="gerencia">
            <Route index element={
              <ProtectedRoute allowedRoles={['administrador', 'gerencia']}>
                <DashboardGerencia />
              </ProtectedRoute>
            } />
            <Route path="metas" element={
              <ProtectedRoute allowedRoles={['administrador', 'gerencia']}>
                <DashboardMetas />
              </ProtectedRoute>
            } />
          </Route>

          <Route path="bodega" element={
            <ProtectedRoute allowedRoles={['administrador', 'gerencia', 'bodega']}>
              <DashboardBodega />
            </ProtectedRoute>
          } />

          <Route path="ventas" element={
            <ProtectedRoute allowedRoles={['administrador', 'gerencia', 'ventas']}>
              <DashboardVentas />
            </ProtectedRoute>
          } />
          
          <Route path="access-denied" element={<AccessDenied />} />

          <Route path="settings" element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          } />
        </Route>
        
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
};
