import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider } from "../../components/ui/toast";
import { RelayPanel } from "../../components/RelayPanel";
import { RequestsPage } from "./RequestsPage";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() }, ApiError: class extends Error {} }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const request = {
  id: "a1", plan_id: "p", order_item_id: "i", supplier_id: "s", supplier_name: "Anand", product_id: "atta", product_name: "Wheat Atta",
  allocated_qty_base_unit: 40, unit_price: 32, pack_count: 1, status: "proposed", confirmed_qty_base_unit: null, confirmed_ready_by: null,
  confirmation_expires_at: new Date(Date.now() + 5 * 3_600_000).toISOString(), route_distance_km: 6, route_duration_minutes: 40, route_source: "estimated", route_cost: 120,
};
const guard = {
  status: "PARTIAL_COMMITMENT_RECOMMENDED", label: "Partial commitment recommended", headline: "Only 20 of 40 kg can be promised without breaking existing commitments.",
  requested: 40, unit: "kg", max_feasible_qty: 20, shortfall_qty: 20, pack_breakdown: { pack_size: 25, full_packs: 0, loose_qty: 20 },
  unit_price: 32, revenue_at_max: 640, revenue_forgone: 640, margin_note: "Margin is not shown.",
  suggested_ready_by: new Date(Date.now() + 3 * 3_600_000).toISOString(), suggestion_basis: "first slot in operating hours",
  position: { inventory_id: "inv", product_id: "atta", product_name: "Wheat Atta", unit: "kg", brand: "Local", pack_size: 25, price_per_base_unit: 32, moq_base_unit: 25,
    is_available: true, on_hand: 80, reported_on_hand: 80, committed: 50, safety_stock: 10, uncommitted: 30, free_to_promise: 20, requested_pending: 40,
    in_transit: 0, delivered: 0, oversubscribed_by: 20, drift_qty: 0, freshness: { confirmed_at: null, source: "stock_count", age_hours: 1, status: "fresh", excluded_from_new_plans: false }, formula: "" },
  checks: [{ rule: "free_to_promise", ok: false, detail: "80 on hand − 50 committed − 10 safety = 20 kg free" }],
  consequence_if_ignored: "The request expires.", basis: "Deterministic rules.",
};

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter>{node}</MemoryRouter></ToastProvider></QueryClientProvider>);
}

test("PromiseGuard shows the free-to-promise arithmetic and only offers feasible decisions", async () => {
  vi.mocked(api.get).mockImplementation(async (path: string) => (path.includes("/guard") ? guard : [request]) as never);
  wrap(<RequestsPage />);
  expect(await screen.findByText(/Only 20 of 40 kg/)).toBeTruthy();
  expect(screen.getByLabelText(/80 on hand minus 50 committed minus 10 safety stock equals 20 kg free to promise/)).toBeTruthy();
  // The full 40 kg is infeasible, so there is no one-click "Accept 40".
  expect(screen.queryByRole("button", { name: /^Accept 40/ })).toBeNull();
  expect(screen.getByRole("button", { name: /Commit 20 \+ relay 20 kg/ })).toBeTruthy();
  expect(screen.getByRole("button", { name: /Commit 20, planner sources the rest/ })).toBeTruthy();
  // Safety stock can only be used through an explicit, recorded override.
  expect(screen.queryByLabelText(/Reason for using safety stock/)).toBeNull();
});

test("merchant relay panel shows uncovered quantity honestly and blocks approval when nothing fits", () => {
  wrap(<RelayPanel orderId="o1" relays={[{
    id: "r1", status: "open", product_name: "Rice", unit: "kg", outstanding_qty: 60, price_ceiling: 43.2, required_brand: null,
    needed_by: null, expires_at: new Date(Date.now() + 3_600_000).toISOString(), created_at: new Date().toISOString(), resolution_note: "", resolved_at: null,
    origin_supplier_name: "NewCo", origin_committed_qty: 40, reason: "Only 40 kg", invites: [],
    preview: { available: true, lines: [], covered: 0, uncovered: 60, current_landed_cost: 1670, new_landed_cost: 1670, budget_cap: 6000, max_suppliers: 1,
      infeasible_reasons: ["supplier limit reached"], excluded_quotes: [], policy_note: "Same optimizer.", price_ceiling: 43.2 },
  }]} />);
  expect(screen.getByText("No partner quote fits your order's limits.")).toBeTruthy();
  expect(screen.getByText("60 kg")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Approve relay plan" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("button", { name: "Use open-market recovery instead" })).toBeTruthy();
});
