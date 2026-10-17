import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Repeat } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { useToast } from "../../components/ui/toast";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import type { Order } from "../../lib/types";

interface Suggestion {
  product_id: string;
  product_name: string;
  suggested_qty_base_unit: number;
  sample_size: number;
  avg_interval_days: number | null;
  last_order_date: string;
  confidence: "low" | "medium" | "high";
}

const CONFIDENCE_VARIANT: Record<string, "default" | "success" | "warning"> = { low: "default", medium: "warning", high: "success" };

export function AutopilotPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { data, isLoading, error } = useQuery({
    queryKey: ["autopilot-suggestions"],
    queryFn: () => api.get<Suggestion[]>("/api/intelligence/autopilot-suggestions"),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const createOrderMutation = useMutation({
    mutationFn: () => {
      const items = (data ?? [])
        .filter((s) => selected.has(s.product_id))
        .map((s) => ({ product_id: s.product_id, requested_qty_base_unit: s.suggested_qty_base_unit, substitution_allowed: true }));
      return api.post<Order>("/api/orders", { items });
    },
    onSuccess: (order) => {
      toast({ title: "Draft order created", description: "Review items and generate plans on the order page.", variant: "success" });
      navigate(`/merchant/orders/${order.id}`);
    },
    onError: () => toast({ title: "Could not create order", variant: "error" }),
  });

  function toggle(productId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) next.delete(productId);
      else next.add(productId);
      return next;
    });
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <Repeat className="h-5 w-5 text-brand-500" /> Procurement Autopilot
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Suggested reorders based on your real purchase frequency. Nothing is ordered automatically -- review, select,
          and this only creates a draft order for you to plan and approve like any other.
        </p>
      </div>

      {isLoading && <Spinner />}
      {error && <ErrorState message="Could not load suggestions." />}
      {data && data.length === 0 && (
        <EmptyState title="No reorders due right now" hint="Suggestions appear once a product is approaching its usual reorder cycle." />
      )}

      {data && data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Suggested reorders</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.map((s) => (
              <label key={s.product_id} className="flex items-center gap-3 rounded-lg border border-slate-100 p-3 text-sm hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60">
                <input type="checkbox" checked={selected.has(s.product_id)} onChange={() => toggle(s.product_id)} className="h-4 w-4 accent-brand-600" />
                <div className="flex-1">
                  <p className="font-medium text-slate-800 dark:text-slate-200">{s.product_name} — ~{s.suggested_qty_base_unit}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Last ordered {formatDate(s.last_order_date)} · usual cycle ~{s.avg_interval_days ?? "—"} days · {s.sample_size} past orders
                  </p>
                </div>
                <Badge variant={CONFIDENCE_VARIANT[s.confidence]}>{s.confidence} confidence</Badge>
              </label>
            ))}
            <div className="flex justify-end pt-2">
              <Button disabled={selected.size === 0 || createOrderMutation.isPending} onClick={() => createOrderMutation.mutate()}>
                {createOrderMutation.isPending ? "Creating…" : `Create draft order (${selected.size})`}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
