import { RecoveryEvidence } from "../components/RecoveryEvidence";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  CheckCircle2, CircleDashed, IndianRupee, RotateCcw, Truck, Zap, ZapOff, FileWarning,
} from "lucide-react";
import { Badge, StatusBadge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input, Label } from "../components/ui/input";
import { ErrorState, Spinner } from "../components/ui/state";
import { InfoHint } from "../components/ui/tooltip";
import { useToast } from "../components/ui/toast";
import { ApiError, api } from "../lib/api";
import { formatINR, timeAgo } from "../lib/format";
import type { AllocationPlan, Order, Payment, ReconciliationResponse, ScenarioResult } from "../lib/types";

const OBJECTIVE_LABEL: Record<string, string> = {
  cheapest: "Cheapest",
  fastest: "Fastest",
  most_reliable: "Most reliable",
};

function PlanCard({
  plan, onSelect, selecting,
}: { plan: AllocationPlan; onSelect: () => void; selecting: boolean }) {
  return (
    <Card className={plan.is_selected ? "border-brand-500 ring-1 ring-brand-500" : ""}>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{OBJECTIVE_LABEL[plan.objective_profile]}</CardTitle>
        {plan.is_feasible ? <Badge variant="success">Feasible</Badge> : <Badge variant="danger">Partial / infeasible</Badge>}
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400">
            Total landed cost <InfoHint text="Product cost + delivery cost. Risk penalty is shown separately and is not added to what you pay." />
          </span>
          <span className="font-semibold text-slate-900 dark:text-slate-100">{formatINR(plan.total_cost)}</span>
        </div>
        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>Product + delivery</span>
          <span>{formatINR(plan.total_product_cost)} + {formatINR(plan.total_delivery_cost)}</span>
        </div>
        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1">Risk penalty <InfoHint text="A scoring factor (cost x (1 - supplier reliability)) used to rank plans -- it is not charged to you." /></span>
          <span>{formatINR(plan.total_risk_penalty)}</span>
        </div>
        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>Estimated delivery</span>
          <span>{plan.estimated_delivery_hours.toFixed(1)} h</span>
        </div>
        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>Suppliers used</span>
          <span>{plan.supplier_count}</span>
        </div>
        <ul className="divide-y divide-slate-100 text-xs text-slate-600 dark:divide-slate-800 dark:text-slate-300">
          {plan.allocations.map((a) => (
            <li key={a.id} className="flex justify-between py-1">
              <span>{a.product_name} — {a.supplier_name}</span>
              <span>{a.allocated_qty_base_unit} base units @ {formatINR(a.unit_price, true)}</span>
            </li>
          ))}
        </ul>
        {!plan.is_feasible && plan.infeasible_reasons.length > 0 && (
          <ul className="list-inside list-disc text-xs text-amber-700 dark:text-amber-400">
            {plan.infeasible_reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        )}
        {!plan.is_selected && (
          <Button data-testid={`select-plan-${plan.objective_profile}`} size="sm" className="mt-2 w-full" onClick={onSelect} disabled={selecting}>
            Select this plan
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function OrderTimeline({ order }: { order: Order }) {
  const sorted = [...order.plans].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const initial = sorted.filter((p) => p.replan_reason === "initial");
  const replans = sorted.filter((p) => p.replan_reason !== "initial");

  const events: { icon: typeof Zap; label: string; detail: string; time: string; tone: string }[] = [];
  events.push({ icon: Zap, label: "Order created", detail: `${order.items.length} item(s) requested`, time: order.created_at, tone: "text-brand-600" });
  if (initial.length > 0) {
    events.push({
      icon: IndianRupee, label: "Plans generated", detail: `${initial.length} option(s) compared by OR-Tools CP-SAT`,
      time: initial[0].created_at, tone: "text-brand-600",
    });
  }
  for (const r of replans) {
    events.push({
      icon: RotateCcw, label: `Automatic replan: ${r.replan_reason.replace(/_/g, " ")}`,
      detail: `New total cost ${formatINR(r.total_cost)}`, time: r.created_at, tone: "text-signal-600",
    });
  }

  return (
    <div className="space-y-0">
      {events.map((ev, idx) => {
        const Icon = ev.icon;
        return (
          <div key={idx} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className={`flex h-7 w-7 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 ${ev.tone}`}>
                <Icon className="h-3.5 w-3.5" />
              </div>
              {idx < events.length - 1 && <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700" />}
            </div>
            <div className="pb-4 pt-0.5">
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{ev.label}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{ev.detail}</p>
              <p className="text-[11px] text-slate-400 dark:text-slate-500">{timeAgo(ev.time)}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [error, setError] = useState<string | null>(null);
  const [receiptQty, setReceiptQty] = useState<Record<string, string>>({});

  const orderQuery = useQuery({
    queryKey: ["order", orderId],
    queryFn: () => api.get<Order>(`/api/orders/${orderId}`),
    refetchInterval: 4000,
  });

  const reviewMutation = useMutation({
    mutationFn: () => api.post(`/api/orders/${orderId}/confirm-items`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["order", orderId] }); },
    onError: (err: Error) => setError(err.message),
  });

  const planMutation = useMutation({
    mutationFn: () => api.post(`/api/orders/${orderId}/plan`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["order", orderId] });
      toast({ title: "Plans generated", description: "Compare cheapest, fastest, and most reliable below.", variant: "success" });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not generate plans"),
  });

  const selectMutation = useMutation({
    mutationFn: (planId: string) => api.post(`/api/orders/${orderId}/select-plan`, { plan_id: planId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["order", orderId] });
      toast({ title: "Plan selected", description: "Suppliers have been notified for confirmation.", variant: "success" });
    },
  });

  const payMutation = useMutation({
    mutationFn: () => api.post<Payment>("/api/payments/initiate", { order_id: orderId }),
    onSuccess: (payment) => {
      qc.invalidateQueries({ queryKey: ["order", orderId] });
      toast({
        title: payment.status === "success" ? "Payment successful (simulated)" : "Payment failed (simulated)",
        variant: payment.status === "success" ? "success" : "error",
      });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Payment failed"),
  });

  const receiptMutation = useMutation({
    mutationFn: ({ allocationId, productId, qty }: { allocationId: string; productId: string; qty: number }) =>
      api.post(`/api/orders/${orderId}/receipts`, { allocation_id: allocationId, product_id: productId, received_qty_base_unit: qty }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reconciliation", orderId] });
      toast({ title: "Receipt recorded", variant: "success" });
    },
  });

  const [scenarioResult, setScenarioResult] = useState<ScenarioResult | null>(null);
  const scenarioMutation = useMutation({
    mutationFn: ({ allocationId, disruptionType }: { allocationId: string; disruptionType: string }) =>
      api.post<ScenarioResult>("/api/scenarios/disrupt", {
        order_id: orderId, allocation_id: allocationId, disruption_type: disruptionType,
        magnitude_pct: disruptionType === "partial_stock" ? 50 : 0,
        description: "Digital Twin simulation triggered from merchant order view",
      }),
    onSuccess: (resp) => {
      setScenarioResult(resp);
      qc.invalidateQueries({ queryKey: ["order", orderId] });
      toast({ title: "Disruption simulated", description: "The real failover engine re-optimized the plan.", variant: "info" });
    },
  });

  const reconciliationQuery = useQuery({
    queryKey: ["reconciliation", orderId],
    queryFn: () => api.get<ReconciliationResponse>(`/api/orders/${orderId}/reconciliation`),
    enabled: !!orderQuery.data && orderQuery.data.status !== "draft" && orderQuery.data.status !== "planned",
  });

  if (orderQuery.isLoading) return <Spinner label="Loading order…" />;
  if (orderQuery.error || !orderQuery.data) return <ErrorState message="Could not load order." />;

  const order = orderQuery.data;
  const plans = order.plans;
  const selectedPlan = plans.find((p) => p.is_selected);
  const latestPlans = plans.slice(-3);
  const isRecovering = order.status === "replanning";

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Order #{order.id.slice(0, 8)}</h1>
          <StatusBadge status={order.status} />
        </div>

        <RecoveryEvidence orderId={order.id} />

        {isRecovering && (
          <div className="animate-recovery-pulse flex items-start gap-3 rounded-xl border border-signal-500/40 bg-signal-500/5 p-4">
            <RotateCcw className="h-5 w-5 shrink-0 animate-spin text-signal-600" style={{ animationDuration: "2s" }} />
            <div>
              <p className="text-sm font-semibold text-signal-700 dark:text-signal-400">Recovery plan ready — awaiting confirmations</p>
              <p className="text-xs text-slate-600 dark:text-slate-300">
                A supplier failed to fully confirm. A revised plan proposes alternative supply. It is not confirmed until suppliers accept.
              </p>
            </div>
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Items requested</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {order.items.map((i) => (
                <li key={i.id} className="flex justify-between py-1.5">
                  <span className="text-slate-700 dark:text-slate-300">{i.product_name}</span>
                  <span className="text-slate-900 dark:text-slate-100">{i.requested_qty_base_unit} base units</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {order.requires_confirmation && <Button disabled={reviewMutation.isPending} onClick={() => reviewMutation.mutate()}>I reviewed the listed products and quantities — approve basket</Button>}

        {order.status === "draft" && (
          <Button onClick={() => planMutation.mutate()} disabled={planMutation.isPending || order.requires_confirmation}>
            {planMutation.isPending ? "Optimizing (OR-Tools CP-SAT)…" : "Generate 3 plans (cheapest / fastest / most reliable)"}
          </Button>
        )}

        {error && <ErrorState message={error} />}

        {!selectedPlan && latestPlans.length > 0 && (
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Compare plans</h2>
            <div className="grid gap-3 md:grid-cols-3">
              {latestPlans.map((p) => (
                <PlanCard key={p.id} plan={p} selecting={selectMutation.isPending} onSelect={() => selectMutation.mutate(p.id)} />
              ))}
            </div>
          </div>
        )}

        {selectedPlan && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              Active plan ({OBJECTIVE_LABEL[selectedPlan.objective_profile]}
              {selectedPlan.replan_reason !== "initial" && <> — replanned after {selectedPlan.replan_reason.replace(/_/g, " ")}</>})
            </h2>
            <Card>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
                      <th className="py-1 pr-2">Product</th>
                      <th className="py-1 pr-2">Supplier</th>
                      <th className="py-1 pr-2">Allocated</th>
                      <th className="py-1 pr-2">Confirmed</th>
                      <th className="py-1 pr-2">Status</th>
                      <th className="py-1 pr-2">Route</th>
                      <th className="py-1 pr-2">Digital Twin</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-slate-800/60">
                    {selectedPlan.allocations.map((a) => (
                      <tr key={a.id}>
                        <td className="py-1.5 pr-2">{a.product_name}</td>
                        <td className="py-1.5 pr-2">{a.supplier_name}</td>
                        <td className="py-1.5 pr-2">{a.allocated_qty_base_unit} kg</td>
                        <td className="py-1.5 pr-2">{a.confirmed_qty_base_unit ?? "—"}</td>
                        <td className="py-1.5 pr-2"><StatusBadge status={a.status} /></td>
                        <td className="py-1.5 pr-2 text-xs text-slate-500 dark:text-slate-400">
                          {a.route_distance_km ? `${a.route_distance_km}km (${a.route_source})` : "—"}
                        </td>
                        <td className="py-1.5 pr-2">
                          {(a.status === "confirmed" || a.status === "proposed") && (
                            <div className="flex gap-1">
                              <Button size="sm" variant="outline" disabled={scenarioMutation.isPending} onClick={() => scenarioMutation.mutate({ allocationId: a.id, disruptionType: "supplier_outage" })}>
                                <ZapOff className="h-3.5 w-3.5" /> Outage
                              </Button>
                              <Button size="sm" variant="outline" disabled={scenarioMutation.isPending} onClick={() => scenarioMutation.mutate({ allocationId: a.id, disruptionType: "partial_stock" })}>
                                <FileWarning className="h-3.5 w-3.5" /> 50% stock
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {scenarioResult && (
              <div className="animate-fade-in-up rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300">
                <p className="font-semibold">Digital Twin result</p>
                <p className="mt-1">{scenarioResult.narrative}</p>
                <div className="mt-2 flex gap-6 text-xs">
                  <span>Cost: {formatINR(scenarioResult.before_total_cost)} → <strong>{formatINR(scenarioResult.after_total_cost)}</strong></span>
                  <span>Delivery: {scenarioResult.before_delivery_hours.toFixed(1)}h → <strong>{scenarioResult.after_delivery_hours.toFixed(1)}h</strong></span>
                </div>
              </div>
            )}

            {order.status === "confirmed" && (
              <Button onClick={() => payMutation.mutate()} disabled={payMutation.isPending}>
                {payMutation.isPending ? "Processing payment…" : "Pay now (simulated / Paytm sandbox)"}
              </Button>
            )}
            {payMutation.data && (
              <p className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                Payment status: <StatusBadge status={payMutation.data.status} />
                {payMutation.data.is_simulated && <Badge variant="info">Simulated</Badge>}
              </p>
            )}
          </div>
        )}

        {reconciliationQuery.data && (
          <Card>
            <CardHeader>
              <CardTitle>Order Truth Engine — ordered vs invoiced vs received</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-slate-500 dark:border-slate-800 dark:text-slate-400">
                    <th className="py-1 pr-2">Product</th>
                    <th className="py-1 pr-2">Ordered</th>
                    <th className="py-1 pr-2">Invoiced</th>
                    <th className="py-1 pr-2">Received</th>
                    <th className="py-1 pr-2">Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliationQuery.data.lines.map((l) => (
                    <tr key={l.product_id} className="border-b border-slate-50 dark:border-slate-800/60">
                      <td className="py-1.5 pr-2">{l.product_name}</td>
                      <td className="py-1.5 pr-2">{l.ordered_qty}</td>
                      <td className="py-1.5 pr-2">{l.invoiced_qty}</td>
                      <td className="py-1.5 pr-2">{l.received_qty}</td>
                      <td className="py-1.5 pr-2">
                        {l.flags.length === 0 ? (
                          <Badge variant="success">OK</Badge>
                        ) : (
                          l.flags.map((f) => <Badge key={f} variant="danger" className="mr-1">{f.replace(/_/g, " ")}</Badge>)
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-2 dark:border-slate-800">
                {selectedPlan?.allocations
                  .filter((a) => a.status !== "rejected" && a.status !== "expired" && a.status !== "superseded")
                  .map((a) => (
                    <div key={a.id} className="flex items-end gap-1">
                      <div className="space-y-1">
                        <Label>{a.product_name} from {a.supplier_name}</Label>
                        <Input type="number" className="w-28" value={receiptQty[a.id] ?? ""} onChange={(e) => setReceiptQty((prev) => ({ ...prev, [a.id]: e.target.value }))} />
                      </div>
                      <Button size="sm" variant="outline" onClick={() => receiptMutation.mutate({ allocationId: a.id, productId: a.product_id, qty: Number(receiptQty[a.id] ?? 0) })}>
                        Record receipt
                      </Button>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Order timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <OrderTimeline order={order} />
          </CardContent>
        </Card>

        {selectedPlan && (
          <Card>
            <CardHeader>
              <CardTitle>Fulfillment progress</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {selectedPlan.allocations.map((a) => (
                <div key={a.id} className="flex items-center gap-2">
                  {a.status === "fulfilled" ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  ) : a.status === "confirmed" || a.status === "short_supply" ? (
                    <Truck className="h-4 w-4 text-sky-600" />
                  ) : (
                    <CircleDashed className="h-4 w-4 text-slate-400" />
                  )}
                  <span className="flex-1 text-slate-700 dark:text-slate-300">{a.product_name} — {a.supplier_name}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
