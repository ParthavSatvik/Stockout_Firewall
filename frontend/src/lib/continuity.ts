// Supplier Continuity Network: PromiseGuard, Supply Relay, Commitment Copilot, Trust Passport.
// Every number here comes from the backend; the client never computes a commitment.

export type GuardStatus =
  | "SAFE_TO_COMMIT"
  | "PARTIAL_COMMITMENT_RECOMMENDED"
  | "DELIVERY_WINDOW_AT_RISK"
  | "COMMITMENT_CONFLICT"
  | "NO_FREE_STOCK"
  | "INSUFFICIENT_DATA";

export interface Freshness {
  confirmed_at: string | null;
  source: "stock_count" | "last_listing_edit";
  age_hours: number | null;
  status: "fresh" | "aging" | "stale" | "unknown";
  excluded_from_new_plans: boolean;
}

export interface InventoryPosition {
  inventory_id: string;
  product_id: string;
  product_name: string;
  unit: string;
  brand: string;
  pack_size: number;
  price_per_base_unit: number;
  moq_base_unit: number;
  is_available: boolean;
  on_hand: number;
  reported_on_hand: number | null;
  committed: number;
  safety_stock: number;
  uncommitted: number;
  free_to_promise: number;
  requested_pending: number;
  in_transit: number;
  delivered: number;
  oversubscribed_by: number;
  drift_qty: number;
  freshness: Freshness;
  formula: string;
}

export interface GuardCheck {
  rule: string;
  ok: boolean;
  detail: string;
}

export interface GuardAssessment {
  status: GuardStatus;
  label: string;
  headline?: string;
  requested: number;
  unit?: string;
  max_feasible_qty: number;
  shortfall_qty?: number;
  pack_breakdown?: { pack_size: number; full_packs: number; loose_qty: number };
  unit_price?: number;
  revenue_at_max?: number;
  revenue_forgone?: number;
  margin_note?: string;
  suggested_ready_by?: string | null;
  suggestion_basis?: string;
  position?: InventoryPosition;
  checks: GuardCheck[];
  consequence_if_ignored?: string;
  basis?: string;
}

export interface RiskFactor {
  factor: string;
  points: number;
  at: string | null;
  detail: string;
}

export interface RiskAssessment {
  level: "on_track" | "watch" | "at_risk" | "critical";
  score: number;
  factors: RiskFactor[];
  confidence: "low" | "medium" | "high";
  confidence_basis: string;
  method: string;
}

export type Stage = "quote" | "reserved" | "picking" | "ready" | "dispatched" | "delivered" | "reconciled";

export interface CommitmentRow {
  allocation_id: string;
  order_ref: string;
  product_name: string;
  unit: string;
  requested_qty: number;
  committed_qty: number | null;
  unit_price: number;
  status: string;
  stage: Stage;
  stage_times: Partial<Record<Stage, string>>;
  ready_by: string | null;
  quote_valid_until: string | null;
  received_qty: number | null;
  stock_freshness: Freshness | null;
  risk: RiskAssessment | null;
  inventory_id: string | null;
  route_duration_minutes: number | null;
}

export interface PromiseLedger {
  inventory: InventoryPosition[];
  commitments: CommitmentRow[];
  lifecycle: Stage[];
  definitions: Record<string, string>;
}

export interface QueueItem {
  kind: string;
  severity: "critical" | "high" | "medium" | "low";
  deadline: string | null;
  title: string;
  why: string;
  consequence: string;
  action: { label: string; href: string } | null;
  evidence: string[];
  ref: string;
}

export interface CopilotResponse {
  generated_at: string;
  queue: QueueItem[];
  answers: {
    needs_attention_now: QueueItem[];
    at_risk_of_missing_dispatch: { allocation_id: string; product_name: string; qty: number; ready_by: string | null; stage: Stage; risk: RiskAssessment }[];
    insufficient_stock_for_new_commitments: { inventory_id: string; product_name: string; brand: string; free_to_promise: number; moq: number; requested_pending: number; unit: string }[];
    safe_partial_fulfilment: { allocation_id: string; product_name: string; requested: number; safe_qty: number; revenue_at_safe_qty: number; revenue_forgone: number; unit: string }[];
    surplus_matches_nearby_demand: { invite_id: string; product_name: string; qty: number; deadline: string; distance_to_merchant_km: number | null }[];
    best_next_action: { title: string; why: string; action: { label: string; href: string } | null };
  };
  method: string;
}

export interface DispatchBoard {
  columns: Record<"reserved" | "picking" | "ready" | "dispatched", CommitmentRow[]>;
  capacity_kg_per_day: number;
  due_today_kg: number;
  operating_hours: string;
}

export interface PassportMetric {
  label: string;
  value: number | null;
  numerator: number;
  denominator: number;
  observations: number;
  status: "measured" | "INSUFFICIENT_HISTORY";
  min_sample: number;
  definition: string;
  higher_is_better: boolean;
}

export interface Passport {
  supplier_id: string;
  supplier_name: string;
  city: string;
  sample: { requests_decided: number; commitments: number; awaiting_decision: number; first_observation: string | null; last_observation: string | null };
  history_status: "measured" | "INSUFFICIENT_HISTORY";
  new_supplier_policy: string;
  outcomes: Record<string, number>;
  quoted_qty: number;
  committed_qty: number;
  delivered_qty: number;
  metrics: Record<string, PassportMetric>;
  median_response_minutes: number | null;
  response_sample: number;
  stock_freshness: { fresh_listings: number; listings: number };
  planner_reliability: { score: number; confidence: string; sample_size: number; note: string };
  strengths: string[];
  improvements: string[];
  provenance: string[];
  method: string;
}

export interface RelayInviteView {
  id: string;
  supplier_id: string;
  supplier_name: string;
  status: string;
  offered_qty: number | null;
  offered_price: number | null;
  offered_ready_by: string | null;
  note: string;
  responded_at: string | null;
  eligibility: Record<string, number | string | null>;
}

export interface RelayPreview {
  available: boolean;
  reason?: string;
  is_feasible?: boolean;
  lines?: { supplier_name: string; qty: number; unit_price: number; line_cost: number; distance_km: number; ready_by: string | null }[];
  outstanding?: number;
  covered?: number;
  uncovered?: number;
  added_product_cost?: number;
  added_delivery_cost?: number;
  current_landed_cost?: number;
  new_landed_cost?: number;
  budget_cap?: number | null;
  budget_remaining_for_recovery?: number | null;
  price_ceiling?: number | null;
  max_suppliers?: number;
  infeasible_reasons?: string[];
  excluded_quotes?: { supplier_name: string; reason: string }[];
  policy_note?: string;
}

export interface RelayView {
  id: string;
  status: "open" | "approved" | "declined" | "fallback" | "expired" | "superseded" | "cancelled";
  product_name: string;
  unit: string;
  outstanding_qty: number;
  price_ceiling: number | null;
  required_brand: string | null;
  needed_by: string | null;
  expires_at: string;
  created_at: string;
  resolution_note: string;
  resolved_at: string | null;
  origin_supplier_name: string;
  origin_committed_qty: number;
  reason: string;
  order_id?: string;
  invites?: RelayInviteView[];
  invite?: {
    id: string;
    status: string;
    offered_qty: number | null;
    offered_price: number | null;
    offered_ready_by: string | null;
    note: string;
    responded_at: string | null;
    why_eligible: Record<string, number | string | null>;
  };
  merchant?: string;
  preview?: RelayPreview | null;
}

export interface RelayCandidate {
  supplier_id: string;
  supplier_name: string;
  inventory_id: string;
  brand: string;
  free_to_promise: number;
  moq: number;
  listed_price: number;
  reliability_score: number;
  reliability_confidence: string;
  reliability_sample_size: number;
  distance_to_merchant_km: number;
  estimated_travel_minutes: number;
  stock_freshness: string;
  eligible: boolean;
  reasons: string[];
}

export interface LedgerEvent {
  id: string;
  at: string;
  action: string;
  actor_role: string;
  supplier_name: string | null;
  from_state: string | null;
  to_state: string | null;
  qty: number | null;
  reason: string;
  payload: Record<string, unknown>;
  allocation_id: string | null;
  relay_id: string | null;
}

// ---------------------------------------------------------------- presentation

export const GUARD_TONE: Record<GuardStatus, { tone: "ok" | "warn" | "bad" | "muted"; short: string }> = {
  SAFE_TO_COMMIT: { tone: "ok", short: "Safe to commit" },
  PARTIAL_COMMITMENT_RECOMMENDED: { tone: "warn", short: "Partial recommended" },
  DELIVERY_WINDOW_AT_RISK: { tone: "warn", short: "Window at risk" },
  COMMITMENT_CONFLICT: { tone: "bad", short: "Commitment conflict" },
  NO_FREE_STOCK: { tone: "bad", short: "No free stock" },
  INSUFFICIENT_DATA: { tone: "muted", short: "Insufficient data" },
};

export const TONE_CLASS = {
  ok: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
  warn: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
  bad: "border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200",
  muted: "border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200",
} as const;

export const SEVERITY_BAR: Record<QueueItem["severity"], string> = {
  critical: "bg-rose-600",
  high: "bg-amber-500",
  medium: "bg-sky-500",
  low: "bg-slate-300 dark:bg-slate-600",
};

export const RISK_BADGE: Record<RiskAssessment["level"], "success" | "info" | "warning" | "danger"> = {
  on_track: "success",
  watch: "info",
  at_risk: "warning",
  critical: "danger",
};

export const FRESHNESS_BADGE: Record<Freshness["status"], "success" | "info" | "warning" | "danger"> = {
  fresh: "success",
  aging: "info",
  stale: "danger",
  unknown: "warning",
};

export const STAGE_LABEL: Record<Stage, string> = {
  quote: "Quote",
  reserved: "Reserved",
  picking: "Picking",
  ready: "Ready",
  dispatched: "Dispatched",
  delivered: "Delivered",
  reconciled: "Reconciled",
};

export function qty(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "—";
  const v = Number.isInteger(value) ? value : Math.round(value * 100) / 100;
  return unit ? `${v} ${unit}` : `${v}`;
}

/** "in 2h 10m" / "35m ago" relative to now, for deadlines. */
export function countdown(iso: string | null | undefined, now = Date.now()): { text: string; overdue: boolean; hours: number } {
  if (!iso) return { text: "no deadline", overdue: false, hours: Infinity };
  const diff = new Date(iso).getTime() - now;
  const mins = Math.round(Math.abs(diff) / 60000);
  const text = mins < 60 ? `${mins}m` : mins < 48 * 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${Math.round(mins / 1440)}d`;
  return { text: diff >= 0 ? `in ${text}` : `${text} ago`, overdue: diff < 0, hours: diff / 3_600_000 };
}

export function istTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Value for <input type="datetime-local"> in the viewer's local time. */
export function toLocalInput(iso: string | null | undefined): string {
  const d = iso ? new Date(iso) : new Date(Date.now() + 3 * 3_600_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}
