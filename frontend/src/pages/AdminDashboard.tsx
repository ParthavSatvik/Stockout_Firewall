import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Activity, AlertTriangle, RotateCcw, ShieldCheck, Tv } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { ErrorState, Spinner } from "../components/ui/state";
import { Tooltip } from "../components/ui/tooltip";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { AdminMetrics } from "../lib/types";

interface NetworkSupplier {
  id: string;
  business_name: string;
  city: string;
  latitude: number;
  longitude: number;
  is_active: boolean;
  reliability_score: number;
  reliability_confidence: string;
  sample_size: number;
  active_allocations: number;
}
interface NetworkMerchant {
  id: string;
  business_name: string;
  city: string;
  latitude: number;
  longitude: number;
}
interface NetworkEvent {
  id: string;
  event_type: string;
  created_at: string;
  supplier_name: string;
  product_name: string;
  allocation_id: string;
  order_id: string;
  triggered_replan: boolean;
}

const EVENT_VARIANT: Record<string, "default" | "success" | "warning" | "danger"> = {
  confirmed: "success", delivered: "success", dispatched: "default",
  rejected: "danger", short_supply: "warning", expired: "danger", disrupted: "warning",
};

function StatCard({ icon: Icon, label, value, accent }: { icon: typeof Activity; label: string; value: string | number; accent?: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between py-4">
        <div>
          <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
          <p className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{value}</p>
        </div>
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${accent ?? "bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400"}`}>
          <Icon className="h-4.5 w-4.5" />
        </div>
      </CardContent>
    </Card>
  );
}

function NetworkMap({ suppliers, merchants }: { suppliers: NetworkSupplier[]; merchants: NetworkMerchant[] }) {
  const points = useMemo(() => {
    const all = [...suppliers.map((s) => ({ lat: s.latitude, lon: s.longitude })), ...merchants.map((m) => ({ lat: m.latitude, lon: m.longitude }))];
    if (all.length === 0) return { project: (_lat: number, _lon: number) => ({ x: 150, y: 150 }) };
    const lats = all.map((p) => p.lat);
    const lons = all.map((p) => p.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const pad = 30;
    const w = 300, h = 300;
    const project = (lat: number, lon: number) => ({
      x: pad + (maxLon === minLon ? (w - 2 * pad) / 2 : ((lon - minLon) / (maxLon - minLon)) * (w - 2 * pad)),
      y: pad + (maxLat === minLat ? (h - 2 * pad) / 2 : (1 - (lat - minLat) / (maxLat - minLat)) * (h - 2 * pad)),
    });
    return { project };
  }, [suppliers, merchants]);

  return (
    <svg viewBox="0 0 300 300" className="h-80 w-full">
      <rect x={0} y={0} width={300} height={300} rx={12} className="fill-slate-50 dark:fill-slate-800/40" />
      {merchants.map((m) => {
        const { x, y } = points.project(m.latitude, m.longitude);
        return (
          <g key={m.id}>
            <rect x={x - 4} y={y - 4} width={8} height={8} rx={2} className="fill-slate-400 dark:fill-slate-500" />
            <text x={x + 7} y={y + 3} className="fill-slate-500 text-[8px] dark:fill-slate-400">{m.business_name.split(" ")[0]}</text>
          </g>
        );
      })}
      {suppliers.map((s) => {
        const { x, y } = points.project(s.latitude, s.longitude);
        const color = !s.is_active ? "fill-slate-400" : s.reliability_score >= 0.75 ? "fill-emerald-500" : s.reliability_score >= 0.5 ? "fill-amber-500" : "fill-rose-500";
        const radius = 5 + Math.min(6, s.active_allocations);
        return (
          <g key={s.id}>
            {s.active_allocations > 0 && <circle cx={x} cy={y} r={radius + 3} className={`${color} opacity-20`} />}
            <circle cx={x} cy={y} r={radius} className={color} />
            <text x={x + radius + 2} y={y + 3} className="fill-slate-700 text-[8px] font-medium dark:fill-slate-200">{s.business_name.split(" ")[0]}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function AdminDashboard() {
  const metricsQuery = useQuery({
    queryKey: ["admin-metrics"],
    queryFn: () => api.get<AdminMetrics>("/api/admin/metrics"),
    refetchInterval: 10000,
  });
  const suppliersQuery = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: () => api.get<NetworkSupplier[]>("/api/admin/suppliers"),
    refetchInterval: 10000,
  });
  const merchantsQuery = useQuery({ queryKey: ["admin-merchants"], queryFn: () => api.get<NetworkMerchant[]>("/api/admin/merchants") });
  const eventsQuery = useQuery({
    queryKey: ["admin-events"],
    queryFn: () => api.get<NetworkEvent[]>("/api/admin/events?limit=20"),
    refetchInterval: 8000,
  });

  if (metricsQuery.isLoading) return <Spinner label="Loading control tower…" />;
  if (metricsQuery.error || !metricsQuery.data) return <ErrorState message="Could not load metrics." />;

  const data = metricsQuery.data;
  const chartData = Object.entries(data.orders_by_status).map(([status, count]) => ({ status, count }));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Tv className="h-5 w-5 text-brand-500" /> Control Tower
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Network-wide procurement health, live supplier status, and the real audit trail behind every replan.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <StatCard icon={Activity} label="Total orders" value={data.total_orders} />
        <StatCard icon={ShieldCheck} label="Fulfilled or partial" value={data.fulfilled_or_partial} accent="bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400" />
        <StatCard icon={RotateCcw} label="Replans (failovers)" value={data.total_replans} accent="bg-signal-500/10 text-signal-600" />
        <StatCard icon={ShieldCheck} label="Suppliers" value={data.supplier_count} />
        <StatCard
          icon={ShieldCheck} label="Avg. reliability"
          value={data.average_supplier_reliability != null ? `${Math.round(data.average_supplier_reliability * 100)}%` : "—"}
        />
        <StatCard icon={AlertTriangle} label="Infeasible plans" value={data.infeasible_plans} accent="bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Supplier network</CardTitle>
            <CardDescription>
              Schematic layout from real supplier/merchant coordinates (not a geographic map). Dot size = active
              allocations, color = reliability (green ≥75%, amber ≥50%, red below, grey inactive).
            </CardDescription>
          </CardHeader>
          <CardContent>
            {suppliersQuery.data && merchantsQuery.data ? (
              <NetworkMap suppliers={suppliersQuery.data} merchants={merchantsQuery.data ?? []} />
            ) : (
              <Spinner />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Event timeline</CardTitle>
            <CardDescription>The real SupplierEvent log driving every replan.</CardDescription>
          </CardHeader>
          <CardContent className="max-h-80 space-y-2 overflow-y-auto">
            {eventsQuery.data?.length === 0 && <p className="text-sm text-slate-400">No events yet.</p>}
            {eventsQuery.data?.map((ev) => (
              <div key={ev.id} className="flex items-start gap-2 text-xs">
                <Badge variant={EVENT_VARIANT[ev.event_type] ?? "default"}>{ev.event_type.replace(/_/g, " ")}</Badge>
                <div className="flex-1">
                  <p className="text-slate-700 dark:text-slate-300">{ev.supplier_name} — {ev.product_name}</p>
                  <p className="text-slate-400 dark:text-slate-500">{timeAgo(ev.created_at)}{ev.triggered_replan && " · triggered a replan"}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Orders by status</CardTitle>
        </CardHeader>
        <CardContent style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
              <XAxis dataKey="status" fontSize={12} />
              <YAxis allowDecimals={false} fontSize={12} />
              <RTooltip />
              <Bar dataKey="count" fill="var(--color-brand-600)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {suppliersQuery.data && (
        <Card>
          <CardHeader>
            <CardTitle>Supplier availability & reliability</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  <th className="py-2">Supplier</th>
                  <th className="py-2">City</th>
                  <th className="py-2">Status</th>
                  <th className="py-2">Reliability</th>
                  <th className="py-2">Active allocations</th>
                </tr>
              </thead>
              <tbody>
                {suppliersQuery.data.map((s) => (
                  <tr key={s.id} className="border-b border-slate-50 dark:border-slate-800/60">
                    <td className="py-2">{s.business_name}</td>
                    <td className="py-2">{s.city}</td>
                    <td className="py-2"><Badge variant={s.is_active ? "success" : "default"}>{s.is_active ? "active" : "inactive"}</Badge></td>
                    <td className="py-2">
                      <Tooltip content={`${s.sample_size} commitments on record`}>
                        <span className="cursor-help underline decoration-dotted">
                          {Math.round(s.reliability_score * 100)}% ({s.reliability_confidence})
                        </span>
                      </Tooltip>
                    </td>
                    <td className="py-2">{s.active_allocations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
