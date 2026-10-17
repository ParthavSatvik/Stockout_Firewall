import { useQuery } from "@tanstack/react-query";
import { MethodNote, PageHeader, Stat } from "../../components/supplier/parts";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { ErrorState, SkeletonCard } from "../../components/ui/state";
import { api } from "../../lib/api";
import { pct, qty, type Passport, type PassportMetric } from "../../lib/continuity";
import { formatDate } from "../../lib/format";
import { cn } from "../../lib/utils";

const OUTCOMES: { key: string; label: string; cls: string }[] = [
  { key: "accepted_in_full", label: "Accepted in full", cls: "bg-emerald-500" },
  { key: "partial_disclosed_upfront", label: "Partial, disclosed up front", cls: "bg-sky-500" },
  { key: "declined_upfront", label: "Declined up front", cls: "bg-slate-400" },
  { key: "broken_after_commitment", label: "Broken after commitment", cls: "bg-rose-500" },
  { key: "silent_expiry", label: "Left to expire", cls: "bg-amber-500" },
];

function MetricRow({ m }: { m: PassportMetric }) {
  const measured = m.status === "measured";
  const good = measured && m.value !== null && (m.higher_is_better ? m.value >= 0.9 : m.value <= 0.05);
  const weak = measured && m.value !== null && (m.higher_is_better ? m.value < 0.75 : m.value > 0.15);
  return (
    <tr className="border-t border-slate-100 dark:border-slate-800">
      <td className="py-2 pr-3"><p className="font-medium text-slate-900 dark:text-slate-100">{m.label}</p><p className="text-[11px] text-slate-500">{m.definition}</p></td>
      <td className="pr-3 text-right">
        {measured
          ? <span className={cn("text-lg font-semibold tabular-nums", good && "text-emerald-700 dark:text-emerald-400", weak && "text-rose-700 dark:text-rose-400")}>{pct(m.value)}</span>
          : <Badge variant="default">Insufficient history</Badge>}
      </td>
      <td className="text-right text-xs tabular-nums text-slate-500">{qty(m.numerator)} / {qty(m.denominator)}{!measured && <span className="block">{m.observations} of ≥ {m.min_sample} needed</span>}</td>
    </tr>
  );
}

export function PassportView({ data }: { data: Passport }) {
  const total = OUTCOMES.reduce((s, o) => s + (data.outcomes[o.key] ?? 0), 0);
  return (
    <div className="space-y-5">
      {data.history_status === "INSUFFICIENT_HISTORY" && (
        <div className="rounded-xl border border-slate-300 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300" role="note">
          <p className="font-semibold">Insufficient history</p><p>{data.new_supplier_policy}</p>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Requests decided" value={data.sample.requests_decided} hint={data.sample.first_observation ? `since ${formatDate(data.sample.first_observation)}` : "no observations"} />
        <Stat label="Committed" value={qty(data.committed_qty)} hint={`of ${qty(data.quoted_qty)} quoted`} />
        <Stat label="Delivered" value={qty(data.delivered_qty)} />
        <Stat label="Stock freshness" value={`${data.stock_freshness.fresh_listings}/${data.stock_freshness.listings}`} hint="listings counted in 24h" tone={data.stock_freshness.fresh_listings < data.stock_freshness.listings ? "warn" : undefined} />
      </div>

      <Card>
        <CardHeader><CardTitle>How requests were answered</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {total > 0 && (
            <div className="flex h-3 overflow-hidden rounded-full" role="img" aria-label={OUTCOMES.map((o) => `${o.label}: ${data.outcomes[o.key] ?? 0}`).join(", ")}>
              {OUTCOMES.map((o) => (data.outcomes[o.key] ?? 0) > 0 && <span key={o.key} className={o.cls} style={{ width: `${((data.outcomes[o.key] ?? 0) / total) * 100}%` }} />)}
            </div>
          )}
          <ul className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {OUTCOMES.map((o) => (
              <li key={o.key} className="flex items-center gap-2"><span className={cn("h-2.5 w-2.5 rounded-sm", o.cls)} aria-hidden />{o.label}<span className="ml-auto tabular-nums font-semibold">{data.outcomes[o.key] ?? 0}</span></li>
            ))}
          </ul>
          <MethodNote>Disclosing a shortfall when you answer is recorded separately from breaking a commitment you already made.</MethodNote>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Evidence</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[28rem] text-sm">
            <thead><tr className="text-xs text-slate-500"><th className="py-1 text-left font-medium">Measure</th><th className="pr-3 text-right font-medium">Rate</th><th className="text-right font-medium">Observed</th></tr></thead>
            <tbody>{Object.entries(data.metrics).map(([k, m]) => <MetricRow key={k} m={m} />)}</tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">Median response time: {data.median_response_minutes !== null ? `${data.median_response_minutes} min` : `insufficient history (${data.response_sample} responses)`}</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Strengths on record</CardTitle></CardHeader>
          <CardContent>{data.strengths.length ? <ul className="space-y-1 text-sm">{data.strengths.map((s) => <li key={s}>• {s}</li>)}</ul> : <p className="text-sm text-slate-500">None measurable yet.</p>}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>What would strengthen this passport</CardTitle></CardHeader>
          <CardContent>{data.improvements.length ? <ul className="space-y-1 text-sm">{data.improvements.map((s) => <li key={s}>• {s}</li>)}</ul> : <p className="text-sm text-slate-500">Nothing flagged by the recorded evidence.</p>}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Provenance</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
          <ul className="space-y-0.5">{data.provenance.map((p) => <li key={p}>• {p}</li>)}</ul>
          <p>Planner reliability score: <strong>{data.planner_reliability.score.toFixed(2)}</strong> ({data.planner_reliability.confidence} confidence, {data.planner_reliability.sample_size} commitments). {data.planner_reliability.note}</p>
          <MethodNote>{data.method}</MethodNote>
        </CardContent>
      </Card>
    </div>
  );
}

export function PassportPage() {
  const q = useQuery({ queryKey: ["passport"], queryFn: () => api.get<Passport>("/api/suppliers/me/passport") });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Supplier Trust Passport" title={q.data ? q.data.supplier_name : "Trust Passport"}>
        Evidence merchants can inspect: what you committed, what you delivered, when, and at what price. No star rating; every rate shows its denominator.
      </PageHeader>
      {q.isPending && <SkeletonCard />}
      {q.isError && <ErrorState message="Could not load your passport." />}
      {q.data && <PassportView data={q.data} />}
    </div>
  );
}
