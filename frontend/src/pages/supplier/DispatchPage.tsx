import { useT, type TKey } from "../../lib/i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Clock, PackageCheck, PackageOpen, Truck, Workflow } from "lucide-react";
import { MethodNote, PageHeader, RiskBadge } from "../../components/supplier/parts";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import { Input, Label } from "../../components/ui/input";
import { ErrorState, SkeletonCard } from "../../components/ui/state";
import { useToast } from "../../components/ui/toast";
import { api, ApiError } from "../../lib/api";
import { countdown, istTime, qty, type CommitmentRow, type DispatchBoard } from "../../lib/continuity";
import { cn } from "../../lib/utils";

const COLUMNS = [
  { key: "reserved", title: "sup.reserved", hint: "Stock held, not yet picked" },
  { key: "picking", title: "sup.picking", hint: "Being weighed and packed" },
  { key: "ready", title: "sup.ready", hint: "Waiting for the vehicle" },
  { key: "dispatched", title: "sup.dispatched", hint: "On the way to the merchant" },
] as const;

const NEXT: Record<string, { label: TKey; path: string; body?: object; icon: typeof Truck }> = {
  reserved: { label: "sup.startPicking", path: "stage", body: { stage: "picking" }, icon: PackageOpen },
  picking: { label: "sup.markReady", path: "stage", body: { stage: "ready" }, icon: PackageCheck },
  ready: { label: "sup.dispatch", path: "dispatch", icon: Truck },
  dispatched: { label: "sup.markDelivered", path: "deliver", icon: PackageCheck },
};

function CommitmentCard({ row, onAdvance, onRelay, busy }: { row: CommitmentRow; onAdvance: () => void; onRelay: () => void; busy: boolean }) {
  const { t } = useT();
  const due = countdown(row.ready_by);
  const next = NEXT[row.stage];
  const Icon = next?.icon ?? Truck;
  return (
    <li className={cn("rounded-lg border bg-white p-3 dark:bg-slate-900",
      row.risk?.level === "critical" ? "border-rose-300 dark:border-rose-800" : row.risk?.level === "at_risk" ? "border-amber-300 dark:border-amber-800" : "border-slate-200 dark:border-slate-800")}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{qty(row.committed_qty, row.unit)} {row.product_name}</p>
        <RiskBadge risk={row.risk} />
      </div>
      <p className="text-xs text-slate-500">Order #{row.order_ref}</p>
      {row.ready_by && (
        <p className={cn("mt-1 flex items-center gap-1 text-xs tabular-nums", due.overdue && row.stage !== "dispatched" ? "font-semibold text-rose-600 dark:text-rose-400" : "text-slate-600 dark:text-slate-300")}>
          <Clock className="h-3 w-3" aria-hidden /> Ready-by {istTime(row.ready_by)} IST · {due.text}
        </p>
      )}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {next && <Button size="sm" variant={row.stage === "ready" ? "default" : "outline"} disabled={busy} onClick={onAdvance}><Icon className="h-3.5 w-3.5" aria-hidden />{t(next.label)}</Button>}
        {row.stage !== "dispatched" && <Button size="sm" variant="ghost" disabled={busy} onClick={onRelay} title="Report that you can no longer supply all of it"><Workflow className="h-3.5 w-3.5" aria-hidden />{t("sup.relayGap")}</Button>}
      </div>
    </li>
  );
}

export function DispatchPage() {
  const { t } = useT();
  const qc = useQueryClient();
  const { toast } = useToast();
  const q = useQuery({ queryKey: ["dispatch-board"], queryFn: () => api.get<DispatchBoard>("/api/suppliers/me/dispatch-board"), refetchInterval: 10_000 });
  const [relayRow, setRelayRow] = useState<CommitmentRow | null>(null);
  const [keep, setKeep] = useState("");
  const [reason, setReason] = useState("");

  const refresh = () => ["dispatch-board", "supplier-copilot", "promise-ledger", "supplier-allocations", "relays"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const fail = (e: unknown) => toast({ title: "Not saved", description: e instanceof ApiError ? e.message : "Request failed", variant: "error" });
  const advance = useMutation({
    mutationFn: (row: CommitmentRow) => { const n = NEXT[row.stage]; return api.post(`/api/allocations/${row.allocation_id}/${n.path}`, n.body); },
    onSuccess: refresh, onError: fail,
  });
  const relay = useMutation({
    mutationFn: () => api.post(`/api/allocations/${relayRow!.allocation_id}/relay`, { commit_qty_base_unit: Number(keep), reason, response_window_minutes: 120 }),
    onSuccess: () => { setRelayRow(null); refresh(); toast({ title: "Disclosed and relayed", description: "Partners were asked to cover the gap; the merchant approves the result.", variant: "success" }); },
    onError: fail,
  });

  if (q.isPending) return <div className="grid grid-cols-1 gap-3 md:grid-cols-4"><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  if (q.isError) return <ErrorState message="Could not load the dispatch board." />;
  const board = q.data;
  const load = board.capacity_kg_per_day ? board.due_today_kg / board.capacity_kg_per_day : 0;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Fulfilment" title={t("sup.dispatchTitle")}
        actions={
          <div className="w-full min-w-[14rem] sm:w-64" aria-label={`Due today ${board.due_today_kg} of ${board.capacity_kg_per_day} kilograms capacity`}>
            <div className="flex justify-between text-xs text-slate-600 dark:text-slate-300"><span>Due today (not dispatched)</span><span className="tabular-nums">{qty(board.due_today_kg)} / {qty(board.capacity_kg_per_day, "kg")}</span></div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
              <div className={cn("h-full rounded-full", load > 1 ? "bg-rose-500" : load > 0.85 ? "bg-amber-500" : "bg-emerald-500")} style={{ width: `${Math.min(100, load * 100)}%` }} />
            </div>
          </div>
        }>
        Commitments ordered by ready-by time. Advance each one as it moves; risk badges list the exact rule that fired.
      </PageHeader>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((col) => {
          const rows = board.columns[col.key];
          return (
            <section key={col.key} aria-labelledby={`col-${col.key}`} className="rounded-xl bg-slate-50 p-2.5 dark:bg-slate-900/50">
              <header className="mb-2 px-1">
                <h2 id={`col-${col.key}`} className="flex items-center justify-between text-sm font-semibold text-slate-800 dark:text-slate-200">{t(col.title)}<span className="text-xs font-normal tabular-nums text-slate-500">{rows.length}</span></h2>
                <p className="text-[11px] text-slate-500">{col.hint}</p>
              </header>
              {rows.length === 0 ? <p className="px-1 py-4 text-center text-xs text-slate-400">{t("sup.nothingHere")}</p> : (
                <ul className="space-y-2">{rows.map((r) => (
                  <CommitmentCard key={r.allocation_id} row={r} busy={advance.isPending}
                    onAdvance={() => advance.mutate(r)}
                    onRelay={() => { setRelayRow(r); setKeep(""); setReason(""); }} />
                ))}</ul>
              )}
            </section>
          );
        })}
      </div>
      <MethodNote>Operating hours {board.operating_hours} IST. Delivery capacity is the daily figure on your profile; litre products are not counted against it.</MethodNote>

      <Dialog open={!!relayRow} onClose={() => setRelayRow(null)} title="Disclose a shortfall and relay the gap"
        description={relayRow ? `You committed ${relayRow.committed_qty} ${relayRow.unit}. Say how much you can still supply; eligible partners are asked for the rest. This is recorded as a broken commitment, so disclose as early as possible.` : ""}
        footer={<><Button variant="outline" onClick={() => setRelayRow(null)}>Cancel</Button>
          <Button disabled={relay.isPending || keep === "" || Number(keep) < 0 || (relayRow ? Number(keep) >= (relayRow.committed_qty ?? 0) : true) || reason.trim().length < 3} onClick={() => relay.mutate()}>Open relay</Button></>}>
        <div className="space-y-2">
          <Label htmlFor="keep-qty">Quantity you can still supply</Label>
          <Input id="keep-qty" type="number" min={0} value={keep} onChange={(e) => setKeep(e.target.value)} />
          <Label htmlFor="gap-reason">What happened</Label>
          <Input id="gap-reason" placeholder="e.g. 20 kg failed quality check" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
      </Dialog>
    </div>
  );
}
