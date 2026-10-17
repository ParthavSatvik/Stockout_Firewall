import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, Clock, Workflow, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { MethodNote, PageHeader } from "../../components/supplier/parts";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input, Label } from "../../components/ui/input";
import { EmptyState, ErrorState, Spinner } from "../../components/ui/state";
import { Tabs } from "../../components/ui/tabs";
import { useToast } from "../../components/ui/toast";
import { api, ApiError } from "../../lib/api";
import { countdown, fromLocalInput, istTime, qty, toLocalInput, type RelayCandidate, type RelayView } from "../../lib/continuity";
import { formatINR } from "../../lib/format";
import { cn } from "../../lib/utils";

const PROTOCOL = ["Shortfall disclosed", "Partners invited", "Partners respond", "Merchant approves", "Stock reserved"];

function protocolStep(r: RelayView): number {
  if (r.status === "approved") return 5;
  if (r.status !== "open") return -1;
  const answered = (r.invites ?? []).some((i) => i.status !== "invited") || (r.invite && r.invite.status !== "invited");
  return answered ? 3 : 2;
}

function ProtocolTrack({ relay }: { relay: RelayView }) {
  const step = protocolStep(relay);
  return (
    <ol className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]" aria-label="Relay protocol progress">
      {PROTOCOL.map((label, i) => (
        <li key={label} className={cn("flex items-center gap-1", i < step ? "text-brand-700 dark:text-brand-300" : "text-slate-400")}>
          <span className={cn("flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold", i < step ? "bg-brand-600 text-white" : "bg-slate-200 dark:bg-slate-800")}>{i + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}

const STATUS_BADGE: Record<string, "default" | "success" | "warning" | "danger" | "info"> = {
  open: "warning", approved: "success", declined: "default", fallback: "info", expired: "danger", superseded: "default",
  invited: "warning", accepted: "success", modified: "info", reserved: "success", not_selected: "default", reservation_failed: "danger",
};

function IncomingCard({ relay, focused }: { relay: RelayView; focused: boolean }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const inv = relay.invite!;
  const [qtyText, setQtyText] = useState(String(Math.min(relay.outstanding_qty, Number(inv.why_eligible.free_to_promise ?? relay.outstanding_qty))));
  const [price, setPrice] = useState(String(inv.why_eligible.listed_price ?? ""));
  const [readyBy, setReadyBy] = useState(toLocalInput(null));
  const [note, setNote] = useState("");
  const open = relay.status === "open" && ["invited", "accepted", "modified"].includes(inv.status);
  const respond = useMutation({
    mutationFn: (action: "accept" | "modify" | "decline") => api.post(`/api/relays/invites/${inv.id}/respond`, {
      action, qty_base_unit: action === "modify" ? Number(qtyText) : undefined, price_per_base_unit: action === "modify" ? Number(price) : undefined,
      ready_by: action === "decline" ? undefined : fromLocalInput(readyBy), note,
    }),
    onSuccess: (_, action) => {
      ["relays", "supplier-copilot"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast({ title: action === "decline" ? "Declined" : "Quote sent", description: action === "decline" ? undefined : "Nothing is reserved until the merchant approves; then your stock is reserved automatically.", variant: "success" });
    },
    onError: (e) => toast({ title: "Not sent", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" }),
  });
  const due = countdown(relay.expires_at);
  const overCeiling = relay.price_ceiling !== null && Number(price) > relay.price_ceiling;
  const isFullListed = Number(qtyText) === relay.outstanding_qty && Number(price) === Number(inv.why_eligible.listed_price);

  return (
    <Card className={cn(focused && "ring-2 ring-brand-400")}>
      <CardContent className="space-y-3 pt-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-base font-semibold text-slate-900 dark:text-slate-100">{qty(relay.outstanding_qty, relay.unit)} {relay.product_name} needed</p>
            <p className="text-xs text-slate-500">Relayed by {relay.origin_supplier_name} · {relay.merchant}</p>
          </div>
          <div className="text-right">
            <Badge variant={STATUS_BADGE[inv.status] ?? "default"}>{inv.status.replace("_", " ")}</Badge>
            {relay.status === "open" && <p className={cn("mt-1 flex items-center justify-end gap-1 text-xs", due.hours < 0.5 ? "text-rose-600" : "text-slate-500")}><Clock className="h-3 w-3" aria-hidden />answer {due.text}</p>}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div><dt className="text-slate-500">Your free to promise</dt><dd className="font-semibold tabular-nums">{qty(Number(inv.why_eligible.free_to_promise), relay.unit)}</dd></div>
          <div><dt className="text-slate-500">Merchant price ceiling</dt><dd className="font-semibold tabular-nums">{relay.price_ceiling !== null ? formatINR(relay.price_ceiling, true) : "none"}</dd></div>
          <div><dt className="text-slate-500">Distance to merchant</dt><dd className="font-semibold tabular-nums">{inv.why_eligible.distance_to_merchant_km} km</dd></div>
          <div><dt className="text-slate-500">Needed by</dt><dd className="font-semibold">{istTime(relay.needed_by)} IST</dd></div>
        </dl>
        {relay.required_brand && <p className="text-xs text-amber-700 dark:text-amber-400">Merchant did not allow substitution: brand {relay.required_brand} only.</p>}
        {open ? (
          <div className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="space-y-1"><Label htmlFor={`q-${inv.id}`}>Quantity ({relay.unit})</Label><Input id={`q-${inv.id}`} type="number" min={1} step={1} max={relay.outstanding_qty} value={qtyText} onChange={(e) => setQtyText(e.target.value)} /></div>
              <div className="space-y-1"><Label htmlFor={`p-${inv.id}`}>Price per {relay.unit} (₹)</Label><Input id={`p-${inv.id}`} type="number" min={0} step="0.5" value={price} onChange={(e) => setPrice(e.target.value)} /></div>
              <div className="space-y-1"><Label htmlFor={`r-${inv.id}`}>Ready by</Label><Input id={`r-${inv.id}`} type="datetime-local" value={readyBy} onChange={(e) => setReadyBy(e.target.value)} /></div>
            </div>
            <Input aria-label="Note" placeholder="Note for the requesting supplier (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
            {overCeiling && <p className="text-xs text-amber-700 dark:text-amber-400">Above the merchant's approved ceiling: your quote will be shown but cannot be selected.</p>}
            <div className="flex flex-wrap gap-2">
              {isFullListed
                ? <Button size="sm" variant="success" disabled={respond.isPending} onClick={() => respond.mutate("accept")}><Check className="h-3.5 w-3.5" aria-hidden />Accept {qty(relay.outstanding_qty, relay.unit)} at listed price</Button>
                : <Button size="sm" disabled={respond.isPending || !qtyText || !price} onClick={() => respond.mutate("modify")}>Send quote: {qtyText} {relay.unit} @ ₹{price}</Button>}
              <Button size="sm" variant="ghost" disabled={respond.isPending} onClick={() => respond.mutate("decline")}><X className="h-3.5 w-3.5" aria-hidden />Decline</Button>
            </div>
            <MethodNote>A quote is a commitment conditional on merchant approval. Your stock is reserved only at that moment, and only if it is still free.</MethodNote>
          </div>
        ) : (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {inv.offered_qty !== null ? `You quoted ${qty(inv.offered_qty, relay.unit)} at ${formatINR(inv.offered_price ?? 0, true)}.` : "No quote sent."} {relay.resolution_note}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Candidates({ relayId }: { relayId: string }) {
  const q = useQuery({ queryKey: ["relays", "candidates", relayId], queryFn: () => api.get<RelayCandidate[]>(`/api/relays/${relayId}/candidates`) });
  if (q.isPending) return <Spinner label="Loading eligibility…" />;
  if (q.isError) return null;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-slate-600 hover:text-slate-900 dark:text-slate-300">Why these partners? ({q.data.filter((c) => c.eligible).length} eligible of {q.data.length})</summary>
      <ul className="mt-2 space-y-1">{q.data.map((c) => (
        <li key={c.inventory_id} className="flex flex-wrap gap-x-2">
          <span className={c.eligible ? "font-medium text-emerald-700 dark:text-emerald-400" : "text-slate-500"}>{c.eligible ? "✓" : "✗"} {c.supplier_name}</span>
          <span className="text-slate-500">{c.eligible ? `${qty(c.free_to_promise)} free · ₹${c.listed_price} · ${c.distance_to_merchant_km} km · reliability ${c.reliability_score.toFixed(2)} (${c.reliability_confidence})` : c.reasons.join("; ")}</span>
        </li>))}</ul>
    </details>
  );
}

function OutgoingCard({ relay }: { relay: RelayView }) {
  const due = countdown(relay.expires_at);
  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-base font-semibold text-slate-900 dark:text-slate-100">You kept {qty(relay.origin_committed_qty, relay.unit)} · relayed {qty(relay.outstanding_qty, relay.unit)} {relay.product_name}</p>
            <p className="text-xs text-slate-500">{relay.reason} · opened {istTime(relay.created_at)} IST</p>
          </div>
          <div className="text-right"><Badge variant={STATUS_BADGE[relay.status] ?? "default"}>{relay.status}</Badge>
            {relay.status === "open" && <p className="mt-1 text-xs text-slate-500">closes {due.text}</p>}</div>
        </div>
        <ProtocolTrack relay={relay} />
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-slate-500"><th className="py-1 font-medium">Partner</th><th className="font-medium">Response</th><th className="font-medium">Quote</th><th className="hidden font-medium sm:table-cell">Ready by</th></tr></thead>
          <tbody>{(relay.invites ?? []).map((i) => (
            <tr key={i.id} className="border-t border-slate-100 dark:border-slate-800">
              <td className="py-1.5">{i.supplier_name}</td>
              <td><Badge variant={STATUS_BADGE[i.status] ?? "default"}>{i.status.replace("_", " ")}</Badge></td>
              <td className="tabular-nums">{i.offered_qty !== null ? `${qty(i.offered_qty)} @ ${formatINR(i.offered_price ?? 0, true)}` : "—"}</td>
              <td className="hidden tabular-nums sm:table-cell">{istTime(i.offered_ready_by)}</td>
            </tr>))}</tbody>
        </table>
        {relay.resolution_note && <p className="text-sm text-slate-600 dark:text-slate-300">{relay.resolution_note}</p>}
        <Candidates relayId={relay.id} />
      </CardContent>
    </Card>
  );
}

export function RelayPage() {
  const [params] = useSearchParams();
  const focus = params.get("focus");
  const q = useQuery({ queryKey: ["relays"], queryFn: () => api.get<{ outgoing: RelayView[]; incoming: RelayView[] }>("/api/relays/mine"), refetchInterval: 8000 });
  const pendingIncoming = q.data?.incoming.filter((r) => r.status === "open" && r.invite?.status === "invited").length ?? 0;
  const [tab, setTab] = useState("incoming");

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Supply Relay Protocol" title="Cover each other's shortfalls">
        When a wholesaler can supply only part of an order, it hands the exact gap to eligible partners instead of leaving the merchant to start over.
        Partners quote; the merchant approves; stock is reserved only then.
      </PageHeader>
      <Tabs value={tab} onChange={setTab} items={[
        { value: "incoming", label: "Requests to me", badge: pendingIncoming },
        { value: "outgoing", label: "My relays", badge: q.data?.outgoing.filter((r) => r.status === "open").length },
      ]} />
      {q.isPending && <Spinner label="Loading relays…" />}
      {q.isError && <ErrorState message="Could not load relays." />}
      {q.data && tab === "incoming" && (q.data.incoming.length === 0
        ? <EmptyState icon={<Workflow className="h-8 w-8" />} title="No relay requests" hint="You are invited only when your recorded free stock, price, freshness and reliability fit the merchant's policy." />
        : <div className="space-y-3">{q.data.incoming.map((r) => <IncomingCard key={r.id} relay={r} focused={r.invite?.id === focus} />)}</div>)}
      {q.data && tab === "outgoing" && (q.data.outgoing.length === 0
        ? <EmptyState icon={<Workflow className="h-8 w-8" />} title="You have not opened a relay" hint="From an incoming request, commit what you can and relay the rest." />
        : <div className="space-y-3">{q.data.outgoing.map((r) => <OutgoingCard key={r.id} relay={r} />)}</div>)}
      <Card>
        <CardHeader><CardTitle>Protocol safeguards</CardTitle></CardHeader>
        <CardContent>
          <ul className="grid gap-1 text-xs text-slate-600 sm:grid-cols-2 dark:text-slate-300">
            <li>• Partners are invited only from recorded, fresh stock that fits the merchant's price ceiling, brand rule and reliability floor.</li>
            <li>• A quote above the merchant's approved ceiling is shown but can never be selected.</li>
            <li>• The merchant's remaining budget and supplier limit are enforced by the same optimizer as automatic recovery.</li>
            <li>• Partners never see the merchant's identity or other partners' quotes.</li>
            <li>• If the window closes or the merchant declines, open-market recovery takes over automatically.</li>
            <li>• Every step is written to an append-only commitment ledger shared with the merchant.</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
