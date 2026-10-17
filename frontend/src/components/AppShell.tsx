import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import {
  LayoutDashboard, ShoppingCart, PlusCircle, Radar, LifeBuoy, Wallet, TrendingDown,
  LineChart, Repeat, Recycle, Inbox, Boxes, ShieldCheck, Tv, LogOut, Moon, Sun, Menu,
  Compass, Truck, Workflow, ScrollText, BadgeCheck, Languages,
} from "lucide-react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { LANGUAGES, useT, type Lang, type TKey } from "../lib/i18n";
import { useTheme } from "../lib/theme";
import type { HealthResponse } from "../lib/types";
import { cn } from "../lib/utils";

function DemoModeBanner() {
  const { data } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/api/health"),
    staleTime: 60_000,
  });
  const { t } = useT();
  if (!data?.demo_mode) return null;

  const missing = [
    !data.sarvam_configured && "Sarvam AI",
    !data.paytm_configured && "Paytm",
    !data.google_maps_configured && "Google Routes",
    !data.supabase_configured && "Supabase",
  ].filter(Boolean) as string[];

  return (
    <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300">
      <strong>{t("shell.demoMode")}</strong> — {t("shell.demoText")}
      {missing.length > 0 && <> {t("shell.notConfigured")} {missing.join(", ")}.</>}
    </div>
  );
}

export function RequireAuth({ children, allowedRoles }: { children: ReactNode; allowedRoles?: string[] }) {
  const { isAuthenticated, role } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  if (allowedRoles && role && !allowedRoles.includes(role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

interface NavItem {
  to: string;
  label: TKey;
  icon: typeof LayoutDashboard;
}
interface NavGroup {
  label: TKey;
  items: NavItem[];
}

const MERCHANT_NAV: NavGroup[] = [
  {
    label: "nav.procurement",
    items: [
      { to: "/merchant", label: "nav.commandCenter", icon: LayoutDashboard },
      { to: "/merchant/orders", label: "nav.orders", icon: ShoppingCart },
      { to: "/merchant/new", label: "nav.newOrder", icon: PlusCircle },
    ],
  },
  {
    label: "nav.intelligence",
    items: [
      { to: "/merchant/intelligence/stockout-radar", label: "nav.stockoutRadar", icon: Radar },
      { to: "/merchant/intelligence/survival-mode", label: "nav.survivalMode", icon: LifeBuoy },
      { to: "/merchant/intelligence/cash-cycle", label: "nav.cashCycle", icon: Wallet },
      { to: "/merchant/intelligence/margin-leak", label: "nav.marginLeak", icon: TrendingDown },
      { to: "/merchant/intelligence/price-index", label: "nav.priceIndex", icon: LineChart },
      { to: "/merchant/intelligence/autopilot", label: "nav.autopilot", icon: Repeat },
      { to: "/merchant/intelligence/dead-stock", label: "nav.deadStock", icon: Recycle },
    ],
  },
];

const SUPPLIER_NAV: NavGroup[] = [
  {
    label: "nav.commitments",
    items: [
      { to: "/supplier", label: "nav.copilot", icon: Compass },
      { to: "/supplier/requests", label: "nav.requests", icon: Inbox },
      { to: "/supplier/dispatch", label: "nav.dispatch", icon: Truck },
      { to: "/supplier/relay", label: "nav.relay", icon: Workflow },
    ],
  },
  {
    label: "nav.stockTrust",
    items: [
      { to: "/supplier/ledger", label: "nav.ledger", icon: ScrollText },
      { to: "/supplier/passport", label: "nav.passport", icon: BadgeCheck },
      { to: "/supplier/inventory", label: "nav.inventory", icon: Boxes },
      { to: "/supplier/dead-stock", label: "nav.deadStock", icon: Recycle },
    ],
  },
];

const ADMIN_NAV: NavGroup[] = [
  { label: "nav.operations", items: [{ to: "/admin", label: "nav.controlTower", icon: Tv }] },
];

function navForRole(role: string | null): NavGroup[] {
  if (role === "merchant") return MERCHANT_NAV;
  if (role === "supplier") return SUPPLIER_NAV;
  if (role === "admin") return ADMIN_NAV;
  return [];
}

export function LanguageSelect() {
  const { lang, setLang, t } = useT();
  return (
    <label className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
      <Languages className="h-4 w-4 shrink-0" aria-hidden />
      <span className="sr-only">{t("shell.language")}</span>
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label={t("shell.language")}
        className="h-8 w-full rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
        {LANGUAGES.map((l) => <option key={l.code} value={l.code} lang={l.code}>{l.label}</option>)}
      </select>
    </label>
  );
}

function BrandMark() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
        <ShieldCheck className="h-4.5 w-4.5" />
      </div>
      <span className="text-sm font-semibold tracking-tight text-slate-900 dark:text-white">Stockout Firewall</span>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { role, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const groups = navForRole(role);
  const { t } = useT();

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4">
        <BrandMark />
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-2 space-y-5">
        {groups.map((group) => (
          <div key={group.label}>
            <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-600">
              {t(group.label)}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = location.pathname === item.to;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={onNavigate}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/70",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {t(item.label)}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="space-y-2 border-t border-slate-200 p-3 dark:border-slate-800">
        <LanguageSelect />
        <div className="flex items-center gap-2">
          <button
            onClick={toggleTheme}
            className="flex flex-1 items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/70"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {theme === "dark" ? t("shell.lightMode") : t("shell.darkMode")}
          </button>
          <button
            onClick={logout}
            title={t("shell.logout")}
            aria-label={t("shell.logout")}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800/70"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-50 dark:bg-slate-950">
        <DemoModeBanner />
        <div className="flex justify-end px-4 pt-3"><div className="w-40"><LanguageSelect /></div></div>
        <div className="flex flex-1 items-center justify-center px-4">{children}</div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col bg-slate-50 dark:bg-slate-950">
      <DemoModeBanner />
      <div className="flex flex-1 overflow-hidden">
        <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 md:block">
          <SidebarContent />
        </aside>

        {mobileOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} />
            <aside className="absolute left-0 top-0 h-full w-64 bg-white shadow-xl dark:bg-slate-900">
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900 md:hidden">
            <button onClick={() => setMobileOpen(true)} aria-label="Menu" aria-expanded={mobileOpen} className="text-slate-600 dark:text-slate-300">
              <Menu className="h-5 w-5" aria-hidden />
            </button>
            <BrandMark />
          </header>
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
