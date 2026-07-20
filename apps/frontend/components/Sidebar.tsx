"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useThemeStore } from "@/lib/themeStore";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/terminal", label: "Trading Terminal" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/positions", label: "Positions" },
  { href: "/history", label: "Trade History" },
  { href: "/ai-predictions", label: "AI Predictions" },
  { href: "/scanner", label: "Market Scanner" },
  { href: "/risk", label: "Risk Dashboard" },
  { href: "/performance", label: "Performance" },
  { href: "/settings", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  const hydrate = useThemeStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-surface flex flex-col">
      <div className="px-5 py-5 border-b border-border flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold tracking-wide text-gray-100">THEMARKET AI</div>
          <div className="text-xs text-gray-500">Quant Forex</div>
        </div>
        <button
          onClick={toggle}
          title="Toggle theme"
          className="text-gray-400 hover:text-gray-100 text-sm rounded-md border border-border w-7 h-7 flex items-center justify-center"
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
      <nav className="flex-1 py-3">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "block px-5 py-2.5 text-sm transition-colors",
                active
                  ? "bg-accent/10 text-accent border-r-2 border-accent"
                  : "text-gray-400 hover:text-gray-100 hover:bg-white/5"
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
