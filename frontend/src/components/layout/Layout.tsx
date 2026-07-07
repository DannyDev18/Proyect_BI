import { Outlet, Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore.ts';
import { useUIStore } from '../../store/uiStore.ts';
import { Sidebar } from './Sidebar.tsx';
import { Header } from './Header.tsx';

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
        {/* Background glow effects for Dark Analytics aesthetic */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-600/10 rounded-full blur-[120px] pointer-events-none" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-slate-800/20 rounded-full blur-[150px] pointer-events-none" />
        
        <Header />
        
        <main className="flex-1 overflow-y-auto p-4 md:p-8 relative z-10 w-full overflow-x-hidden">
          <div className="max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};
