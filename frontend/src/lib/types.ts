export type UserRole = "merchant" | "supplier" | "admin";

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  base_unit: string;
}

export interface SupplierOffer {
  id: string;
  supplier_id: string;
  supplier_name: string;
  product_id: string;
  product_name: string;
  brand: string;
  pack_size: number;
  pack_unit: string;
  price_per_base_unit: number;
  stock_qty_base_unit: number;
  moq_base_unit: number;
  is_available: boolean;
  freshness_source: string;
  reliability_score: number;
  reliability_confidence: "low" | "medium" | "high";
  reliability_sample_size: number;
  safety_stock_base_unit: number;
  committed_qty_base_unit: number;
  free_to_promise_base_unit: number;
  stock_confirmed_at: string | null;
}

export interface SurplusListing {
  id: string;
  product_id: string;
  product_name: string;
  qty_base_unit: number;
  asking_price_per_base_unit: number;
  status: string;
}

export type ObjectiveProfile = "cheapest" | "fastest" | "most_reliable";

export type OrderStatus =
  | "draft"
  | "planned"
  | "awaiting_confirmation"
  | "confirmed"
  | "replanning"
  | "partially_fulfilled"
  | "fulfilled"
  | "infeasible"
  | "cancelled";

export type AllocationStatus =
  | "proposed"
  | "confirmed"
  | "rejected"
  | "expired"
  | "short_supply"
  | "fulfilled"
  | "superseded";

export interface OrderItem {
  id: string;
  product_id: string;
  product_name: string;
  requested_qty_base_unit: number;
  substitution_allowed: boolean;
  notes: string;
}

export interface Allocation {
  id: string;
  plan_id: string;
  order_item_id: string;
  supplier_id: string;
  supplier_name: string;
  product_id: string;
  product_name: string;
  allocated_qty_base_unit: number;
  unit_price: number;
  pack_count: number;
  status: AllocationStatus;
  confirmed_qty_base_unit: number | null;
  confirmed_ready_by: string | null;
  confirmation_expires_at: string | null;
  route_distance_km: number | null;
  route_duration_minutes: number | null;
  route_source: string;
  route_cost: number;
  fulfillment_stage?: string | null;
}

export interface AllocationPlan {
  id: string;
  order_id: string;
  objective_profile: ObjectiveProfile;
  is_selected: boolean;
  is_feasible: boolean;
  replan_reason: string;
  total_product_cost: number;
  total_delivery_cost: number;
  total_risk_penalty: number;
  total_cost: number;
  estimated_delivery_hours: number;
  supplier_count: number;
  explanation: Record<string, unknown>;
  infeasible_reasons: string[];
  created_at: string;
  allocations: Allocation[];
}

export interface Order {
  id: string;
  merchant_id: string;
  status: OrderStatus;
  objective_profile: ObjectiveProfile;
  budget_cap: number | null;
  price_tolerance_pct: number;
  min_reliability: number;
  allow_substitution: boolean;
  max_suppliers: number;
  requires_confirmation: boolean;
  parse_confidence: number;
  raw_input_text: string;
  created_at: string;
  items: OrderItem[];
  plans: AllocationPlan[];
}

export interface ParsedItem {
  matched_text: string;
  quantity_base_unit: number;
  base_unit: string;
  product_id: string | null;
  product_name: string | null;
  matched_alias: string | null;
  confidence: number;
}

export interface ParseResponse {
  items: ParsedItem[];
  overall_confidence: number;
  unmatched_fragments: string[];
  requires_confirmation: boolean;
}

export interface ReconciliationLine {
  product_id: string;
  product_name: string;
  ordered_qty: number;
  invoiced_qty: number;
  received_qty: number;
  ordered_vs_invoiced_diff: number;
  invoiced_vs_received_diff: number;
  invoiced_unit_price: number | null;
  allocated_unit_price: number | null;
  price_diff: number | null;
  flags: string[];
}

export interface ReconciliationResponse {
  order_id: string;
  lines: ReconciliationLine[];
  has_discrepancies: boolean;
}

export interface Payment {
  id: string;
  order_id: string;
  provider: "simulated" | "paytm";
  amount: number;
  currency: string;
  status: "pending" | "success" | "failed";
  provider_order_id: string;
  provider_txn_id: string | null;
  is_simulated: boolean;
}

export interface HealthResponse {
  status: string;
  app_env: string;
  demo_mode: boolean;
  sarvam_configured: boolean;
  paytm_configured: boolean;
  google_maps_configured: boolean;
  supabase_configured: boolean;
}

export interface AdminMetrics {
  total_orders: number;
  orders_by_status: Record<string, number>;
  total_replans: number;
  infeasible_plans: number;
  supplier_count: number;
  average_supplier_reliability: number | null;
  fulfilled_or_partial: number;
}

export interface ScenarioResult {
  order_id: string;
  disruption_type: string;
  before_plan_id: string;
  after_plan_id: string;
  before_total_cost: number;
  after_total_cost: number;
  before_delivery_hours: number;
  after_delivery_hours: number;
  narrative: string;
}
