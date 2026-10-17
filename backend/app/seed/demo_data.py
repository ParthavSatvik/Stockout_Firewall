"""DEMO SEED -- rich, clearly labelled sample data so every merchant screen has something
real to compute from. All rows are inputs (orders, quotes, prices, listings); every number
shown in the app is still calculated by the normal services from them.

merchant1 (Ganesh Kirana) gets a buying history across products with different cadences
(some due now, some not), weekly supplier price history, selling prices (one deliberately
thin), cash on hand, and Dead-Stock listings with offers in both directions. merchant2 is
left without history on purpose: it demonstrates the honest empty states for a new shop.

History orders carry plan totals but no supplier allocations, so supplier reliability and
Trust Passport evidence are unaffected.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.models.catalog import (
    MerchantProductPrice,
    PriceObservation,
    Product,
    SupplierInventory,
    SurplusListing,
    SurplusOffer,
)
from app.models.core import MerchantProfile, SupplierProfile
from app.models.orders import AllocationPlan, ObjectiveProfile, Order, OrderItem, OrderStatus

# product -> (qty per order, every N days, days since the last order). Due when
# days_since_last >= 0.85 * N (Procurement Autopilot / Stockout Radar).
BUYING_PATTERN = {
    "Sugar": (25.0, 7, 8),          # due now
    "Sunflower Oil": (15.0, 10, 11),  # due now
    "Tea Powder": (2.0, 14, 20),    # overdue -> high stockout risk
    "Wheat Atta": (25.0, 9, 4),     # recently bought, not due
    "Toor Dal": (10.0, 15, 6),      # not due
    "Salt": (10.0, 20, 18),         # due soon
}
REPEATS = 7
SELLING_PRICES = {"Rice": 46.0, "Sugar": 43.0, "Sunflower Oil": 132.0, "Tea Powder": 330.0, "Wheat Atta": 38.0, "Toor Dal": 124.0}
CASH_ON_HAND = 25000.0
DELIVERY_FEE = 95.0


def _cheapest_price(db, product: Product) -> float:
    rows = db.query(SupplierInventory).filter(SupplierInventory.product_id == product.id).all()
    return min(r.price_per_base_unit for r in rows) if rows else 0.0


def seed_buying_history(db, merchant: MerchantProfile, products: dict[str, Product]) -> None:
    now = datetime.now(UTC)
    for name, (qty, every, last_ago) in BUYING_PATTERN.items():
        product = products[name]
        price = _cheapest_price(db, product)
        for k in range(REPEATS):
            when = now - timedelta(days=last_ago + k * every, hours=3 + k)
            order = Order(merchant_id=merchant.id, status=OrderStatus.FULFILLED, objective_profile=ObjectiveProfile.CHEAPEST,
                          raw_input_text=f"[demo seed] {qty:g} kg {name.lower()}", created_at=when, updated_at=when,
                          min_reliability=0.3, price_tolerance_pct=15.0)
            db.add(order)
            db.flush()
            db.add(OrderItem(order_id=order.id, product_id=product.id, requested_qty_base_unit=qty, notes="demo seed"))
            cost = round(qty * price, 2)
            db.add(AllocationPlan(order_id=order.id, objective_profile=ObjectiveProfile.CHEAPEST, is_selected=True, is_feasible=True,
                                  replan_reason="initial", total_product_cost=cost, total_delivery_cost=DELIVERY_FEE,
                                  total_cost=cost + DELIVERY_FEE, estimated_delivery_hours=1.5, supplier_count=1,
                                  explanation={"demo_seed": True}, created_at=when, updated_at=when))
    merchant.available_cash_on_hand = CASH_ON_HAND
    for name, sell in SELLING_PRICES.items():
        db.add(MerchantProductPrice(merchant_id=merchant.id, product_id=products[name].id, selling_price_per_base_unit=sell))
    db.flush()


def seed_price_history(db, weeks: int = 26) -> None:
    """Weekly quotes per listing, drifting around today's price and ending exactly at it."""
    now = datetime.now(UTC)
    for inv in db.query(SupplierInventory).all():
        phase = (hash(inv.supplier_id + inv.product_id) % 628) / 100
        for w in range(weeks, 0, -1):
            drift = 0.06 * math.sin(w / 4 + phase) + 0.002 * w  # prices were a little higher in the past
            db.add(PriceObservation(supplier_id=inv.supplier_id, product_id=inv.product_id,
                                    price_per_base_unit=round(inv.price_per_base_unit * (1 + drift), 2),
                                    observed_at=now - timedelta(days=7 * w)))
        db.add(PriceObservation(supplier_id=inv.supplier_id, product_id=inv.product_id,
                                price_per_base_unit=inv.price_per_base_unit, observed_at=now - timedelta(hours=2)))
    db.flush()


def seed_dead_stock(db, merchants: dict[str, MerchantProfile], suppliers: dict[str, SupplierProfile], products: dict[str, Product]) -> None:
    m1, m2 = merchants["merchant1@example.com"], merchants["merchant2@example.com"]
    lak, bal, anand = suppliers["Lakshmi Traders"], suppliers["Sri Balaji Provisions"], suppliers["Anand Wholesale Grains"]
    dal = SurplusListing(lister_supplier_id=lak.id, product_id=products["Toor Dal"].id, qty_base_unit=60, asking_price_per_base_unit=100)
    sugar = SurplusListing(lister_supplier_id=bal.id, product_id=products["Sugar"].id, qty_base_unit=40, asking_price_per_base_unit=38)
    besan = SurplusListing(lister_merchant_id=m2.id, product_id=products["Besan"].id, qty_base_unit=15, asking_price_per_base_unit=78)
    oil = SurplusListing(lister_merchant_id=m1.id, product_id=products["Sunflower Oil"].id, qty_base_unit=12, asking_price_per_base_unit=112)
    db.add_all([dal, sugar, besan, oil])
    db.flush()
    db.add_all([
        SurplusOffer(listing_id=dal.id, offerer_user_id=m1.user_id, qty_requested_base_unit=30, offered_price_per_base_unit=95),
        SurplusOffer(listing_id=besan.id, offerer_user_id=anand.user_id, qty_requested_base_unit=15, offered_price_per_base_unit=74),
        SurplusOffer(listing_id=oil.id, offerer_user_id=m2.user_id, qty_requested_base_unit=12, offered_price_per_base_unit=108),
        SurplusOffer(listing_id=oil.id, offerer_user_id=bal.user_id, qty_requested_base_unit=6, offered_price_per_base_unit=110),
    ])
    db.flush()
