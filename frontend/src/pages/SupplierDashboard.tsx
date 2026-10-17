import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Clock, Inbox, PackageCheck, Truck } from "lucide-react";
import { Badge, StatusBadge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { ConfirmDialog } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../components/ui/state";
import { useToast } from "../components/ui/toast";
import { api } from "../lib/api";
import { formatINR } from "../lib/format";
import type { Allocation } from "../lib/types";

interface ReliabilitySummary {
  reliability_score: number;
  confidence: string;
  sample_size: number;
  total_commitments: number;
  fulfilled_count: number;
  short_supply_count: number;
  rejected_count: number;
  expired_count: number;
}

function deadlineUrgency(expiresAt: string | null): { label: string; variant: "default" | "warning" | "danger" } {
  if (!expiresAt) return { label: "no deadline", variant: "default" };
  const hoursLeft = (new Date(expiresAt).getTime() - Date.now()) / 3_600_000;
  if (hoursLeft <= 0) return { label: "overdue", variant: "danger" };
  if (hoursLeft <= 2) return { label: `${Math.round(hoursLeft)}h left`, variant: "danger" };
  if (hoursLeft <= 6) return { label: `${Math.round(hoursLeft)}h left`, variant: "warning" };
  return { label: `${Math.round(hoursLeft)}h left`, variant: "default" };
}

function ReliabilityCard() {
  const { data } = useQuery({
    queryKey: ["supplier-reliability"],
    queryFn: () => api.get<ReliabilitySummary>("/api/suppliers/me/reliability"),
  });
  if (!data) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>My reliability score</CardTitle>
        <CardDescription>Computed from your real commitment history -- not a fabricated rating.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{Math.round(data.reliability_score * 100)}%</span>
          <Badge variant={data.confidence === "low" ? "warning" : data.confidence === "medium" ? "info" : "success"}>
            {data.confidence} confidence
          </Badge>
          <span className="text-xs text-slate-400">({data.sample_size} commitments)</span>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Fulfilled {data.fulfilled_count} · Short-supplied {data.short_supply_count} · Rejected {data.rejected_count} · Expired {data.expired_count}
        </p>
        {data.sample_size < 4 && (
          <p className="text-xs text-amber-700 dark:text-amber-400">Low sample size — this score is not yet statistically reliable.</p>
        )}
      </CardContent>
    </Card>
  );
}

export function SupplierDashboard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data, isLoading, error } = useQuery({
    queryKey: ["supplier-allocations"],
    queryFn: () => api.get<Allocation[]>("/api/suppliers/me/allocations"),
    refetchInterval: 5000,
  });
  const [qtyByAlloc, setQtyByAlloc] = useState<Record<string, string>>({});
  const [rejectTarget, setRejectTarget] = useState<Allocation | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["supplier-allocations"] });

  const confirmMutation = useMutation({
    mutationFn: ({ id, qty }: { id: string; qty: number }) =>
      api.post(`/api/allocations/${id}/confirm`, { confirmed_qty_base_unit: qty, ready_by: new Date(Date.now() + 2 * 86400000).toISOString() }),
    onSuccess: (_, vars) => {
      invalidate();
      toast({ title: "Confirmation sent", description: `Confirmed ${vars.qty} units.`, variant: "success" });
    },
  });
  const rejectMutation = useMutation({
    mutationFn: (id: string) => api.post(`/api/allocations/${id}/reject`, { reason: "Cannot fulfill at this time" }),
    onSuccess: () => {
      invalidate();
      setRejectTarget(null);
      toast({ title: "Order rejected", description: "The merchant's system will automatically reallocate this quantity.", variant: "info" });
    },
  });
  const dispatchMutation = useMutation({
    mutationFn: (id: string) => api.post(`/api/allocations/${id}/dispatch`),
    onSuccess: () => invalidate(),
  });
  const deliverMutation = useMutation({
    mutationFn: (id: string) => api.post(`/api/allocations/${id}/deliver`),
    onSuccess: () => {
      invalidate();
      toast({ title: "Marked delivered", variant: "success" });
    },
  });

  const { pending, active } = useMemo(() => {
    const all = data ?? [];
    return {
      pending: all.filter((a) => a.status === "proposed"),
      active: all.filter((a) => a.status === "confirmed" || a.status === "short_supply"),
    };
  }, [data]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Incoming Orders</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Respond before the confirmation deadline to avoid an automatic reallocation away from you.</p>
      </div>

      <ReliabilityCard />

      {isLoading && <Spinner label="Loading incoming orders…" />}
      {error && <ErrorState message="Could not load incoming orders." />}
      {data && data.length === 0 && <EmptyState title="No incoming orders yet" icon={<Inbox className="h-8 w-8" />} />}

      {pending.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Needs your response ({pending.length})</h2>
          <div className="space-y-2">
            {pending.map((a) => {
              const urgency = deadlineUrgency(a.confirmation_expires_at);
              return (
                <Card key={a.id} className={urgency.variant === "danger" ? "border-rose-300 dark:border-rose-800" : ""}>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                        {a.product_name} — {a.allocated_qty_base_unit} units @ {formatINR(a.unit_price, true)}
                      </p>
                      <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                        <Clock className="h-3 w-3" />
                        <Badge variant={urgency.variant}>{urgency.label}</Badge>
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number" className="w-24" placeholder="Qty"
                        value={qtyByAlloc[a.id] ?? a.allocated_qty_base_unit}
                        onChange={(e) => setQtyByAlloc((prev) => ({ ...prev, [a.id]: e.target.value }))}
                      />
                      <Button
                        data-testid={`confirm-${a.id}`} size="sm" variant="success"
                        onClick={() => confirmMutation.mutate({ id: a.id, qty: Number(qtyByAlloc[a.id] ?? a.allocated_qty_base_unit) })}
                      >
                        Confirm
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => setRejectTarget(a)}>
                        Reject
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {active.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Confirmed — ready to fulfill ({active.length})</h2>
          <div className="space-y-2">
            {active.map((a) => (
              <Card key={a.id}>
                <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                      {a.product_name} — {a.confirmed_qty_base_unit ?? a.allocated_qty_base_unit} units confirmed
                    </p>
                    <StatusBadge status={a.status} />
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => dispatchMutation.mutate(a.id)}>
                      <Truck className="h-3.5 w-3.5" /> Dispatch
                    </Button>
                    <Button size="sm" onClick={() => deliverMutation.mutate(a.id)}>
                      <PackageCheck className="h-3.5 w-3.5" /> Delivered
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!rejectTarget}
        onClose={() => setRejectTarget(null)}
        onConfirm={() => rejectTarget && rejectMutation.mutate(rejectTarget.id)}
        title="Reject this allocation?"
        description={`The merchant's system will automatically reallocate ${rejectTarget?.allocated_qty_base_unit ?? ""} units to an alternative supplier. This action is recorded against your reliability score.`}
        confirmLabel="Reject order"
        variant="destructive"
        isLoading={rejectMutation.isPending}
      />
    </div>
  );
}
