import { useT } from "../../lib/i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { FreshnessBadge, MethodNote, PageHeader, PromiseEquation, RiskBadge, StageTrack } from "../../components/supplier/parts";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label } from "../../components/ui/input";
import { ErrorState, Spinner } from "../../components/ui/state";
import { InfoHint } from "../../components/ui/tooltip";
import { useToast } from "../../components/ui/toast";
import { api, ApiError } from "../../lib/api";
import { istTime, qty, type InventoryPosition, type LedgerEvent, type PromiseLedger } from "../../lib/continuity";
import { cn } from "../../lib/utils";

function CountForm({ pos, onClose }: { pos: InventoryPosition; onClose: () => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [onHand, setOnHand] = useState(String(pos.on_hand));
  const [safety, setSafety] = useState(String(pos.safety_stock));
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => api.post<{ free_to_promise_base_unit: number }>(`/api/suppliers/me/inventory/${pos.inventory_id}/stock-count`, {
      on_hand_base_unit: Number(onHand), safety_stock_base_unit: Number(safety), reason,
    }),
    onSuccess: (r) => {
      ["promise-ledger", "supplier-copilot", "dispatch-board", "guard", "ledger-events"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      const drift = Number(onHand) < pos.committed;
      toast({ title: drift ? "Count recorded — below your commitments" : "Stock count recorded",
        description: drift ? `${pos.committed - Number(onHand)} ${pos.unit} short of what you promised. Relay the gap from the dispatch board.` : `Free to promise is now ${r.free_to_promise_base_unit} ${pos.unit}.`,
        variant: drift ? "error" : "success" });
      onClose();
    },
    onError: (e) => toast({ title: "Not saved", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" }),
  });
  return (
    <form className="grid gap-2 rounded-lg bg-slate-50 p-3 sm:grid-cols-[1fr_1fr_2fr_auto] dark:bg-slate-900" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div className="space-y-1"><Label htmlFor={`oh-${pos.inventory_id}`}>Physical on hand ({pos.unit})</Label><Input id={`oh-${pos.inventory_id}`} type="number" min={0} step="any" value={onHand} onChange={(e) => setOnHand(e.target.value)} autoFocus /></div>
      <div className="space-y-1"><Label htmlFor={`ss-${pos.inventory_id}`}>Safety stock</Label><Input id={`ss-${pos.inventory_id}`} type="number" min={0} step="any" value={safety} onChange={(e) => setSafety(e.target.value)} /></div>
      <div className="space-y-1"><Label htmlFor={`rs-${pos.inventory_id}`}>Note (optional)</Label><Input id={`rs-${pos.inventory_id}`} placeholder="e.g. weekly count, 2 bags damaged" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
      <div className="flex items-end gap-1.5"><Button type="submit" size="sm" disabled={save.isPending || onHand === ""}>Save count</Button><Button type="button" size="sm" variant="ghost" onClick={onClose}>Cancel</Button></div>
      <p className="text-[11px] text-slate-500 sm:col-span-4">Enter what is physically in the warehouse. The {qty(pos.committed, pos.unit)} already committed is subtracted automatically, so it is never promised twice.</p>
    </form>
  );
}

const ACTION_LABEL: Record<string, string> = {
  stock_count: "Stock counted", commitment_drift_detected: "Drift detected", commitment_accepted: "Commitment accepted",
  partial_commitment: "Partial commitment", request_rejected: "Request declined", commitment_broken: "Commitment broken",
  stage_changed: "Stage changed", relay_opened: "Relay opened", relay_invite_sent: "Relay invite", relay_accepted: "Relay accepted",
  relay_modified: "Relay counter-quote", relay_declined: "Relay declined", relay_approved: "Relay approved", relay_stock_reserved: "Relay stock reserved",
  relay_reservation_failed: "Relay reservation failed", relay_expired: "Relay expired", relay_fallback: "Relay fell back", relay_superseded: "Relay superseded",
  declined_with_relay: "Declined and relayed",
};

export function LedgerPage() {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const counting = params.get("count");
  const q = useQuery({ queryKey: ["promise-ledger"], queryFn: () => api.get<PromiseLedger>("/api/suppliers/me/promise-ledger"), refetchInterval: 15_000 });
  const events = useQuery({ queryKey: ["ledger-events"], queryFn: () => api.get<LedgerEvent[]>("/api/suppliers/me/ledger-events") });

  if (q.isPending) return <Spinner label="Loading promise ledger…" />;
  if (q.isError) return <ErrorState message="Could not load the promise ledger." />;
  const { inventory, commitments, definitions } = q.data;
  const live = commitments.filter((c) => c.stage !== "delivered" && c.stage !== "reconciled");
  const closed = commitments.filter((c) => c.stage === "delivered" || c.stage === "reconciled").slice(0, 12);

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Promise Intelligence Ledger" title={t("sup.ledgerTitle")}>
        Listed stock is not promisable stock. Every figure below is derived from your last physical count and your recorded commitments.
      </PageHeader>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{t("sup.stockPositions")}</CardTitle>
          <span className="hidden text-xs text-slate-500 sm:block">free to promise = on hand − committed − safety stock</span>
        </CardHeader>
        <CardContent className="space-y-2">
          {inventory.map((p) => (
            <div key={p.inventory_id} className={cn("rounded-lg border p-3", p.drift_qty > 0 ? "border-rose-300 dark:border-rose-800" : p.oversubscribed_by > 0 ? "border-amber-300 dark:border-amber-800" : "border-slate-200 dark:border-slate-800")}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{p.product_name} <span className="font-normal text-slate-500">· {p.brand} · {p.pack_size} {p.unit} packs</span></p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <FreshnessBadge freshness={p.freshness} />
                    {p.requested_pending > 0 && <Badge variant={p.oversubscribed_by > 0 ? "warning" : "default"}>{qty(p.requested_pending, p.unit)} requested, not reserved</Badge>}
                    {p.in_transit > 0 && <Badge variant="info">{qty(p.in_transit, p.unit)} in transit</Badge>}
                    {p.drift_qty > 0 && <Badge variant="danger">count {qty(p.drift_qty, p.unit)} below commitments</Badge>}
                    {!p.is_available && <Badge>paused</Badge>}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <PromiseEquation compact onHand={p.on_hand} committed={p.committed} safety={p.safety_stock} free={p.free_to_promise} unit={p.unit} />
                  <Button size="sm" variant="outline" onClick={() => setParams(counting === p.inventory_id ? {} : { count: p.inventory_id })} aria-expanded={counting === p.inventory_id}>
                    <ClipboardCheck className="h-3.5 w-3.5" aria-hidden /> {t("sup.count")}
                  </Button>
                </div>
              </div>
              {counting === p.inventory_id && <div className="mt-2"><CountForm pos={p} onClose={() => setParams({})} /></div>}
            </div>
          ))}
          <dl className="grid gap-x-6 gap-y-1 pt-2 text-[11px] text-slate-500 sm:grid-cols-2">
            {Object.entries(definitions).map(([k, v]) => <div key={k}><dt className="inline font-semibold">{k.replace(/_/g, " ")}: </dt><dd className="inline">{v}</dd></div>)}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Commitment lifecycle</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead><tr className="text-left text-xs text-slate-500">
              <th className="py-1.5 font-medium">Commitment</th><th className="font-medium">Asked / committed</th><th className="font-medium">Stage</th>
              <th className="font-medium">Ready-by / valid until</th><th className="font-medium">Risk <InfoHint text="Rule-based points from stock freshness, counts, deadlines and capacity. Hover a badge for the factors." /></th>
            </tr></thead>
            <tbody>{[...live, ...closed].map((c) => (
              <tr key={c.allocation_id} className="border-t border-slate-100 align-top dark:border-slate-800">
                <td className="py-2"><p className="font-medium text-slate-900 dark:text-slate-100">{c.product_name}</p><p className="text-xs text-slate-500">#{c.order_ref} · ₹{c.unit_price}/{c.unit}</p></td>
                <td className="tabular-nums">{qty(c.requested_qty)} / {qty(c.committed_qty, c.unit)}{c.received_qty !== null && <p className="text-xs text-slate-500">received {qty(c.received_qty, c.unit)}</p>}</td>
                <td><StageTrack stage={c.stage} times={c.stage_times} /></td>
                <td className="text-xs tabular-nums text-slate-600 dark:text-slate-300">{c.stage === "quote" ? `quote valid until ${istTime(c.quote_valid_until)}` : istTime(c.ready_by)}</td>
                <td>{c.risk ? <RiskBadge risk={c.risk} /> : <span className="text-xs text-slate-400">—</span>}</td>
              </tr>))}</tbody>
          </table>
          {commitments.length === 0 && <p className="py-6 text-center text-sm text-slate-500">No commitments yet.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Audit trail</CardTitle></CardHeader>
        <CardContent>
          {events.isPending ? <Spinner label="Loading audit trail…" /> : events.isError ? <ErrorState message="Audit trail unavailable." /> : events.data.length === 0 ? <p className="text-sm text-slate-500">No recorded changes yet.</p> : (
            <ol className="space-y-1.5 text-sm">{events.data.slice(0, 40).map((e) => (
              <li key={e.id} className="flex flex-wrap gap-x-2">
                <span className="w-28 shrink-0 text-xs tabular-nums text-slate-500">{istTime(e.at)}</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">{ACTION_LABEL[e.action] ?? e.action}</span>
                {e.from_state && e.to_state && <span className="text-xs text-slate-500">{e.from_state} → {e.to_state}</span>}
                {e.qty !== null && <span className="text-xs tabular-nums text-slate-600 dark:text-slate-300">{qty(e.qty)}</span>}
                {e.reason && <span className="text-xs text-slate-500">“{e.reason}”</span>}
                <span className="text-xs text-slate-400">by {e.actor_role}</span>
              </li>))}</ol>
          )}
          <MethodNote>Append-only: entries are never edited or deleted by the application.</MethodNote>
        </CardContent>
      </Card>
    </div>
  );
}
