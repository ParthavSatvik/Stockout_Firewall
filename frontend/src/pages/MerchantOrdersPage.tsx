import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search, Plus } from "lucide-react";
import { Button } from "../components/ui/button";
import { StatusBadge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { EmptyState, ErrorState, SkeletonCard } from "../components/ui/state";
import { Input, Select } from "../components/ui/input";
import { api } from "../lib/api";
import { formatDate, formatINR } from "../lib/format";
import type { Order, OrderStatus } from "../lib/types";

const STATUS_OPTIONS: { value: OrderStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "planned", label: "Planned" },
  { value: "awaiting_confirmation", label: "Awaiting confirmation" },
  { value: "replanning", label: "Replanning" },
  { value: "confirmed", label: "Confirmed" },
  { value: "partially_fulfilled", label: "Partially fulfilled" },
  { value: "fulfilled", label: "Fulfilled" },
  { value: "infeasible", label: "Infeasible" },
];

export function MerchantOrdersPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["orders"],
    queryFn: () => api.get<Order[]>("/api/orders"),
  });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<OrderStatus | "all">("all");

  const filtered = useMemo(() => {
    if (!data) return [];
    return data
      .filter((o) => statusFilter === "all" || o.status === statusFilter)
      .filter((o) => {
        if (!search.trim()) return true;
        const haystack = `${o.id} ${o.items.map((i) => i.product_name).join(" ")}`.toLowerCase();
        return haystack.includes(search.trim().toLowerCase());
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [data, search, statusFilter]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Orders</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Every basket you've placed, and its live recovery status.</p>
        </div>
        <Link to="/merchant/new">
          <Button>
            <Plus className="h-4 w-4" /> New Order
          </Button>
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-48">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <Input className="pl-8" placeholder="Search by product or order id…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select className="w-56" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as OrderStatus | "all")}>
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && (
        <div className="grid gap-3">
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </div>
      )}
      {error && <ErrorState message="Could not load orders." />}
      {data && data.length === 0 && (
        <EmptyState title="No orders yet" hint="Create your first order to see supplier plans and live status." />
      )}
      {data && data.length > 0 && filtered.length === 0 && (
        <EmptyState title="No orders match your filters" hint="Try a different search term or status." />
      )}

      {filtered.length > 0 && (
        <div className="grid gap-3">
          {filtered.map((order) => {
            const selectedPlan = order.plans.find((p) => p.is_selected);
            return (
              <Link key={order.id} to={`/merchant/orders/${order.id}`}>
                <Card className="transition-all hover:border-brand-400 hover:shadow-md dark:hover:border-brand-600">
                  <CardHeader className="flex-row items-center justify-between space-y-0">
                    <CardTitle>
                      Order #{order.id.slice(0, 8)} · {order.items.length} item(s)
                    </CardTitle>
                    <StatusBadge status={order.status} />
                  </CardHeader>
                  <CardContent className="flex items-center justify-between text-sm text-slate-600 dark:text-slate-400">
                    <div>
                      <p>{order.items.map((i) => i.product_name).join(", ")}</p>
                      <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">{formatDate(order.created_at)}</p>
                    </div>
                    {selectedPlan && <span className="font-semibold text-slate-900 dark:text-slate-100">{formatINR(selectedPlan.total_cost)}</span>}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
