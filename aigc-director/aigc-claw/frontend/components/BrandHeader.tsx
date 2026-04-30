'use client';

import Link from 'next/link';

export default function BrandHeader() {
  return (
    <header className="min-h-14 bg-white border-b border-gray-200 flex items-center px-4 flex-shrink-0 z-10 min-w-0">
      <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition-opacity flex-shrink-0">
        <img
          src="/logo.jpg"
          alt="Logo"
          className="w-8 h-8 rounded-lg object-contain"
        />
        <span className="font-bold text-sm text-gray-800 tracking-tight">
          AIGC-Claw
        </span>
      </Link>
    </header>
  );
}
