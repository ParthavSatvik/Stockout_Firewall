import type { ReactNode } from "react";
import { Badge } from "../ui/badge";
import { Tooltip } from "../ui/tooltip";
import { cn } from "../../lib/utils";
import {
  FRESHNESS_BADGE, RISK_BADGE, STAGE_LABEL, qty,
  type Freshness, type RiskAssessment, type Stage,
} from "../../lib/continuity";

export function PageHeader({ eyebrow, title, children, actions }: { eyebrow?: string; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-600 dark:text-brand-400">{eyebrow}</p>}
        <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
        {children && <p className="mt-0.5 max-w-2xl text-sm text-slate-500 dark:text-slate-400">{children}</p>}
      </div>
      {actions}
    </div>
  );
}

/** The free-to-promise arithmetic, shown term by term so every number is traceable. */
export function PromiseEquation({ onHand, committed, safety, free, unit, compact }: {
  onHand: number; committed: number; safety: number; free: number; unit: string; compact?: boolean;
}) {
  const term = (label: string, value: number, cls = "") => (
    <div className={cn("flex flex-col", compact ? "min-w-[3.5rem]" : "min-w-[4.5rem]")}>
      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</span>
      <span className={cn("tabular-nums font-semibold text-slate-900 dark:text-slate-100", compact ? "text-sm" : "text-lg", cls)}>{qty(value)}</span>
    </div>
  );
  const op = (s: string) => <span className={cn("self-end pb-0.5 text-slate-400", compact ? "text-sm" : "text-lg")}>{s}</span>;
  return (
    <div className="flex flex-wrap items-end gap-x-2 gap-y-1" aria-label={`${onHand} on hand minus ${committed} committed minus ${safety} safety stock equals ${free} ${unit} free to promise`}>
      {term("On hand", onHand)}
      {op("−")}
      {term("Committed", committed)}
      {op("−")}
      {term("Safety", safety)}
      {op("=")}
      <div className={cn("flex flex-col rounded-md px-2 py-0.5", free > 0 ? "bg-emerald-100 dark:bg-emerald-950/60" : "bg-rose-100 dark:bg-rose-950/60")}>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Free to promise</span>
        <span className={cn("tabular-nums font-bold", compact ? "text-sm" : "text-lg", free > 0 ? "text-emerald-800 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300")}>
          {qty(free, unit)}
        </span>
      </div>
    </div>
  );
}

const TRACK: Stage[] = ["quote", "reserved", "picking", "ready", "dispatched", "delivered", "reconciled"];

export function StageTrack({ stage, times }: { stage: Stage; times?: Partial<Record<Stage, string>> }) {
  const at = TRACK.indexOf(stage);
  return (
    <ol className="flex items-center gap-1" aria-label={`Stage: ${STAGE_LABEL[stage]}`}>
      {TRACK.map((s, i) => (
        <li key={s} className="flex items-center gap-1">
          <Tooltip content={`${STAGE_LABEL[s]}${times?.[s] ? ` · ${new Date(times[s]!).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}` : ""}`}>
            <span
              className={cn(
                "block h-2 w-2 rounded-full",
                i < at && "bg-brand-500",
                i === at && "h-2.5 w-2.5 bg-brand-600 ring-2 ring-brand-200 dark:ring-brand-900",
                i > at && "bg-slate-200 dark:bg-slate-700",
              )}
            />
          </Tooltip>
          {i < TRACK.length - 1 && <span className={cn("h-px w-2.5", i < at ? "bg-brand-400" : "bg-slate-200 dark:bg-slate-700")} />}
        </li>
      ))}
      <span className="ml-1.5 text-xs font-medium text-slate-700 dark:text-slate-300">{STAGE_LABEL[stage]}</span>
    </ol>
  );
}

export function RiskBadge({ risk }: { risk: RiskAssessment | null }) {
  if (!risk) return null;
  const label = risk.level.replace("_", " ");
  const content = risk.factors.length
    ? <span className="block space-y-0.5 text-left">{risk.factors.map((f) => <span key={f.factor} className="block">+{f.points} {f.detail}</span>)}<span className="block pt-1 opacity-70">Rule-based points · {risk.confidence} evidence</span></span>
    : <span>No risk factors recorded · {risk.confidence} evidence</span>;
  return (
    <Tooltip content={content}>
      <Badge variant={RISK_BADGE[risk.level]} tabIndex={0} className="cursor-help capitalize">{label}{risk.score > 0 && ` · ${risk.score}`}</Badge>
    </Tooltip>
  );
}

export function FreshnessBadge({ freshness }: { freshness: Freshness | null }) {
  if (!freshness) return null;
  const age = freshness.age_hours === null ? "never counted" : freshness.age_hours < 1 ? "counted <1h ago" : `counted ${Math.round(freshness.age_hours)}h ago`;
  return (
    <Tooltip content={freshness.excluded_from_new_plans ? "Not confirmed in 24h: excluded from new merchant plans" : `Source: ${freshness.source.replace(/_/g, " ")}`}>
      <Badge variant={FRESHNESS_BADGE[freshness.status]} tabIndex={0} className="cursor-help">{age}</Badge>
    </Tooltip>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "warn" | "bad" }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className={cn("mt-0.5 text-xl font-semibold tabular-nums text-slate-900 dark:text-slate-100", tone === "warn" && "text-amber-700 dark:text-amber-400", tone === "bad" && "text-rose-700 dark:text-rose-400")}>{value}</p>
      {hint && <p className="text-[11px] text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}

export function MethodNote({ children }: { children: ReactNode }) {
  return <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-500">{children}</p>;
}
