"""Aggregates that power the merchant command-center dashboard. Every figure is
computed from existing Order/AllocationPlan/Allocation rows -- nothing here is a
separate "metrics" table that could drift from reality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.orders import AllocationPlan, Order, OrderStatus
from app.services.intelligence import FULFILLMENT_STATUSES, stockout_radar
from app.services.reliability import get_or_default_reliability

IN_PROGRESS_STATUSES = (
    OrderStatus.DRAFT,
    OrderStatus.PLANNED,
    OrderStatus.AWAITING_CONFIRMATION,
    OrderStatus.REPLANNING,
)
RECOVERY_WINDOW_DAYS = 30


@dataclass
class ActionFeedItem:
    severity: str  # "info" | "warning" | "critical"
    message: str
    order_id: str | None = None


@dataclass
class MerchantSummary:
    total_spend: float
    estimated_savings: float
    savings_basis: str
    orders_in_progress: int
    orders_awaiting_confirmation: int
    shortage_alert_count: int
    avg_supplier_reliability: float | None
    recent_recovery_events: int
    action_feed: list[ActionFeedItem] = field(default_factory=list)


def merchant_summary(db: Session, merchant_id: str) -> MerchantSummary:
    orders = db.query(Order).filter(Order.merchant_id == merchant_id).all()

    total_spend = 0.0
    estimated_savings = 0.0
    for o in orders:
        if o.status not in FULFILLMENT_STATUSES:
            continue
        selected = next((p for p in o.plans if p.is_selected), None)
        if selected is None:
            continue
        total_spend += selected.total_cost
        siblings = [p for p in o.plans if p.replan_reason == "initial" and not p.is_selected]
        if siblings:
            most_expensive = max(p.total_cost for p in siblings + [selected])
            estimated_savings += max(0.0, most_expensive - selected.total_cost)

    orders_in_progress = sum(1 for o in orders if o.status in IN_PROGRESS_STATUSES)
    orders_awaiting = sum(1 for o in orders if o.status == OrderStatus.AWAITING_CONFIRMATION)

    radar = stockout_radar(db, merchant_id)
    shortage_alerts = sum(1 for r in radar if r.risk_level in ("medium", "high"))

    supplier_ids = {
        a.supplier_id
        for o in orders
        for p in o.plans
        if p.is_selected
        for a in p.allocations
        if a.status != "superseded"
    }
    scores = [get_or_default_reliability(db, sid).reliability_score for sid in supplier_ids]
    avg_reliability = round(sum(scores) / len(scores), 3) if scores else None

    cutoff = datetime.now(UTC) - timedelta(days=RECOVERY_WINDOW_DAYS)
    recovery_events = (
        db.query(AllocationPlan)
        .join(Order, AllocationPlan.order_id == Order.id)
        .filter(Order.merchant_id == merchant_id, AllocationPlan.replan_reason != "initial", AllocationPlan.created_at >= cutoff)
        .count()
    )

    feed: list[ActionFeedItem] = []
    for o in orders:
        if o.requires_confirmation and o.status == OrderStatus.DRAFT:
            feed.append(ActionFeedItem("warning", "An order's parsed text had low confidence -- review items before planning.", o.id))
        if o.status == OrderStatus.INFEASIBLE:
            feed.append(ActionFeedItem("critical", "An order could not be fully sourced under your current rules.", o.id))
        if o.status == OrderStatus.REPLANNING:
            feed.append(ActionFeedItem("warning", "A supplier failure triggered automatic reallocation -- review the new plan.", o.id))
        if o.status == OrderStatus.AWAITING_CONFIRMATION:
            stale_allocs = [
                a for p in o.plans if p.is_selected for a in p.allocations
                if a.status == "proposed" and a.confirmation_expires_at
                and a.confirmation_expires_at.replace(tzinfo=UTC) < datetime.now(UTC) + timedelta(hours=2)
            ]
            if stale_allocs:
                feed.append(ActionFeedItem("warning", "A supplier confirmation deadline is approaching soon.", o.id))
    for r in radar:
        if r.risk_level == "high":
            feed.append(ActionFeedItem("critical", f"Stockout risk for {r.product_name}: {r.reasons[0] if r.reasons else ''}"))

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    feed.sort(key=lambda f: severity_rank[f.severity])

    return MerchantSummary(
        total_spend=round(total_spend, 2),
        estimated_savings=round(estimated_savings, 2),
        savings_basis="vs. the most expensive of the alternative plans generated for the same order",
        orders_in_progress=orders_in_progress,
        orders_awaiting_confirmation=orders_awaiting,
        shortage_alert_count=shortage_alerts,
        avg_supplier_reliability=avg_reliability,
        recent_recovery_events=recovery_events,
        action_feed=feed[:10],
    )
