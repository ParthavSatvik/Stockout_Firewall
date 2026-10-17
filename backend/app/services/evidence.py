"""Read-only recovery evidence. A replacement proposal is never called a delivery."""
from app.models.orders import AllocationStatus


def recovery_evidence(order):
    plan = next((p for p in order.plans if p.is_selected), None)
    if plan is None:
        return {"plan_id": None, "items": [], "message": "Approve a plan to see its evidence."}
    rows = []
    inactive = {AllocationStatus.REJECTED, AllocationStatus.EXPIRED, AllocationStatus.SUPERSEDED}
    outstanding = (plan.explanation or {}).get("outstanding_by_item", {})
    for item in order.items:
        lines = [a for a in plan.allocations if a.order_item_id == item.id and a.status not in inactive]
        confirmed = sum(a.confirmed_qty_base_unit or 0 for a in lines if a.status != AllocationStatus.PROPOSED)
        proposed = sum(a.allocated_qty_base_unit for a in lines if a.status == AllocationStatus.PROPOSED)
        delivered = sum(a.confirmed_qty_base_unit or 0 for a in lines if a.status == AllocationStatus.FULFILLED)
        baseline = max(0, item.requested_qty_base_unit - outstanding[item.id]) if item.id in outstanding else None
        rows.append({
            "product": item.product_name, "unit": item.product.base_unit,
            "requested": item.requested_qty_base_unit, "confirmed": round(confirmed, 3),
            "proposed": round(proposed, 3), "delivered": round(delivered, 3),
            "uncovered": round(max(0, item.requested_qty_base_unit - confirmed - proposed), 3),
            "no_recovery_baseline": baseline,
            "additional_planned_coverage": round(max(0, min(item.requested_qty_base_unit, confirmed + proposed) - baseline), 3) if baseline is not None else None,
        })
    return {
        "plan_id": plan.id, "reason": plan.replan_reason, "items": rows,
        "landed_cost": plan.total_cost, "budget_cap": order.budget_cap,
        "budget_headroom": round(order.budget_cap - plan.total_cost, 2) if order.budget_cap is not None else None,
        "supplier_count": plan.supplier_count, "max_suppliers": order.max_suppliers,
        "budget_respected": order.budget_cap is None or plan.total_cost <= order.budget_cap + 0.005,
        "supplier_limit_respected": plan.supplier_count <= order.max_suppliers,
        "explanation": plan.explanation,
        "caveat": "Quotes are not reserved until supplier confirmation. Routes are estimates. Baseline holds other commitments constant without replacing the reported shortfall. This is planned coverage, not avoided stockouts or delivered goods.",
    }
