"""Deterministic supplier-allocation optimizer built on OR-Tools CP-SAT.

Design notes (read before changing constraints):

- All quantities/prices are scaled to integers before being handed to CP-SAT, because
  CP-SAT only supports integer linear arithmetic. QTY_SCALE turns kg/litre/piece base
  units into integer "milli-units" (1 kg -> 1000). PRICE_SCALE turns INR into paise.
  The *reported* totals are always recomputed from the chosen integer solution using
  plain Python floats -- the scaled objective value itself is never shown to a user.

- Hard constraints (see brief "REAL OPTIMIZATION" section):
    * requested quantity vs. permitted substitution (brands/suppliers of the same
      normalized product; see README/ARCHITECTURE for the cross-product-substitution
      limitation)
    * supplier stock and MOQ
    * merchant budget cap and price tolerance (price tolerance is enforced as a
      pre-filter against the cheapest eligible offer per product)
    * minimum reliability (pre-filter)
    * supplier delivery capacity
    * supplier-count / consolidation preference (max_suppliers)

- A basket that cannot be fully filled is NOT reported as a hard CP-SAT infeasibility.
  Each order item has a `shortfall` variable that absorbs any unmet quantity, weighted
  by a very large penalty in the objective, so the solver always prefers full
  fulfilment when it is achievable but still returns the best permitted partial basket
  when it is not (per brief: "report infeasibility honestly ... best permitted partial
  basket").

- Three objective profiles share the same hard constraints and differ only in the
  relative weight given to cost vs. estimated delivery time vs. supplier reliability
  risk.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

QTY_SCALE = 1000  # base unit -> milli-units (e.g. 1 kg -> 1000)
PRICE_SCALE = 100  # INR -> paise
SHORTFALL_PENALTY = 10_000_000  # dominates every other term; solver avoids shortfall first
SOLVER_TIME_LIMIT_SECONDS = 5.0


@dataclass
class OfferCandidate:
    """One supplier's sellable offer for a product, already resolved from SupplierInventory."""

    offer_id: str
    supplier_id: str
    supplier_name: str
    product_id: str
    pack_size_base_unit: float
    price_per_base_unit: float
    stock_qty_base_unit: float
    moq_base_unit: float
    reliability_score: float
    reliability_confidence: str
    distance_km: float
    is_preferred: bool = False


@dataclass
class ItemRequest:
    order_item_id: str
    product_id: str
    product_name: str
    requested_qty_base_unit: float
    substitution_allowed: bool
    base_unit: str = "kg"


@dataclass
class SupplierCapacity:
    supplier_id: str
    delivery_capacity_kg_per_day: float


@dataclass
class OptimizerPolicy:
    objective_profile: str  # "cheapest" | "fastest" | "most_reliable"
    budget_cap: float | None
    price_tolerance_pct: float
    min_reliability: float
    max_suppliers: int
    committed_supplier_ids: set[str] = field(default_factory=set)
    price_ceiling_by_product: dict[str, float] = field(default_factory=dict)


@dataclass
class AllocationLine:
    order_item_id: str
    product_id: str
    offer_id: str
    supplier_id: str
    allocated_qty_base_unit: float
    pack_count: int
    unit_price: float
    distance_km: float


@dataclass
class PlanResult:
    objective_profile: str
    is_feasible: bool
    allocations: list[AllocationLine]
    total_product_cost: float
    total_delivery_cost: float
    total_risk_penalty: float
    total_cost: float
    estimated_delivery_hours: float
    supplier_count: int
    shortfall_by_item: dict[str, float]
    infeasible_reasons: list[str]
    excluded_offers: list[dict] = field(default_factory=list)


def _scaled_qty(q: float) -> int:
    return max(0, round(q * QTY_SCALE))


def _scaled_price_per_unit_paise(p: float) -> int:
    # price per *scaled* quantity unit, in paise, rounded -- a small rounding term that
    # only affects the internal search objective, never the reported totals.
    return max(0, round(p * PRICE_SCALE / QTY_SCALE))


def solve_allocation(
    items: list[ItemRequest],
    offers_by_product: dict[str, list[OfferCandidate]],
    capacities: dict[str, SupplierCapacity],
    policy: OptimizerPolicy,
) -> PlanResult:
    from app.services.geo import estimate_delivery_cost_inr
    model = cp_model.CpModel()
    infeasible_reasons: list[str] = []
    excluded_offers: list[dict] = []

    # --- Pre-filter offers: reliability threshold and price-tolerance band ---
    eligible_offers: dict[str, list[OfferCandidate]] = {}
    for item in items:
        candidates = [o for o in offers_by_product.get(item.product_id, []) if o.stock_qty_base_unit > 0]
        if not item.substitution_allowed:
            pass  # no cross-supplier restriction modeled yet beyond same product

        reliability_filtered = [c for c in candidates if c.reliability_score >= policy.min_reliability]
        excluded_reliability = len(candidates) - len(reliability_filtered)
        for c in candidates:
            if c.reliability_score < policy.min_reliability:
                excluded_offers.append(
                    {
                        "supplier_id": c.supplier_id,
                        "supplier_name": c.supplier_name,
                        "product_id": c.product_id,
                        "reason": f"reliability {c.reliability_score:.2f} below minimum {policy.min_reliability:.2f}",
                    }
                )

        if not reliability_filtered:
            if candidates:
                infeasible_reasons.append(
                    f"{item.product_name}: all {len(candidates)} supplier offer(s) excluded by "
                    f"minimum reliability {policy.min_reliability:.2f}"
                )
            else:
                infeasible_reasons.append(f"{item.product_name}: no supplier currently has stock")
            eligible_offers[item.order_item_id] = []
            continue

        cheapest = min(c.price_per_base_unit for c in reliability_filtered)
        price_ceiling = min(cheapest * (1 + policy.price_tolerance_pct / 100.0), policy.price_ceiling_by_product.get(item.product_id, float("inf")))
        price_filtered = [c for c in reliability_filtered if c.price_per_base_unit <= price_ceiling]
        excluded_price = len(reliability_filtered) - len(price_filtered)
        for c in reliability_filtered:
            if c.price_per_base_unit > price_ceiling:
                excluded_offers.append(
                    {
                        "supplier_id": c.supplier_id,
                        "supplier_name": c.supplier_name,
                        "product_id": c.product_id,
                        "reason": (
                            f"price Rs.{c.price_per_base_unit:.2f} exceeds tolerance band "
                            f"(cheapest Rs.{cheapest:.2f} +{policy.price_tolerance_pct:.0f}%)"
                        ),
                    }
                )

        if excluded_reliability or excluded_price:
            infeasible_reasons.append(
                f"{item.product_name}: {excluded_reliability} offer(s) excluded by reliability, "
                f"{excluded_price} by price tolerance; {len(price_filtered)} eligible remain"
            )

        eligible_offers[item.order_item_id] = price_filtered

    # --- Variables ---
    pack_count: dict[tuple[str, str], cp_model.IntVar] = {}
    use_offer: dict[tuple[str, str], cp_model.IntVar] = {}
    shortfall: dict[str, cp_model.IntVar] = {}
    supplier_used: dict[str, cp_model.IntVar] = {}

    all_supplier_ids = sorted({o.supplier_id for offers in eligible_offers.values() for o in offers})
    for sid in all_supplier_ids:
        supplier_used[sid] = model.NewBoolVar(f"supplier_used_{sid}")

    for item in items:
        q_scaled = _scaled_qty(item.requested_qty_base_unit)
        shortfall[item.order_item_id] = model.NewIntVar(0, q_scaled, f"shortfall_{item.order_item_id}")
        total_terms = []
        max_overshoot = 0
        for offer in eligible_offers[item.order_item_id]:
            key = (item.order_item_id, offer.offer_id)
            pack_size_scaled = max(1, _scaled_qty(offer.pack_size_base_unit))
            max_packs_by_stock = int(offer.stock_qty_base_unit // offer.pack_size_base_unit) if offer.pack_size_base_unit > 0 else 0
            max_packs_by_need = math.ceil(item.requested_qty_base_unit / offer.pack_size_base_unit) + 1 if offer.pack_size_base_unit > 0 else 0
            max_packs = max(0, min(max_packs_by_stock, max_packs_by_need))
            max_overshoot = max(max_overshoot, pack_size_scaled)

            pc = model.NewIntVar(0, max_packs, f"pack_{item.order_item_id}_{offer.offer_id}")
            pack_count[key] = pc
            uo = model.NewBoolVar(f"use_{item.order_item_id}_{offer.offer_id}")
            use_offer[key] = uo

            model.Add(pc <= max_packs * uo)
            min_packs_for_moq = (
                math.ceil(offer.moq_base_unit / offer.pack_size_base_unit) if offer.moq_base_unit > 0 else 0
            )
            if min_packs_for_moq > 0:
                model.Add(pc >= min_packs_for_moq * uo)
            else:
                model.Add(pc >= uo)  # using an offer means buying at least one pack

            model.Add(uo <= supplier_used[offer.supplier_id])

            total_terms.append((pc, pack_size_scaled))

        if total_terms:
            total_expr = sum(pc * size for pc, size in total_terms)
            model.Add(total_expr + shortfall[item.order_item_id] >= q_scaled)
            model.Add(total_expr <= q_scaled + max_overshoot)
        else:
            model.Add(shortfall[item.order_item_id] == q_scaled)

    # One supplier_used can only be true if at least one of its offers is used (already
    # enforced by `uo <= supplier_used`); now cap total distinct suppliers used.
    if all_supplier_ids:
        for sid in all_supplier_ids:
            uses = [use_offer[(item.order_item_id, o.offer_id)] for item in items for o in eligible_offers[item.order_item_id] if o.supplier_id == sid]
            model.Add(supplier_used[sid] <= sum(uses))
        model.Add(sum(v for sid, v in supplier_used.items() if sid not in policy.committed_supplier_ids) <= max(0, policy.max_suppliers - len(policy.committed_supplier_ids)))

    # The same offer cannot be consumed independently by multiple order lines.
    for oid in {o.offer_id for offers in eligible_offers.values() for o in offers}:
        occurrences = [(item, o) for item in items for o in eligible_offers[item.order_item_id] if o.offer_id == oid]
        model.Add(sum(pack_count[(i.order_item_id, o.offer_id)] * _scaled_qty(o.pack_size_base_unit) for i, o in occurrences) <= _scaled_qty(occurrences[0][1].stock_qty_base_unit))
    delivery_paise = {sid: (0 if sid in policy.committed_supplier_ids else math.ceil(estimate_delivery_cost_inr(max(o.distance_km for offers in eligible_offers.values() for o in offers if o.supplier_id == sid)) * PRICE_SCALE)) for sid in all_supplier_ids}

    # Supplier delivery-capacity constraint across the whole order.
    for sid in all_supplier_ids:
        cap = capacities.get(sid)
        if cap is None:
            continue
        cap_scaled = _scaled_qty(cap.delivery_capacity_kg_per_day)
        terms = []
        for item in items:
            for offer in eligible_offers[item.order_item_id]:
                if offer.supplier_id != sid or item.base_unit != "kg":
                    continue
                key = (item.order_item_id, offer.offer_id)
                pack_size_scaled = max(1, _scaled_qty(offer.pack_size_base_unit))
                terms.append(pack_count[key] * pack_size_scaled)
        if terms:
            model.Add(sum(terms) <= cap_scaled)

    # Budget cap (product cost only -- delivery cost is a smaller, bounded add-on and
    # is additionally checked after solving).
    if policy.budget_cap is not None:
        budget_scaled = max(0, round(policy.budget_cap * PRICE_SCALE))
        cost_terms = []
        for item in items:
            for offer in eligible_offers[item.order_item_id]:
                key = (item.order_item_id, offer.offer_id)
                pack_cost_paise = math.ceil(round(offer.pack_size_base_unit * offer.price_per_base_unit * PRICE_SCALE, 6))
                cost_terms.append(pack_count[key] * pack_cost_paise)
        if cost_terms:
            model.Add(sum(cost_terms) + sum(supplier_used[sid] * cost for sid, cost in delivery_paise.items()) <= budget_scaled)

    # --- Objective ---
    objective_terms = []
    for item in items:
        # Shortfall is minimized first in a separate solve (lexicographic objective).
        for offer in eligible_offers[item.order_item_id]:
            key = (item.order_item_id, offer.offer_id)
            pc = pack_count[key]
            pack_cost_paise = math.ceil(round(offer.pack_size_base_unit * offer.price_per_base_unit * PRICE_SCALE, 6))
            preferred_discount = 50 if offer.is_preferred else 0  # small nudge, never overrides hard rules

            if policy.objective_profile == "fastest":
                time_weight = round(offer.distance_km * 100)
                objective_terms.append(use_offer[key] * time_weight * 50)
                objective_terms.append(pc * pack_cost_paise)
            elif policy.objective_profile == "most_reliable":
                risk_weight = round((1 - offer.reliability_score) * 100_000)
                objective_terms.append(use_offer[key] * risk_weight)
                objective_terms.append(pc * pack_cost_paise)
            else:  # cheapest
                objective_terms.append(pc * pack_cost_paise)
                objective_terms.append(use_offer[key] * round(offer.distance_km * 20))

            if preferred_discount:
                objective_terms.append(-use_offer[key] * preferred_discount)

    objective_terms.extend(supplier_used[sid] * cost for sid, cost in delivery_paise.items())
    model.Minimize(sum(shortfall.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status == cp_model.OPTIMAL:
        minimum_shortfall = sum(solver.Value(v) for v in shortfall.values())
        model.Add(sum(shortfall.values()) == minimum_shortfall)
        model.Minimize(sum(objective_terms))
        status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PlanResult(
            objective_profile=policy.objective_profile,
            is_feasible=False,
            allocations=[],
            total_product_cost=0.0,
            total_delivery_cost=0.0,
            total_risk_penalty=0.0,
            total_cost=0.0,
            estimated_delivery_hours=0.0,
            supplier_count=0,
            shortfall_by_item={item.order_item_id: item.requested_qty_base_unit for item in items},
            infeasible_reasons=infeasible_reasons + ["Solver could not find any feasible allocation."],
            excluded_offers=excluded_offers,
        )

    allocations: list[AllocationLine] = []
    total_product_cost = 0.0
    used_supplier_ids: set[str] = set()
    max_distance_km = 0.0
    total_risk_penalty = 0.0
    shortfall_by_item: dict[str, float] = {}

    for item in items:
        shortfall_val = solver.Value(shortfall[item.order_item_id]) / QTY_SCALE
        shortfall_by_item[item.order_item_id] = round(shortfall_val, 3)
        for offer in eligible_offers[item.order_item_id]:
            key = (item.order_item_id, offer.offer_id)
            packs = solver.Value(pack_count[key])
            if packs <= 0:
                continue
            qty = round(packs * offer.pack_size_base_unit, 3)
            allocations.append(
                AllocationLine(
                    order_item_id=item.order_item_id,
                    product_id=item.product_id,
                    offer_id=offer.offer_id,
                    supplier_id=offer.supplier_id,
                    allocated_qty_base_unit=qty,
                    pack_count=packs,
                    unit_price=offer.price_per_base_unit,
                    distance_km=offer.distance_km,
                )
            )
            total_product_cost += qty * offer.price_per_base_unit
            used_supplier_ids.add(offer.supplier_id)
            max_distance_km = max(max_distance_km, offer.distance_km)
            total_risk_penalty += qty * offer.price_per_base_unit * (1 - offer.reliability_score)

    from app.services.geo import estimate_delivery_cost_inr, estimate_duration_minutes

    total_delivery_cost = sum(
        estimate_delivery_cost_inr(
            max((a.distance_km for a in allocations if a.supplier_id == sid), default=0.0)
        )
        for sid in used_supplier_ids if sid not in policy.committed_supplier_ids
    )
    estimated_delivery_hours = (
        round(estimate_duration_minutes(max_distance_km) / 60.0, 2) if allocations else 0.0
    )

    is_feasible = all(v <= 1e-6 for v in shortfall_by_item.values())
    if not is_feasible and not infeasible_reasons:
        short_items = ", ".join(
            f"{iid} short by {v}" for iid, v in shortfall_by_item.items() if v > 1e-6
        )
        infeasible_reasons.append(f"Could not fully satisfy requested quantity: {short_items}")

    total_cost = total_product_cost + total_delivery_cost

    return PlanResult(
        objective_profile=policy.objective_profile,
        is_feasible=is_feasible,
        allocations=allocations,
        total_product_cost=round(total_product_cost, 2),
        total_delivery_cost=round(total_delivery_cost, 2),
        total_risk_penalty=round(total_risk_penalty, 2),
        total_cost=round(total_cost, 2),
        estimated_delivery_hours=estimated_delivery_hours,
        supplier_count=len(used_supplier_ids),
        shortfall_by_item=shortfall_by_item,
        infeasible_reasons=infeasible_reasons,
        excluded_offers=excluded_offers,
    )
