import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { LifeBuoy, Plus, Trash2 } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label, Select } from "../../components/ui/input";
import { ErrorState } from "../../components/ui/state";
import { ApiError, api } from "../../lib/api";
import { formatINR } from "../../lib/format";
import type { Product } from "../../lib/types";

interface DraftLine {
  product_id: string;
  product_name: string;
  requested_qty_base_unit: number;
  priority: number;
}

interface TierResult {
  priority: number;
  items: string[];
  is_feasible: boolean;
  allocations: { product_id: string; supplier_id: string; allocated_qty_base_unit: number; unit_price: number }[];
  tier_cost: number;
  shortfall_by_item: Record<string, number>;
  infeasible_reasons: string[];
}
interface SurvivalResult {
  tiers: TierResult[];
  total_spent: number;
  budget_cap: number;
  remaining_budget: number;
  fully_unfulfilled_items: { product_id: string; product_name: string; priority: number; shortfall_qty_base_unit: number }[];
}

const PRIORITY_LABEL: Record<number, string> = { 1: "Must-have", 2: "Important", 3: "Nice-to-have" };

export function SurvivalModePage() {
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.get<Product[]>("/api/products") });
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [productId, setProductId] = useState("");
  const [qty, setQty] = useState("");
  const [priority, setPriority] = useState(1);
  const [budget, setBudget] = useState("2000");
  const [error, setError] = useState<string | null>(null);

  const planMutation = useMutation({
    mutationFn: () =>
      api.post<SurvivalResult>("/api/intelligence/survival-mode", {
        items: lines.map((l) => ({
          product_id: l.product_id, product_name: l.product_name,
          requested_qty_base_unit: l.requested_qty_base_unit, priority: l.priority,
        })),
        budget_cap: Number(budget),
      }),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not compute survival basket"),
  });

  function addLine() {
    const product = products?.find((p) => p.id === productId);
    if (!product || !qty) return;
    setLines((prev) => [...prev, { product_id: product.id, product_name: product.name, requested_qty_base_unit: Number(qty), priority }]);
    setQty("");
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-slate-100">
          <LifeBuoy className="h-5 w-5 text-brand-500" /> Merchant Survival Mode
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          When your full basket exceeds what's affordable or available, rank items by priority and the real optimizer
          spends your budget tier by tier -- must-haves first -- and shows exactly what can't be covered.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Basket with priorities</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {lines.map((line, idx) => (
            <div key={idx} className="flex items-center gap-2 text-sm">
              <Badge variant={line.priority === 1 ? "danger" : line.priority === 2 ? "warning" : "default"}>
                {PRIORITY_LABEL[line.priority]}
              </Badge>
              <span className="flex-1">{line.product_name} — {line.requested_qty_base_unit}</span>
              <button onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))} className="text-slate-400 hover:text-rose-600">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}

          <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
            <div className="min-w-40 flex-1 space-y-1">
              <Label>Product</Label>
              <Select value={productId} onChange={(e) => setProductId(e.target.value)}>
                <option value="">Select…</option>
                {products?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </div>
            <div className="w-24 space-y-1">
              <Label>Qty</Label>
              <Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
            </div>
            <div className="w-36 space-y-1">
              <Label>Priority</Label>
              <Select value={priority} onChange={(e) => setPriority(Number(e.target.value))}>
                <option value={1}>1 — Must-have</option>
                <option value={2}>2 — Important</option>
                <option value={3}>3 — Nice-to-have</option>
              </Select>
            </div>
            <Button variant="outline" onClick={addLine}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          </div>

          <div className="flex items-end gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
            <div className="w-48 space-y-1">
              <Label>Available budget (₹)</Label>
              <Input type="number" value={budget} onChange={(e) => setBudget(e.target.value)} />
            </div>
            <Button disabled={lines.length === 0 || planMutation.isPending} onClick={() => planMutation.mutate()}>
              {planMutation.isPending ? "Optimizing…" : "Build survival basket"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} />}

      {planMutation.data && (
        <div className="space-y-3">
          <Card>
            <CardContent className="flex flex-wrap gap-6 py-4 text-sm">
              <span>Budget: <strong>{formatINR(planMutation.data.budget_cap)}</strong></span>
              <span>Spent: <strong>{formatINR(planMutation.data.total_spent)}</strong></span>
              <span>Remaining: <strong>{formatINR(planMutation.data.remaining_budget)}</strong></span>
            </CardContent>
          </Card>

          {planMutation.data.tiers.map((tier) => (
            <Card key={tier.priority}>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle>{PRIORITY_LABEL[tier.priority] ?? `Priority ${tier.priority}`} — {tier.items.join(", ")}</CardTitle>
                <Badge variant={tier.is_feasible ? "success" : "warning"}>{tier.is_feasible ? "fully covered" : "partially covered"}</Badge>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="text-slate-500 dark:text-slate-400">Tier cost: {formatINR(tier.tier_cost)}</p>
                {!tier.is_feasible && tier.infeasible_reasons.map((r, i) => (
                  <p key={i} className="text-xs text-amber-700 dark:text-amber-400">{r}</p>
                ))}
              </CardContent>
            </Card>
          ))}

          {planMutation.data.fully_unfulfilled_items.length > 0 && (
            <Card className="border-rose-200 dark:border-rose-900">
              <CardHeader>
                <CardTitle>Cannot be fulfilled within budget</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                {planMutation.data.fully_unfulfilled_items.map((it, i) => (
                  <p key={i} className="text-rose-700 dark:text-rose-400">
                    {it.product_name}: short by {it.shortfall_qty_base_unit}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
