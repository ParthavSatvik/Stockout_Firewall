"""Supplier reliability scoring from actual commitment history.

Confidence is explicitly tied to sample size -- a supplier with one lucky delivery is
NOT reported as "95% reliable". New suppliers with no history get a neutral prior
(0.7) labelled 'low' confidence, never a fabricated high-accuracy figure.
"""
from sqlalchemy.orm import Session

from app.models.ops import SupplierReliabilityStat
from app.models.orders import Allocation, AllocationPlan, AllocationStatus

NEW_SUPPLIER_PRIOR = 0.7
LOW_CONFIDENCE_MAX_SAMPLE = 3
MEDIUM_CONFIDENCE_MAX_SAMPLE = 9

# Laplace-style smoothing: blend the prior with observed history, weighted by a
# virtual sample count, so a single bad event doesn't swing the score wildly.
PRIOR_VIRTUAL_SAMPLES = 2


def _confidence_label(sample_size: int) -> str:
    if sample_size <= LOW_CONFIDENCE_MAX_SAMPLE:
        return "low"
    if sample_size <= MEDIUM_CONFIDENCE_MAX_SAMPLE:
        return "medium"
    return "high"


def recompute_supplier_reliability(db: Session, supplier_id: str) -> SupplierReliabilityStat:
    terminal_statuses = (
        AllocationStatus.FULFILLED,
        AllocationStatus.REJECTED,
        AllocationStatus.EXPIRED,
        AllocationStatus.SHORT_SUPPLY,
    )
    allocations = (
        db.query(Allocation).join(AllocationPlan, Allocation.plan_id == AllocationPlan.id)
        .filter(AllocationPlan.is_selected.is_(True), Allocation.supplier_id == supplier_id, Allocation.status.in_(terminal_statuses))
        .all()
    )

    total = len(allocations)
    fulfilled = sum(1 for a in allocations if a.status == AllocationStatus.FULFILLED and (a.confirmed_qty_base_unit or 0) >= a.allocated_qty_base_unit)
    short_supply = sum(1 for a in allocations if a.status == AllocationStatus.SHORT_SUPPLY or (a.status == AllocationStatus.FULFILLED and (a.confirmed_qty_base_unit or 0) < a.allocated_qty_base_unit))
    rejected = sum(1 for a in allocations if a.status == AllocationStatus.REJECTED)
    expired = sum(1 for a in allocations if a.status == AllocationStatus.EXPIRED)

    observed_success_rate = (fulfilled / total) if total else NEW_SUPPLIER_PRIOR
    blended_score = (
        (observed_success_rate * total) + (NEW_SUPPLIER_PRIOR * PRIOR_VIRTUAL_SAMPLES)
    ) / (total + PRIOR_VIRTUAL_SAMPLES)

    stat = db.query(SupplierReliabilityStat).filter(
        SupplierReliabilityStat.supplier_id == supplier_id
    ).first()
    if stat is None:
        stat = SupplierReliabilityStat(supplier_id=supplier_id)
        db.add(stat)

    stat.total_commitments = total
    stat.fulfilled_count = fulfilled
    stat.short_supply_count = short_supply
    stat.rejected_count = rejected
    stat.expired_count = expired
    stat.on_time_count = 0  # no timestamp evidence
    stat.reliability_score = round(blended_score, 4)
    stat.sample_size = total
    stat.confidence = _confidence_label(total)
    db.flush()
    return stat


def get_or_default_reliability(db: Session, supplier_id: str) -> SupplierReliabilityStat:
    stat = db.query(SupplierReliabilityStat).filter(
        SupplierReliabilityStat.supplier_id == supplier_id
    ).first()
    if stat is None:
        return SupplierReliabilityStat(
            supplier_id=supplier_id,
            reliability_score=NEW_SUPPLIER_PRIOR,
            confidence="low",
            sample_size=0,
        )
    return stat
