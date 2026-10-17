import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleSlash, Clock, Inbox, ShieldCheck, Workflow, XCircle } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { MethodNote, PageHeader, PromiseEquation } from "../../components/supplier/parts";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Dialog } from "../../components/ui/dialog";
import { Input, Label, Select } from "../../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { useToast } from "../../components/ui/toast";
import { api, ApiError } from "../../lib/api";
import {
  GUARD_TONE, TONE_CLASS, countdown, fromLocalInput, istTime, qty, toLocalInput, type GuardAssessment,
} from "../../lib/continuity";
import { formatINR } from "../../lib/format";
import type { Allocation } from "../../lib/types";
import { cn } from "../../lib/utils";

const REJECT_CODES = [
  ["out_of_stock", "Out of stock"], ["insufficient_capacity", "No dispatch capacity"], ["price_changed", "Price no longer valid"],
  ["delivery_window", "Cannot meet the delivery window"], ["quality_issue", "Quality issue with stock"], ["other", "Other"],
] as const;

function GuardIcon({ status }: { status: GuardAssessment["status"] }) {
  const tone = GUARD_TONE[status].tone;
  if (tone === "ok") return <CheckCircle2 className="h-5 w-5" aria-hidden />;
  if (tone === "bad") return <XCircle className="h-5 w-5" aria-hidden />;
  if (tone === "muted") return <CircleSlash className="h-5 w-5" aria-hidden />;
  return <AlertTriangle className="h-5 w-5" aria-hidden />;
}

function DecisionPanel({ alloc, onDone }: { alloc: Allocation; onDone: () => void }) {
  const { toast } = useToast();
  // null = "use PromiseGuard's suggestion"; a string is the supplier's own edit.
  const [readyByEdit, setReadyBy] = useState<string | null>(null);
  const [qtyEdit, setQtyText] = useState<string | null>(null);
  const [override, setOverride] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [relayReasonEdit, setRelayReason] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectCode, setRejectCode] = useState<string>("out_of_stock");
  const [rejectNote, setRejectNote] = useState("");
  // Re-check the delivery window only for a ready-by the supplier typed; the suggestion
  // is already chosen inside operating hours and daily capacity.
  const editedIso = readyByEdit ? fromLocalInput(readyByEdit) : null;
  const guardQ = useQuery({
    queryKey: ["guard", alloc.id, editedIso],
    queryFn: () => api.get<GuardAssessment>(`/api/allocations/${alloc.id}/guard${editedIso ? `?ready_by=${encodeURIComponent(editedIso)}` : ""}`),
    placeholderData: (prev) => prev,
  });
  const guard = guardQ.data;
  const qtyText = qtyEdit ?? (guard ? String(guard.max_feasible_qty) : "");
  const readyBy = readyByEdit ?? (guard?.suggested_ready_by ? toLocalInput(guard.suggested_ready_by) : "");
  const relayReason = relayReasonEdit ?? (guard ? `Only ${guard.max_feasible_qty} ${guard.unit ?? ""} free to promise right now` : "");
  const readyIso = fromLocalInput(readyBy);

  const commitQty = Number(qtyText);
  const requested = alloc.allocated_qty_base_unit;
  const rest = Math.max(0, Math.round((requested - commitQty) * 1000) / 1000);
  const exceedsGuard = guard ? commitQty > guard.max_feasible_qty + 1e-6 : false;
  const validQty = qtyText !== "" && Number.isFinite(commitQty) && commitQty >= 0 && commitQty <= requested;
  // Safety stock can be overridden; stock already committed to other orders never can.
  const withSafety = guard?.position ? guard.position.free_to_promise + guard.position.safety_stock : 0;
  const overridable = exceedsGuard && !!guard?.position && guard.position.safety_stock > 0 && commitQty <= withSafety + 1e-6;
  const needsOverride = exceedsGuard && !(overridable && override);

  const handleError = (e: unknown) => toast({ title: "Not saved", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" });
  const confirm = useMutation({
    mutationFn: () => api.post(`/api/allocations/${alloc.id}/confirm`, {
      confirmed_qty_base_unit: commitQty, ready_by: readyIso, override_safety_stock: override, override_reason: overrideReason,
    }),
    onSuccess: () => { toast({ title: commitQty >= requested ? "Commitment accepted" : `Committed ${commitQty}; the planner reallocates ${rest}`, variant: "success" }); onDone(); },
    onError: handleError,
  });
  const relay = useMutation({
    mutationFn: () => api.post(`/api/allocations/${alloc.id}/relay`, {
      commit_qty_base_unit: commitQty, ready_by: commitQty > 0 ? readyIso : null, reason: relayReason, response_window_minutes: 120,
    }),
    onSuccess: () => { toast({ title: "Supply relay opened", description: `Partners were asked for ${rest} ${guard?.unit ?? ""}. The merchant approves the final plan.`, variant: "success" }); onDone(); },
    onError: handleError,
  });
  const reject = useMutation({
    mutationFn: () => api.post(`/api/allocations/${alloc.id}/reject`, { reason_code: rejectCode, reason: rejectNote }),
    onSuccess: () => { setRejectOpen(false); toast({ title: "Request declined", description: "Recorded as an up-front decline, not a broken commitment.", variant: "info" }); onDone(); },
    onError: handleError,
  });
  const busy = confirm.isPending || relay.isPending || reject.isPending;

  if (guardQ.isPending) return <Spinner label="PromiseGuard is checking this request…" />;
  if (guardQ.isError || !guard) return <ErrorState message="PromiseGuard could not assess this request." />;
  const tone = GUARD_TONE[guard.status].tone;
  const pos = guard.position;
  const expiry = countdown(alloc.confirmation_expires_at);

  return (
    <div className="space-y-4">
      <div className={cn("flex gap-3 rounded-xl border p-4", TONE_CLASS[tone])} role="status" aria-live="polite">
        <GuardIcon status={guard.status} />
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] opacity-80">PromiseGuard · {guard.label}</p>
          <p className="text-sm font-semibold">{guard.headline}</p>
          {guard.consequence_if_ignored && <p className="mt-1 text-xs opacity-80">{guard.consequence_if_ignored}</p>}
        </div>
      </div>

      {pos && (
        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{pos.product_name} · {pos.brand}</p>
            <p className="text-xs text-slate-500">{pos.pack_size} {pos.unit} packs · MOQ {pos.moq_base_unit} · {formatINR(pos.price_per_base_unit, true)}/{pos.unit}</p>
          </div>
          <PromiseEquation onHand={pos.on_hand} committed={pos.committed} safety={pos.safety_stock} free={pos.free_to_promise} unit={pos.unit} />
          {pos.requested_pending > requested && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              Other open requests also want {qty(pos.requested_pending - requested, pos.unit)} of this stock. Nothing is reserved until you confirm.
            </p>
          )}
        </div>
      )}

      <ul className="grid gap-1.5 text-sm sm:grid-cols-2">
        {guard.checks.map((c) => (
          <li key={c.rule} className="flex gap-2">
            {c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-label="passes" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" aria-label="fails" />}
            <span className="text-slate-700 dark:text-slate-300">{c.detail}</span>
          </li>
        ))}
      </ul>

      <form className="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800" onSubmit={(e) => e.preventDefault()}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="commit-qty">Quantity you will commit ({guard.unit})</Label>
            <Input id="commit-qty" type="number" min={0} max={requested} step="any" inputMode="decimal" value={qtyText} onChange={(e) => setQtyText(e.target.value)} aria-describedby="qty-help" />
            <p id="qty-help" className="text-xs text-slate-500">
              Requested {qty(requested, guard.unit)} · safe maximum {qty(guard.max_feasible_qty, guard.unit)}
              {guard.pack_breakdown && guard.max_feasible_qty > 0 && ` (${guard.pack_breakdown.full_packs} × ${guard.pack_breakdown.pack_size} ${guard.unit} packs + ${guard.pack_breakdown.loose_qty} loose)`}
            </p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ready-by">Ready for dispatch by</Label>
            <Input id="ready-by" type="datetime-local" value={readyBy} onChange={(e) => setReadyBy(e.target.value)} aria-describedby="ready-help" />
            <p id="ready-help" className="text-xs text-slate-500">Suggested {istTime(guard.suggested_ready_by)} IST — {guard.suggestion_basis}</p>
          </div>
        </div>
        {validQty && commitQty > 0 && (
          <p className="text-xs text-slate-600 dark:text-slate-300">
            At {formatINR(alloc.unit_price, true)}/{guard.unit}: {formatINR(commitQty * alloc.unit_price)} committed
            {rest > 0 && <> · {formatINR(rest * alloc.unit_price)} not served by you</>}. {guard.margin_note}
          </p>
        )}
        {overridable && pos && (
          <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
            <label className="flex items-center gap-2 font-medium text-amber-900 dark:text-amber-200">
              <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} className="h-4 w-4 accent-amber-600" />
              Dip into my {qty(pos.safety_stock, pos.unit)} safety stock (recorded in the ledger)
            </label>
            {override && <Input aria-label="Reason for using safety stock" placeholder="Why is this worth it?" value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} />}
          </div>
        )}
        {exceedsGuard && !overridable && (
          <p className="text-sm text-rose-700 dark:text-rose-400" role="alert">
            {qty(commitQty, guard.unit)} would break stock already committed to other orders
            {pos && pos.safety_stock > 0 ? ` (at most ${qty(withSafety, guard.unit)} even using safety stock)` : ""}.
            Commit at most {qty(guard.max_feasible_qty, guard.unit)} or open a relay for the rest.
          </p>
        )}
        {rest > 0 && validQty && (
          <div className="space-y-1">
            <Label htmlFor="relay-reason">Reason partners and the merchant will see</Label>
            <Input id="relay-reason" value={relayReason} onChange={(e) => setRelayReason(e.target.value)} />
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          {validQty && rest <= 0 && (
            <Button variant="success" disabled={busy || needsOverride || !readyIso || (override && overrideReason.trim().length < 3)} onClick={() => confirm.mutate()}>
              <ShieldCheck className="h-4 w-4" aria-hidden /> Accept {qty(requested, guard.unit)}
            </Button>
          )}
          {validQty && rest > 0 && (
            <>
              <Button disabled={busy || needsOverride || relayReason.trim().length < 3 || (commitQty > 0 && !readyIso)} onClick={() => relay.mutate()}>
                <Workflow className="h-4 w-4" aria-hidden /> {commitQty > 0 ? `Commit ${qty(commitQty)} + relay ${qty(rest, guard.unit)}` : `Relay all ${qty(rest, guard.unit)} to partners`}
              </Button>
              {commitQty > 0 && (
                <Button variant="outline" disabled={busy || needsOverride || !readyIso} onClick={() => confirm.mutate()}>
                  Commit {qty(commitQty)}, planner sources the rest
                </Button>
              )}
            </>
          )}
          <Button variant="ghost" className="text-rose-700 dark:text-rose-400" disabled={busy} onClick={() => setRejectOpen(true)}>Decline</Button>
        </div>
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <Clock className="h-3 w-3" aria-hidden /> Quote valid until {istTime(alloc.confirmation_expires_at)} IST ({expiry.text}). Nothing is reserved until you confirm.
        </p>
      </form>
      <MethodNote>{guard.basis}</MethodNote>

      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} title="Decline this request?"
        description="Declining up front is recorded as an honest disclosure, separately from breaking a commitment. The merchant's planner reallocates the full quantity."
        footer={<><Button variant="outline" onClick={() => setRejectOpen(false)}>Keep</Button><Button variant="destructive" disabled={reject.isPending} onClick={() => reject.mutate()}>Decline request</Button></>}>
        <div className="space-y-2">
          <Label htmlFor="reject-code">Reason</Label>
          <Select id="reject-code" value={rejectCode} onChange={(e) => setRejectCode(e.target.value)}>
            {REJECT_CODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Input aria-label="Note for the merchant" placeholder="Optional note" value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} />
        </div>
      </Dialog>
    </div>
  );
}

export function RequestsPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const q = useQuery({ queryKey: ["supplier-allocations"], queryFn: () => api.get<Allocation[]>("/api/suppliers/me/allocations"), refetchInterval: 8000 });
  const pending = useMemo(() => (q.data ?? []).filter((a) => a.status === "proposed")
    .sort((a, b) => (a.confirmation_expires_at ?? "").localeCompare(b.confirmation_expires_at ?? "")), [q.data]);
  const focus = params.get("focus");
  const selected = pending.find((a) => a.id === focus) ?? pending[0];

  const done = () => {
    setParams({});
    for (const key of ["supplier-allocations", "supplier-copilot", "promise-ledger", "dispatch-board", "relays"]) qc.invalidateQueries({ queryKey: [key] });
  };

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="PromiseGuard" title="Incoming requests">
        Each request is checked against what you can actually promise: stock on hand minus existing commitments and safety stock, your hours and your daily capacity.
      </PageHeader>
      {q.isPending && <Spinner label="Loading requests…" />}
      {q.isError && <ErrorState message="Could not load requests." />}
      {q.data && pending.length === 0 && <EmptyState icon={<Inbox className="h-8 w-8" />} title="No requests awaiting a decision" hint="New merchant requests and relay-selected lines appear here." />}
      {selected && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
          <nav aria-label="Requests awaiting decision">
            <ul className="space-y-1.5">
              {pending.map((a) => {
                const due = countdown(a.confirmation_expires_at);
                const active = a.id === selected.id;
                return (
                  <li key={a.id}>
                    <button onClick={() => setParams({ focus: a.id })} aria-current={active ? "true" : undefined}
                      className={cn("w-full rounded-lg border px-3 py-2 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500",
                        active ? "border-brand-400 bg-brand-50 dark:border-brand-700 dark:bg-brand-950/40" : "border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900")}>
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{qty(a.allocated_qty_base_unit)} {a.product_name}</p>
                      <p className="flex justify-between text-xs text-slate-500">
                        <span>{formatINR(a.unit_price, true)}/unit</span>
                        <span className={cn(due.hours < 1 && "font-semibold text-rose-600")}>expires {due.text}</span>
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
          <Card><CardContent className="pt-5"><DecisionPanel key={selected.id} alloc={selected} onDone={done} /></CardContent></Card>
        </div>
      )}
    </div>
  );
}
