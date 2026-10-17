"""Deterministic, explainable intelligence modules built entirely on data already in
the schema (order history, live supplier inventory, price observations). None of these
call an LLM or a trained model -- every number traces back to a SQL aggregate over real
rows, and every module reports "insufficient data" rather than a confident-looking
number when the sample size is too small to mean anything.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.catalog import MerchantProductPrice, Product, SupplierInventory
from app.models.core import SupplierProfile
from app.models.orders import (
    AllocationPlan,
    Order,
    OrderItem,
    OrderStatus,
)

MIN_SAMPLE_FOR_TREND = 2
DUE_SOON_THRESHOLD = 0.85  # fraction of the average reorder cycle already elapsed
LOW_MARGIN_THRESHOLD_PCT = 12.0
CASH_COMFORTABLE_RATIO = 1.5
CASH_TIGHT_RATIO = 1.0

FULFILLMENT_STATUSES = (
    OrderStatus.CONFIRMED,
    OrderStatus.PARTIALLY_FULFILLED,
    OrderStatus.FULFILLED,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _merchant_order_items(db: Session, merchant_id: str) -> list[tuple[Order, OrderItem]]:
    rows = (
        db.query(Order, OrderItem)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(Order.merchant_id == merchant_id, Order.status.in_(FULFILLMENT_STATUSES))
        .order_by(Order.created_at.asc())
        .all()
    )
    return rows


@dataclass
class StockoutRadarItem:
    product_id: str
    product_name: str
    sample_size: int
    insufficient_data: bool
    avg_order_qty: float | None
    avg_reorder_interval_days: float | None
    days_since_last_order: float | None
    network_stock_base_unit: float
    risk_level: str  # "none" | "low" | "medium" | "high" | "unknown"
    reasons: list[str] = field(default_factory=list)
    recommended_action: str | None = None


def stockout_radar(db: Session, merchant_id: str) -> list[StockoutRadarItem]:
    rows = _merchant_order_items(db, merchant_id)
    by_product: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for order, item in rows:
        by_product[item.product_id].append((order.created_at, item.requested_qty_base_unit))

    results: list[StockoutRadarItem] = []
    for product_id, points in by_product.items():
        product = db.get(Product, product_id)
        name = product.name if product else product_id
        sample_size = len(points)

        network_stock = (
            db.query(SupplierInventory)
            .join(SupplierProfile, SupplierInventory.supplier_id == SupplierProfile.id)
            .filter(
                SupplierInventory.product_id == product_id,
                SupplierInventory.is_available.is_(True),
                SupplierProfile.is_active.is_(True),
            )
            .all()
        )
        network_stock_total = sum(o.stock_qty_base_unit for o in network_stock)

        if sample_size < MIN_SAMPLE_FOR_TREND:
            results.append(
                StockoutRadarItem(
                    product_id=product_id, product_name=name, sample_size=sample_size,
                    insufficient_data=True, avg_order_qty=None, avg_reorder_interval_days=None,
                    days_since_last_order=None, network_stock_base_unit=network_stock_total,
                    risk_level="unknown",
                    reasons=[f"Only {sample_size} past order(s) -- need at least {MIN_SAMPLE_FOR_TREND} to estimate a reorder cycle."],
                )
            )
            continue

        dates = sorted(d for d, _ in points)
        qtys = [q for _, q in points]
        avg_qty = sum(qtys) / len(qtys)
        intervals = [(dates[i + 1] - dates[i]).total_seconds() / 86400 for i in range(len(dates) - 1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else None
        last_order_date = dates[-1]
        days_since_last = (_now() - last_order_date.replace(tzinfo=UTC) if last_order_date.tzinfo is None
                            else _now() - last_order_date).total_seconds() / 86400

        reasons = []
        risk_level = "none"

        if avg_interval is not None and days_since_last >= avg_interval * DUE_SOON_THRESHOLD:
            risk_level = "medium"
            reasons.append(
                f"{days_since_last:.0f} days since last order, vs. a usual ~{avg_interval:.0f}-day cycle."
            )
        if network_stock_total < avg_qty:
            risk_level = "high"
            reasons.append(
                f"Network-wide available stock ({network_stock_total:.0f}) is below your typical order "
                f"size ({avg_qty:.0f}) across all eligible suppliers."
            )

        action = None
        if risk_level != "none":
            action = f"Consider reordering ~{avg_qty:.0f} of {name} soon."

        results.append(
            StockoutRadarItem(
                product_id=product_id, product_name=name, sample_size=sample_size, insufficient_data=False,
                avg_order_qty=round(avg_qty, 2),
                avg_reorder_interval_days=round(avg_interval, 1) if avg_interval else None,
                days_since_last_order=round(days_since_last, 1),
                network_stock_base_unit=network_stock_total, risk_level=risk_level,
                reasons=reasons, recommended_action=action,
            )
        )

    results.sort(key=lambda r: {"high": 0, "medium": 1, "low": 2, "none": 3, "unknown": 4}[r.risk_level])
    return results


@dataclass
class CashCycleSummary:
    available_cash: float | None
    sample_size: int
    insufficient_data: bool
    avg_order_cost: float | None
    avg_interval_days: float | None
    last_order_date: str | None
    projected_next_order_date: str | None
    cash_coverage_ratio: float | None
    status: str  # "no_cash_input" | "insufficient_data" | "comfortable" | "tight" | "short"
    explanation: str


def cash_cycle_summary(db: Session, merchant_id: str, available_cash: float | None) -> CashCycleSummary:
    orders = (
        db.query(Order)
        .join(AllocationPlan, AllocationPlan.order_id == Order.id)
        .filter(Order.merchant_id == merchant_id, Order.status.in_(FULFILLMENT_STATUSES), AllocationPlan.is_selected.is_(True))
        .order_by(Order.created_at.asc())
        .all()
    )
    costs = []
    dates = []
    for o in orders:
        plan = next((p for p in o.plans if p.is_selected), None)
        if plan:
            costs.append(plan.total_cost)
            dates.append(o.created_at)

    sample_size = len(costs)
    if available_cash is None:
        return CashCycleSummary(
            available_cash=None, sample_size=sample_size, insufficient_data=sample_size < MIN_SAMPLE_FOR_TREND,
            avg_order_cost=None, avg_interval_days=None, last_order_date=None, projected_next_order_date=None,
            cash_coverage_ratio=None, status="no_cash_input",
            explanation="Enter your available cash on hand to see coverage against upcoming procurement needs.",
        )

    if sample_size < MIN_SAMPLE_FOR_TREND:
        return CashCycleSummary(
            available_cash=available_cash, sample_size=sample_size, insufficient_data=True,
            avg_order_cost=None, avg_interval_days=None, last_order_date=None, projected_next_order_date=None,
            cash_coverage_ratio=None, status="insufficient_data",
            explanation=f"Only {sample_size} past order(s) on record -- need at least {MIN_SAMPLE_FOR_TREND} to project upcoming spend.",
        )

    avg_cost = sum(costs) / len(costs)
    intervals = [(dates[i + 1] - dates[i]).total_seconds() / 86400 for i in range(len(dates) - 1)]
    avg_interval = sum(intervals) / len(intervals) if intervals else None
    last_date = dates[-1]
    projected_next = last_date + timedelta(days=avg_interval) if avg_interval else None
    ratio = available_cash / avg_cost if avg_cost > 0 else None

    if ratio is None:
        status, explanation = "insufficient_data", "Could not compute an average order cost."
    elif ratio >= CASH_COMFORTABLE_RATIO:
        status, explanation = "comfortable", f"Cash on hand covers {ratio:.1f}x your typical next order (Rs.{avg_cost:.0f})."
    elif ratio >= CASH_TIGHT_RATIO:
        status, explanation = "tight", f"Cash on hand covers only {ratio:.1f}x your typical next order (Rs.{avg_cost:.0f}) -- plan carefully."
    else:
        status, explanation = "short", f"Cash on hand is {ratio:.1f}x your typical next order (Rs.{avg_cost:.0f}) -- likely short for the next cycle."

    return CashCycleSummary(
        available_cash=available_cash, sample_size=sample_size, insufficient_data=False,
        avg_order_cost=round(avg_cost, 2), avg_interval_days=round(avg_interval, 1) if avg_interval else None,
        last_order_date=last_date.isoformat(), projected_next_order_date=projected_next.isoformat() if projected_next else None,
        cash_coverage_ratio=round(ratio, 2) if ratio is not None else None, status=status, explanation=explanation,
    )


@dataclass
class MarginLeakLine:
    product_id: str
    product_name: str
    selling_price_per_base_unit: float
    cheapest_cost_per_base_unit: float | None
    cheapest_supplier_name: str | None
    margin_pct: float | None
    margin_per_base_unit: float | None
    is_leaking: bool
    note: str


def margin_leak_report(db: Session, merchant_id: str) -> list[MarginLeakLine]:
    entries = db.query(MerchantProductPrice).filter(MerchantProductPrice.merchant_id == merchant_id).all()
    results = []
    for entry in entries:
        product = db.get(Product, entry.product_id)
        offers = (
            db.query(SupplierInventory, SupplierProfile)
            .join(SupplierProfile, SupplierInventory.supplier_id == SupplierProfile.id)
            .filter(
                SupplierInventory.product_id == entry.product_id,
                SupplierInventory.is_available.is_(True),
                SupplierProfile.is_active.is_(True),
            )
            .order_by(SupplierInventory.price_per_base_unit.asc())
            .first()
        )
        if offers is None:
            results.append(
                MarginLeakLine(
                    product_id=entry.product_id, product_name=product.name if product else entry.product_id,
                    selling_price_per_base_unit=entry.selling_price_per_base_unit,
                    cheapest_cost_per_base_unit=None, cheapest_supplier_name=None, margin_pct=None,
                    margin_per_base_unit=None, is_leaking=False,
                    note="No current supplier offer available for comparison.",
                )
            )
            continue
        inv, supplier = offers
        margin_per_unit = entry.selling_price_per_base_unit - inv.price_per_base_unit
        margin_pct = (margin_per_unit / entry.selling_price_per_base_unit * 100) if entry.selling_price_per_base_unit else None
        is_leaking = margin_pct is not None and margin_pct < LOW_MARGIN_THRESHOLD_PCT
        note = (
            f"Selling Rs.{entry.selling_price_per_base_unit:.2f} vs. cheapest available cost "
            f"Rs.{inv.price_per_base_unit:.2f} from {supplier.business_name}."
        )
        results.append(
            MarginLeakLine(
                product_id=entry.product_id, product_name=product.name if product else entry.product_id,
                selling_price_per_base_unit=entry.selling_price_per_base_unit,
                cheapest_cost_per_base_unit=inv.price_per_base_unit, cheapest_supplier_name=supplier.business_name,
                margin_pct=round(margin_pct, 1) if margin_pct is not None else None,
                margin_per_base_unit=round(margin_per_unit, 2), is_leaking=is_leaking, note=note,
            )
        )
    results.sort(key=lambda r: (r.margin_pct is None, r.margin_pct if r.margin_pct is not None else 0))
    return results


@dataclass
class PriceIndexSummary:
    product_id: str
    product_name: str
    sample_size: int
    insufficient_data: bool
    avg_price: float | None
    min_price: float | None
    max_price: float | None
    distinct_suppliers: int
    most_recent_observation: str | None
    comparability_note: str


def price_index(db: Session, product_id: str, window_days: int = 180):
    from app.models.catalog import PriceObservation

    product = db.get(Product, product_id)
    cutoff = _now() - timedelta(days=window_days)
    rows = (
        db.query(PriceObservation)
        .filter(PriceObservation.product_id == product_id, PriceObservation.observed_at >= cutoff)
        .all()
    )
    name = product.name if product else product_id
    if len(rows) < MIN_SAMPLE_FOR_TREND:
        return PriceIndexSummary(
            product_id=product_id, product_name=name, sample_size=len(rows), insufficient_data=True,
            avg_price=None, min_price=None, max_price=None, distinct_suppliers=len({r.supplier_id for r in rows}),
            most_recent_observation=rows[-1].observed_at.isoformat() if rows else None,
            comparability_note=f"Only {len(rows)} price observation(s) in the last {window_days} days -- not enough to index.",
        )

    prices = [r.price_per_base_unit for r in rows]
    return PriceIndexSummary(
        product_id=product_id, product_name=name, sample_size=len(rows), insufficient_data=False,
        avg_price=round(sum(prices) / len(prices), 2), min_price=round(min(prices), 2), max_price=round(max(prices), 2),
        distinct_suppliers=len({r.supplier_id for r in rows}),
        most_recent_observation=max(r.observed_at for r in rows).isoformat(),
        comparability_note=(
            "Prices are normalized to the product's base unit (kg/litre/piece) so different pack sizes are "
            "directly comparable; brand/quality differences within a product are not distinguished."
        ),
    )


@dataclass
class AutopilotSuggestion:
    product_id: str
    product_name: str
    suggested_qty_base_unit: float
    sample_size: int
    avg_interval_days: float | None
    last_order_date: str
    confidence: str  # "low" | "medium" | "high"


def autopilot_suggestions(db: Session, merchant_id: str) -> list[AutopilotSuggestion]:
    rows = _merchant_order_items(db, merchant_id)
    by_product: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for order, item in rows:
        by_product[item.product_id].append((order.created_at, item.requested_qty_base_unit))

    out = []
    for product_id, points in by_product.items():
        if len(points) < MIN_SAMPLE_FOR_TREND:
            continue
        product = db.get(Product, product_id)
        dates = sorted(d for d, _ in points)
        qtys = [q for _, q in points]
        avg_qty = sum(qtys) / len(qtys)
        intervals = [(dates[i + 1] - dates[i]).total_seconds() / 86400 for i in range(len(dates) - 1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else None
        last_date = dates[-1]
        days_since_last = (_now() - (last_date if last_date.tzinfo else last_date.replace(tzinfo=UTC))).total_seconds() / 86400

        if avg_interval is None or days_since_last < avg_interval * DUE_SOON_THRESHOLD:
            continue  # not due yet

        confidence = "high" if len(points) >= 5 else "medium" if len(points) >= 3 else "low"
        out.append(
            AutopilotSuggestion(
                product_id=product_id, product_name=product.name if product else product_id,
                suggested_qty_base_unit=round(avg_qty, 2), sample_size=len(points),
                avg_interval_days=round(avg_interval, 1), last_order_date=last_date.isoformat(), confidence=confidence,
            )
        )
    return out
