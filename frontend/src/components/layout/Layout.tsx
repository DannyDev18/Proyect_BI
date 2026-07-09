import { Outlet, Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore.ts';
import { useUIStore } from '../../store/uiStore.ts';
import { Sidebar } from './Sidebar.tsx';
import { Header } from './Header.tsx';
import { ProvenanceRail } from './ProvenanceRail.tsx';

export const Layout = () => {
  const { isAuthenticated } = useAuthStore();
  const { isSidebarOpen, closeSidebar } = useUIStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans relative">
      {/* Mobile overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-30 md:hidden" 
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar Navigation */}
      <Sidebar />
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        <Header />
        <ProvenanceRail />

        <main className="flex-1 overflow-y-auto p-4 md:p-8 relative z-10 w-full overflow-x-hidden">
          <div className="max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};
