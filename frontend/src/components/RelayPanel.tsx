import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Workflow } from "lucide-react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { countdown, istTime, qty, type LedgerEvent, type RelayView } from "../lib/continuity";
import { formatINR } from "../lib/format";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { useToast } from "./ui/toast";

const INVITE_BADGE: Record<string, "default" | "success" | "warning" | "danger" | "info"> = {
  invited: "warning", accepted: "success", modified: "info", declined: "default", reserved: "success", not_selected: "default", reservation_failed: "danger",
};

/** Merchant view of a supplier-initiated Supply Relay: partner quotes, the optimizer's
 *  preview under the order's own policy, and the approve / decline decision. */
export function RelayPanel({ orderId, relays }: { orderId: string; relays: RelayView[] }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const refresh = () => ["order", "evidence", "order-relays", "commitment-trail"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const fail = (e: unknown) => toast({ title: "Not done", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" });
  const approve = useMutation({
    mutationFn: (id: string) => api.post(`/api/orders/${orderId}/relays/${id}/approve`),
    onSuccess: () => { refresh(); toast({ title: "Relay plan approved", description: "Partner stock was reserved at the quoted price.", variant: "success" }); },
    onError: fail,
  });
  const decline = useMutation({
    mutationFn: (id: string) => api.post(`/api/orders/${orderId}/relays/${id}/decline`, { note: "Merchant chose open-market recovery" }),
    onSuccess: () => { refresh(); toast({ title: "Switched to open-market recovery", variant: "info" }); },
    onError: fail,
  });
  if (relays.length === 0) return null;
  const relay = relays[0];
  const pv = relay.preview;
  const due = countdown(relay.expires_at);

  return (
    <Card className={relay.status === "open" ? "border-brand-300 dark:border-brand-800" : undefined} data-testid="relay-panel">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2"><Workflow className="h-4 w-4 text-brand-600" aria-hidden />Supply relay</CardTitle>
            <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-300">
              {relay.origin_supplier_name} committed {qty(relay.origin_committed_qty, relay.unit)} and asked partner wholesalers for the remaining {qty(relay.outstanding_qty, relay.unit)} {relay.product_name}.
            </p>
            <p className="text-xs text-slate-500">“{relay.reason}”</p>
          </div>
          <div className="text-right">
            <Badge variant={relay.status === "open" ? "warning" : relay.status === "approved" ? "success" : "default"}>{relay.status}</Badge>
            {relay.status === "open" && <p className="mt-1 text-xs text-slate-500">window closes {due.text}; then open-market recovery runs</p>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-slate-500"><th className="py-1 font-medium">Partner</th><th className="font-medium">Response</th><th className="font-medium">Quote</th><th className="hidden font-medium sm:table-cell">Evidence</th></tr></thead>
          <tbody>{(relay.invites ?? []).map((i) => (
            <tr key={i.id} className="border-t border-slate-100 dark:border-slate-800">
              <td className="py-1.5"><Link to={`/merchant/suppliers/${i.supplier_id}/passport`} className="text-brand-700 hover:underline dark:text-brand-400">{i.supplier_name}</Link></td>
              <td><Badge variant={INVITE_BADGE[i.status] ?? "default"}>{i.status.replace("_", " ")}</Badge></td>
              <td className="tabular-nums">{i.offered_qty !== null ? `${qty(i.offered_qty)} @ ${formatINR(i.offered_price ?? 0, true)}` : "—"}</td>
              <td className="hidden text-xs text-slate-500 sm:table-cell">{qty(Number(i.eligibility.free_to_promise))} free · reliability {Number(i.eligibility.reliability_score).toFixed(2)} ({String(i.eligibility.reliability_confidence)}) · {String(i.eligibility.distance_to_merchant_km)} km</td>
            </tr>))}</tbody>
        </table>

        {relay.status === "open" && pv && (
          pv.available ? (
            <div className="space-y-2 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">If you approve now</p>
              {pv.lines && pv.lines.length > 0 ? (
                <ul className="text-sm">{pv.lines.map((l) => <li key={l.supplier_name}>{l.supplier_name}: {qty(l.qty, relay.unit)} @ {formatINR(l.unit_price, true)} = {formatINR(l.line_cost)} · ready {istTime(l.ready_by)} IST</li>)}</ul>
              ) : <p className="text-sm text-rose-700 dark:text-rose-400">No partner quote fits your order's limits.</p>}
              <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <div><dt className="text-xs text-slate-500">Covered</dt><dd className="font-semibold tabular-nums">{qty(pv.covered ?? 0, relay.unit)}</dd></div>
                <div><dt className="text-xs text-slate-500">Still uncovered</dt><dd className={`font-semibold tabular-nums ${(pv.uncovered ?? 0) > 0 ? "text-rose-700 dark:text-rose-400" : ""}`}>{qty(pv.uncovered ?? 0, relay.unit)}</dd></div>
                <div><dt className="text-xs text-slate-500">Landed cost</dt><dd className="font-semibold tabular-nums">{formatINR(pv.current_landed_cost ?? 0)} → {formatINR(pv.new_landed_cost ?? 0)}</dd></div>
                <div><dt className="text-xs text-slate-500">Budget</dt><dd className="font-semibold tabular-nums">{pv.budget_cap !== null && pv.budget_cap !== undefined ? formatINR(pv.budget_cap) : "no cap"}</dd></div>
              </dl>
              {(pv.excluded_quotes ?? []).map((x) => <p key={x.supplier_name} className="text-xs text-slate-500">Excluded {x.supplier_name}: {x.reason}</p>)}
              {(pv.infeasible_reasons ?? []).map((r) => <p key={r} className="text-xs text-amber-700 dark:text-amber-400">{r}</p>)}
              <p className="text-[11px] text-slate-500">{pv.policy_note} Price ceiling {pv.price_ceiling ? formatINR(pv.price_ceiling, true) : "none"} · max {pv.max_suppliers} suppliers.</p>
            </div>
          ) : <p className="text-sm text-slate-500">{pv.reason}</p>
        )}

        {relay.status === "open" && (
          <div className="flex flex-wrap gap-2">
            <Button disabled={!pv?.available || !pv.lines?.length || approve.isPending} onClick={() => approve.mutate(relay.id)}>Approve relay plan</Button>
            <Button variant="outline" disabled={decline.isPending} onClick={() => decline.mutate(relay.id)}>Use open-market recovery instead</Button>
          </div>
        )}
        {relay.status !== "open" && relay.resolution_note && <p className="text-sm text-slate-600 dark:text-slate-300">{relay.resolution_note}</p>}
      </CardContent>
    </Card>
  );
}

const TRAIL_LABEL: Record<string, string> = {
  commitment_accepted: "accepted", partial_commitment: "committed part", request_rejected: "declined", commitment_broken: "reported a broken commitment",
  stage_changed: "moved stage", relay_opened: "opened a supply relay", relay_invite_sent: "was invited to the relay", relay_accepted: "accepted the relay",
  relay_modified: "sent a counter-quote", relay_declined: "declined the relay", relay_approved: "approved the relay plan", relay_stock_reserved: "stock reserved",
  relay_reservation_failed: "could not reserve stock", relay_expired: "relay window closed", relay_fallback: "no eligible partner", relay_superseded: "relay superseded",
  declined_with_relay: "declined and relayed",
};

export function CommitmentTrail({ orderId }: { orderId: string }) {
  const q = useQuery({ queryKey: ["commitment-trail", orderId], queryFn: () => api.get<LedgerEvent[]>(`/api/orders/${orderId}/commitment-ledger`), refetchInterval: 6000 });
  if (!q.data || q.data.length === 0) return null;
  return (
    <Card>
      <CardHeader><CardTitle>Commitment trail</CardTitle></CardHeader>
      <CardContent>
        <ol className="space-y-1.5 text-sm">{q.data.map((e) => (
          <li key={e.id} className="flex flex-wrap gap-x-2">
            <span className="w-24 shrink-0 text-xs tabular-nums text-slate-500">{istTime(e.at)}</span>
            <span><strong className="font-medium">{e.actor_role === "merchant" ? "You" : e.supplier_name ?? "System"}</strong> {TRAIL_LABEL[e.action] ?? e.action}
              {e.qty !== null && <span className="tabular-nums"> · {qty(e.qty)}</span>}
              {e.from_state && e.to_state && <span className="text-xs text-slate-500"> ({e.from_state} → {e.to_state})</span>}</span>
          </li>))}</ol>
        <p className="mt-2 text-[11px] text-slate-500">The same append-only record the suppliers see.</p>
      </CardContent>
    </Card>
  );
}
