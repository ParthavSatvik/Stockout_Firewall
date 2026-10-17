import { useQuery } from "@tanstack/react-query";
import { useT } from "../lib/i18n";
import { WhatsAppAlertsCard } from "../components/WhatsAppAlertsCard";
import { Link } from "react-router-dom";
import {
  IndianRupee, TrendingUp, Clock, ShieldCheck, RotateCcw, AlertTriangle, AlertCircle,
  Info, ArrowRight, Radar, LifeBuoy, Wallet, TrendingDown, LineChart, Repeat, Recycle,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { ErrorState, SkeletonCard } from "../components/ui/state";
import { InfoHint } from "../components/ui/tooltip";
import { api } from "../lib/api";
import { formatINR } from "../lib/format";
import type { Order } from "../lib/types";

interface ActionFeedItem {
  severity: "info" | "warning" | "critical";
  message: string;
  order_id: string | null;
}
interface DashboardSummary {
  total_spend: number;
  estimated_savings: number;
  savings_basis: string;
  orders_in_progress: number;
  orders_awaiting_confirmation: number;
  shortage_alert_count: number;
  avg_supplier_reliability: number | null;
  recent_recovery_events: number;
  action_feed: ActionFeedItem[];
}

const SEVERITY_STYLE: Record<ActionFeedItem["severity"], { icon: typeof Info; className: string }> = {
  critical: { icon: AlertCircle, className: "text-rose-600 dark:text-rose-400" },
  warning: { icon: AlertTriangle, className: "text-amber-600 dark:text-amber-400" },
  info: { icon: Info, className: "text-sky-600 dark:text-sky-400" },
};

const INTELLIGENCE_LINKS = [
  { to: "/merchant/intelligence/stockout-radar", label: "Stockout Radar", icon: Radar },
  { to: "/merchant/intelligence/survival-mode", label: "Survival Mode", icon: LifeBuoy },
  { to: "/merchant/intelligence/cash-cycle", label: "Cash-Cycle Planner", icon: Wallet },
  { to: "/merchant/intelligence/margin-leak", label: "Margin Leak Detector", icon: TrendingDown },
  { to: "/merchant/intelligence/price-index", label: "Price Index", icon: LineChart },
  { to: "/merchant/intelligence/autopilot", label: "Autopilot", icon: Repeat },
  { to: "/merchant/intelligence/dead-stock", label: "Dead-Stock Exchange", icon: Recycle },
];

function KpiCard({
  icon: Icon, label, value, hint, accent,
}: { icon: typeof IndianRupee; label: string; value: string; hint?: string; accent?: string }) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between py-4">
        <div>
          <p className="flex items-center gap-1 text-xs font-medium text-slate-500 dark:text-slate-400">
            {label}
            {hint && <InfoHint text={hint} />}
          </p>
          <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">{value}</p>
        </div>
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${accent ?? "bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400"}`}>
          <Icon className="h-4.5 w-4.5" />
        </div>
      </CardContent>
    </Card>
  );
}

export function MerchantHomePage() {
  const { t } = useT();
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.get<DashboardSummary>("/api/intelligence/dashboard-summary"),
    refetchInterval: 15000,
  });
  const ordersQuery = useQuery({ queryKey: ["orders"], queryFn: () => api.get<Order[]>("/api/orders") });

  const recentOrders = (ordersQuery.data ?? [])
    .slice()
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{t("home.title")}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">{t("home.subtitle")}</p>
      </div>

      {summaryQuery.isLoading && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[1, 2, 3, 4, 5].map((i) => <SkeletonCard key={i} />)}
        </div>
      )}
      {summaryQuery.error && <ErrorState message="Could not load dashboard summary." />}

      {summaryQuery.data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <KpiCard
            icon={IndianRupee} label={t("home.spend")} value={formatINR(summaryQuery.data.total_spend)}
            hint="Sum of the selected plan's total cost across every confirmed or fulfilled order."
          />
          <KpiCard
            icon={TrendingUp} label={t("home.savings")} value={formatINR(summaryQuery.data.estimated_savings)}
            hint={summaryQuery.data.savings_basis} accent="bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
          />
          <KpiCard
            icon={Clock} label={t("home.inProgress")} value={String(summaryQuery.data.orders_in_progress)}
            hint="Draft, planned, awaiting confirmation, or currently replanning."
          />
          <KpiCard
            icon={ShieldCheck} label={t("home.reliability")}
            value={summaryQuery.data.avg_supplier_reliability != null ? `${Math.round(summaryQuery.data.avg_supplier_reliability * 100)}%` : t("home.noData")}
            hint="Average reliability score across suppliers you've actually used, weighted by real commitment history."
          />
          <KpiCard
            icon={RotateCcw} label={t("home.recovery")} value={String(summaryQuery.data.recent_recovery_events)}
            hint="Automatic replans triggered by a supplier rejection, short supply, or expired confirmation."
            accent="bg-signal-500/10 text-signal-600"
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("home.actionFeed")}</CardTitle>
            <CardDescription>{t("home.actionFeedDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            {summaryQuery.data?.action_feed.length === 0 && (
              <p className="py-6 text-center text-sm text-slate-400">{t("home.nothing")}</p>
            )}
            {summaryQuery.data?.action_feed.map((item, idx) => {
              const { icon: Icon, className } = SEVERITY_STYLE[item.severity];
              const body = (
                <div className="flex items-start gap-2.5 rounded-lg px-2 py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60">
                  <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${className}`} />
                  <p className="flex-1 text-sm text-slate-700 dark:text-slate-300">{item.message}</p>
                  {item.order_id && <ArrowRight className="h-3.5 w-3.5 mt-1 shrink-0 text-slate-300" />}
                </div>
              );
              return item.order_id ? (
                <Link key={idx} to={`/merchant/orders/${item.order_id}`}>{body}</Link>
              ) : (
                <div key={idx}>{body}</div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("home.modules")}</CardTitle>
            <CardDescription>{t("home.modulesDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-0.5">
            {INTELLIGENCE_LINKS.map((link) => {
              const Icon = link.icon;
              return (
                <Link
                  key={link.to} to={link.to}
                  className="flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800/60"
                >
                  <Icon className="h-4 w-4 text-brand-500" /> {link.label}
                  <ArrowRight className="ml-auto h-3.5 w-3.5 text-slate-300" />
                </Link>
              );
            })}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("home.recentOrders")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {recentOrders.length === 0 && <p className="py-4 text-center text-sm text-slate-400">{t("home.noOrders")}</p>}
          {recentOrders.map((order) => {
            const plan = order.plans.find((p) => p.is_selected);
            return (
              <Link
                key={order.id} to={`/merchant/orders/${order.id}`}
                className="flex items-center justify-between rounded-lg px-2 py-2 text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60"
              >
                <span className="text-slate-700 dark:text-slate-300">
                  #{order.id.slice(0, 8)} — {order.items.map((i) => i.product_name).join(", ")}
                </span>
                <span className="flex items-center gap-2">
                  {plan && <span className="font-medium text-slate-900 dark:text-slate-100">{formatINR(plan.total_cost)}</span>}
                  <Badge variant="default">{order.status.replace(/_/g, " ")}</Badge>
                </span>
              </Link>
            );
          })}
        </CardContent>
      </Card>
      <WhatsAppAlertsCard audience="merchant" />
    </div>
  );
}
