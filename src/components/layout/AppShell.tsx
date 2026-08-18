'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useSidebar, useStore } from '@/lib/store';
import { theme } from '@/styles/theme';
import Sidebar from './Sidebar';
import Header from './Header';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { collapsed } = useSidebar();
  const [isDesktop, setIsDesktop] = useState(false);

  // Detect desktop viewport
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    setIsDesktop(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Close mobile sidebar on route change
  useEffect(() => {
    useStore.getState().sidebar.setMobileOpen(false);
  }, [pathname]);

  // Skip shell for login page
  if (pathname === '/login') {
    return <>{children}</>;
  }

  const sidebarWidth = collapsed ? theme.sidebar.collapsedWidth : theme.sidebar.expandedWidth;

  return (
    <div className="min-h-screen" style={{ backgroundColor: theme.colors.background }}>
      <Sidebar />

      {/* Main content area — offset by sidebar width on desktop only */}
      <div
        className="flex flex-col min-h-screen"
        style={{ marginLeft: isDesktop ? sidebarWidth : 0 }}
      >
        <Header />

        <main className="flex-1 p-4 md:p-6">
          {children}
        </main>

        {/* Footer */}
        <footer
          className="mt-auto px-4 py-3 text-center text-xs border-t"
          style={{
            backgroundColor: theme.colors.surface,
            borderColor: theme.colors.border,
            color: theme.colors.textDisabled,
          }}
        >
          UltraBot Web Trading Terminal · Built with Next.js
        </footer>
      </div>
    </div>
  );
}
