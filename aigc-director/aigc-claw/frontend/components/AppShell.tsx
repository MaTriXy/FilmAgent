'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronLeft, ChevronRight, Clapperboard, Hexagon, Home, PanelLeftOpen, Repeat2, UserRound } from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';

const NAV_ITEMS = [
  { href: '/', label: 'AIGC-Claw', icon: Home },
  { href: '/sandbox', label: '临时工作台', icon: Hexagon },
  { href: '/pipelines/standard', label: '文艺短视频', icon: Clapperboard },
  { href: '/pipelines/action-transfer', label: '动作迁移', icon: Repeat2 },
  { href: '/pipelines/digital-human', label: '数字人口播', icon: UserRound },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 border-r border-gray-200 bg-white shadow-sm transition-all duration-300',
          open ? 'w-60' : 'w-0 border-r-0'
        )}
      >
        <div className={clsx('h-full overflow-hidden transition-opacity duration-200', open ? 'opacity-100' : 'opacity-0')}>
          <div className="flex h-16 items-center px-4 border-b border-gray-100">
            <div className="flex items-center gap-2 min-w-0">
              <PanelLeftOpen className="w-4 h-4 text-blue-500 flex-shrink-0" />
              <span className="text-sm font-semibold text-gray-800 truncate">AIGC-Claw</span>
            </div>
          </div>
          <nav className="p-3 space-y-1">
            {NAV_ITEMS.map(item => {
              const Icon = item.icon;
              const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                    active
                      ? 'bg-blue-50 text-blue-600'
                      : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
                  )}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>

      {open && (
        <button
          onClick={() => setOpen(false)}
          className="fixed left-60 top-1/2 z-50 h-14 w-7 -translate-y-1/2 rounded-r-xl border border-l-0 border-gray-200 bg-white text-gray-400 shadow-sm hover:w-9 hover:text-blue-600 hover:border-blue-200 hover:bg-blue-50 flex items-center justify-center transition-all"
          title="收起侧边栏"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      )}

      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed left-0 top-1/2 z-50 h-14 w-7 -translate-y-1/2 rounded-r-xl border border-l-0 border-gray-200 bg-white text-gray-400 shadow-sm hover:w-9 hover:text-blue-600 hover:border-blue-200 hover:bg-blue-50 flex items-center justify-center transition-all"
          title="打开侧边栏"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      )}

      <main className={clsx('min-h-screen min-w-0 overflow-x-hidden transition-[margin] duration-300', open ? 'ml-60' : 'ml-0')}>
        {children}
      </main>
    </div>
  );
}
