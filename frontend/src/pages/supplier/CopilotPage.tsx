import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Clock } from "lucide-react";
import { Link } from "react-router-dom";
import { MethodNote, PageHeader, Stat } from "../../components/supplier/parts";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { EmptyState, ErrorState, SkeletonCard } from "../../components/ui/state";
import { api } from "../../lib/api";
import { SEVERITY_BAR, countdown, istTime, qty, type CopilotResponse, type QueueItem } from "../../lib/continuity";
import { formatINR } from "../../lib/format";
import { cn } from "../../lib/utils";

function QueueRow({ item }: { item: QueueItem }) {
  const due = countdown(item.deadline);
  return (
    <li className="flex gap-3 py-3">
      <span className={cn("mt-1 w-1 shrink-0 self-stretch rounded-full", SEVERITY_BAR[item.severity])} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            <span className="sr-only">{item.severity} priority: </span>{item.title}
          </p>
          {item.deadline && (
            <span className={cn("inline-flex items-center gap-1 text-xs tabular-nums", due.overdue || due.hours < 1 ? "font-semibold text-rose-600 dark:text-rose-400" : "text-slate-500 dark:text-slate-400")}>
              <Clock className="h-3 w-3" aria-hidden /> {due.text}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-300">{item.why}</p>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400"><span className="font-medium">If ignored:</span> {item.consequence}</p>
      </div>
      {item.action && (
        <Link to={item.action.href} className="shrink-0 self-center rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
          {item.action.label}
        </Link>
      )}
    </li>
  );
}

export function CopilotPage() {
  const q = useQuery({ queryKey: ["supplier-copilot"], queryFn: () => api.get<CopilotResponse>("/api/suppliers/me/copilot"), refetchInterval: 10_000 });

  if (q.isPending) return <div className="space-y-3"><SkeletonCard /><SkeletonCard /></div>;
  if (q.isError) return <ErrorState message="Could not load the Commitment Copilot." />;
  const { queue, answers } = q.data;
  const best = answers.best_next_action;
  const awaiting = queue.filter((i) => i.kind === "request_awaiting_decision").length;
  const invites = answers.surplus_matches_nearby_demand.length;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Commitment Copilot" title="What needs you now">
        Ranked from your recorded stock, commitments, deadlines and capacity. Every item says why, and what happens if you wait.
      </PageHeader>

      <section aria-labelledby="best-action" className="rounded-xl border border-brand-200 bg-brand-50/60 p-4 dark:border-brand-900 dark:bg-brand-950/30">
        <p id="best-action" className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-700 dark:text-brand-300">Best next action</p>
        <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-base font-semibold text-slate-900 dark:text-slate-100">{best.title}</p>
            <p className="text-sm text-slate-600 dark:text-slate-300">{best.why}</p>
          </div>
          {best.action ? (
            <Link to={best.action.href} className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-400 focus:ring-offset-2 dark:focus:ring-offset-slate-950">
              {best.action.label} <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          ) : <CheckCircle2 className="h-6 w-6 text-emerald-600" aria-label="All clear" />}
        </div>
      </section>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Requests to decide" value={awaiting} tone={awaiting ? "warn" : undefined} />
        <Stat label="Commitments at risk" value={answers.at_risk_of_missing_dispatch.length} tone={answers.at_risk_of_missing_dispatch.length ? "bad" : undefined} />
        <Stat label="SKUs short for new orders" value={answers.insufficient_stock_for_new_commitments.length} />
        <Stat label="Relay requests for you" value={invites} hint="Demand you can serve" />
      </div>

      <Card>
        <CardHeader><CardTitle>Action queue</CardTitle></CardHeader>
        <CardContent>
          {queue.length === 0
            ? <EmptyState title="Nothing needs attention" hint="No open requests, at-risk commitments, stale stock or relay requests." />
            : <ul className="divide-y divide-slate-100 dark:divide-slate-800">{queue.map((item) => <QueueRow key={`${item.kind}-${item.ref}`} item={item} />)}</ul>}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Which orders can I partly fill safely?</CardTitle></CardHeader>
          <CardContent>
            {answers.safe_partial_fulfilment.length === 0 ? <p className="text-sm text-slate-500">Every open request either fits in full or cannot be served.</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-slate-500"><th className="py-1 font-medium">Product</th><th className="font-medium">Safe / asked</th><th className="font-medium">Revenue kept</th><th className="font-medium">Forgone</th></tr></thead>
                <tbody>{answers.safe_partial_fulfilment.map((p) => (
                  <tr key={p.allocation_id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5"><Link className="text-brand-700 hover:underline dark:text-brand-400" to={`/supplier/requests?focus=${p.allocation_id}`}>{p.product_name}</Link></td>
                    <td className="tabular-nums">{qty(p.safe_qty)} / {qty(p.requested, p.unit)}</td>
                    <td className="tabular-nums">{formatINR(p.revenue_at_safe_qty)}</td>
                    <td className="tabular-nums text-slate-500">{formatINR(p.revenue_forgone)}</td>
                  </tr>))}</tbody>
              </table>
            )}
            <MethodNote>Revenue only; purchase cost is not recorded, so margin is not estimated.</MethodNote>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Where am I short for new commitments?</CardTitle></CardHeader>
          <CardContent>
            {answers.insufficient_stock_for_new_commitments.length === 0 ? <p className="text-sm text-slate-500">Free stock covers MOQ and pending requests on every listing.</p> : (
              <ul className="space-y-1.5 text-sm">{answers.insufficient_stock_for_new_commitments.map((s) => (
                <li key={s.inventory_id} className="flex justify-between gap-2">
                  <span>{s.product_name} <span className="text-slate-400">· {s.brand}</span></span>
                  <span className="tabular-nums text-slate-600 dark:text-slate-300">{qty(s.free_to_promise, s.unit)} free · {qty(s.requested_pending)} asked · MOQ {qty(s.moq)}</span>
                </li>))}</ul>
            )}
          </CardContent>
        </Card>
      </div>

      {invites > 0 && (
        <Card>
          <CardHeader><CardTitle>Nearby demand you can serve</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">{answers.surplus_matches_nearby_demand.map((d) => (
              <li key={d.invite_id} className="flex flex-wrap justify-between gap-2">
                <Link to={`/supplier/relay?focus=${d.invite_id}`} className="text-brand-700 hover:underline dark:text-brand-400">{qty(d.qty, "")} {d.product_name} needed</Link>
                <span className="text-slate-500">{d.distance_to_merchant_km} km from merchant · answer by {istTime(d.deadline)} IST</span>
              </li>))}</ul>
          </CardContent>
        </Card>
      )}
      <MethodNote>{q.data.method}</MethodNote>
    </div>
  );
}
