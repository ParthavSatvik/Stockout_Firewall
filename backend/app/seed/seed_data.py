"""Deterministic demo seed data: Indian wholesale kirana products, merchants,
suppliers, inventory, alias lexicon for code-mixed parsing, and a little fabricated
*historical* order/allocation data purely so supplier reliability scores have real
sample sizes to compute from (not invented accuracy numbers -- the computation is the
same recompute_supplier_reliability() used for live orders).

Run with: python -m app.seed.seed_data   (idempotent: clears and re-seeds demo rows)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.database import Base, SessionLocal, engine
from app.models.catalog import Product, ProductAlias, SupplierInventory
from app.models.continuity import CommitmentLedgerEntry
from app.models.core import MerchantProfile, SupplierProfile, User, UserRole
from app.models.ops import Invoice, InvoiceItem, ReceiptRecord
from app.models.orders import (
    Allocation,
    AllocationPlan,
    AllocationStatus,
    ObjectiveProfile,
    Order,
    OrderItem,
    OrderStatus,
    SupplierEvent,
    SupplierEventType,
)
from app.security import hash_password
from app.services.reliability import recompute_supplier_reliability

DEMO_PASSWORD = "demo1234"


def _now_minus(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _clear_demo_data(db) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()



PRODUCTS = [
    {"name": "Rice", "category": "grains", "base_unit": "kg",
     "aliases": [("rice", "en"), ("akki", "kn"), ("chawal", "hi"), ("basmati rice", "en"), ("sona masoori", "en")]},
    {"name": "Wheat Atta", "category": "grains", "base_unit": "kg",
     "aliases": [("atta", "hi"), ("wheat flour", "en"), ("gehu atta", "hi"), ("godhi hittu", "kn")]},
    {"name": "Toor Dal", "category": "pulses", "base_unit": "kg",
     "aliases": [("toor dal", "hi"), ("arhar dal", "hi"), ("togari bele", "kn"), ("pigeon pea", "en")]},
    {"name": "Moong Dal", "category": "pulses", "base_unit": "kg",
     "aliases": [("moong dal", "hi"), ("hesaru bele", "kn"), ("green gram", "en")]},
    {"name": "Sugar", "category": "staples", "base_unit": "kg",
     "aliases": [("sugar", "en"), ("sakkare", "kn"), ("cheeni", "hi"), ("chini", "hi")]},
    {"name": "Sunflower Oil", "category": "oil", "base_unit": "litre",
     "aliases": [("oil", "en"), ("sunflower oil", "en"), ("enne", "kn"), ("tel", "hi")]},
    {"name": "Salt", "category": "staples", "base_unit": "kg",
     "aliases": [("salt", "en"), ("uppu", "kn"), ("namak", "hi")]},
    {"name": "Besan", "category": "pulses", "base_unit": "kg",
     "aliases": [("besan", "hi"), ("gram flour", "en"), ("kadale hittu", "kn")]},
    {"name": "Tea Powder", "category": "beverages", "base_unit": "kg",
     "aliases": [("tea", "en"), ("tea powder", "en"), ("chai", "hi"), ("chaha pudi", "kn")]},
]

MERCHANTS = [
    {"email": "merchant1@example.com", "full_name": "Ganesh Kirana", "business_name": "Ganesh Kirana Store",
     "city": "Bengaluru", "latitude": 12.9716, "longitude": 77.5946},
    {"email": "merchant2@example.com", "full_name": "Suresh Patel", "business_name": "Patel General Stores",
     "city": "Bengaluru", "latitude": 12.9352, "longitude": 77.6245},
    # Holds only the labelled PromiseGuard demo orders, so the other merchants' history stays clean.
    {"email": "merchant3@example.com", "full_name": "Shree Ram Provisions", "business_name": "Shree Ram Provisions (demo scenario)",
     "city": "Bengaluru", "latitude": 12.9900, "longitude": 77.5700},
]

# (business_name, city, lat, lon, capacity_kg_per_day)
SUPPLIERS = [
    {"email": "anand@example.com", "business_name": "Anand Wholesale Grains", "city": "Bengaluru",
     "latitude": 12.9980, "longitude": 77.5500, "capacity": 500.0},
    {"email": "lakshmi@example.com", "business_name": "Lakshmi Traders", "city": "Bengaluru",
     "latitude": 12.9100, "longitude": 77.6400, "capacity": 800.0},
    {"email": "balaji@example.com", "business_name": "Sri Balaji Provisions", "city": "Bengaluru",
     "latitude": 13.0300, "longitude": 77.6200, "capacity": 400.0},
    {"email": "newco@example.com", "business_name": "NewCo Supplies (joined this month)", "city": "Bengaluru",
     "latitude": 12.9500, "longitude": 77.5000, "capacity": 300.0},
]

# Per-supplier, per-product offers: (supplier_business_name, product_name, brand, pack_size, pack_unit, price, stock, moq)
OFFERS = [
    ("Anand Wholesale Grains", "Rice", "Local", 25.0, "kg", 38.0, 150.0, 25.0),
    ("Lakshmi Traders", "Rice", "Premium", 25.0, "kg", 41.0, 400.0, 25.0),
    ("Sri Balaji Provisions", "Rice", "Local", 10.0, "kg", 40.0, 120.0, 10.0),

    ("Anand Wholesale Grains", "Wheat Atta", "Local", 25.0, "kg", 32.0, 300.0, 25.0),
    ("Lakshmi Traders", "Wheat Atta", "Premium", 10.0, "kg", 34.0, 200.0, 10.0),

    ("Lakshmi Traders", "Toor Dal", "Standard", 25.0, "kg", 110.0, 150.0, 25.0),
    ("Sri Balaji Provisions", "Toor Dal", "Standard", 5.0, "kg", 115.0, 80.0, 5.0),

    ("Anand Wholesale Grains", "Moong Dal", "Standard", 5.0, "kg", 95.0, 60.0, 5.0),
    ("Lakshmi Traders", "Moong Dal", "Standard", 25.0, "kg", 98.0, 100.0, 25.0),

    ("Anand Wholesale Grains", "Sugar", "Standard", 25.0, "kg", 42.0, 300.0, 25.0),
    ("Sri Balaji Provisions", "Sugar", "Standard", 50.0, "kg", 41.0, 200.0, 50.0),

    ("Lakshmi Traders", "Sunflower Oil", "Fortune", 15.0, "litre", 118.0, 150.0, 15.0),
    ("Anand Wholesale Grains", "Sunflower Oil", "Local", 5.0, "litre", 120.0, 100.0, 5.0),

    ("Sri Balaji Provisions", "Salt", "Tata", 1.0, "kg", 22.0, 500.0, 10.0),
    ("Anand Wholesale Grains", "Salt", "Local", 25.0, "kg", 18.0, 200.0, 25.0),

    ("Lakshmi Traders", "Besan", "Standard", 25.0, "kg", 85.0, 100.0, 25.0),
    ("NewCo Supplies (joined this month)", "Besan", "Standard", 25.0, "kg", 80.0, 150.0, 25.0),

    ("Sri Balaji Provisions", "Tea Powder", "Standard", 1.0, "kg", 280.0, 50.0, 1.0),
    ("NewCo Supplies (joined this month)", "Tea Powder", "Standard", 0.5, "kg", 265.0, 80.0, 0.5),

    # NewCo also offers rice cheaply but has zero track record -- demonstrates the
    # "low confidence, not fabricated accuracy" reliability rule for a brand-new supplier.
    ("NewCo Supplies (joined this month)", "Rice", "Budget", 25.0, "kg", 36.0, 100.0, 25.0),
]

# historical outcomes used only to generate realistic reliability sample sizes
HISTORY = {
    "Anand Wholesale Grains": ["fulfilled"] * 6 + ["short_supply"] * 2 + ["rejected"],
    "Lakshmi Traders": ["fulfilled"] * 11 + ["short_supply"],
    "Sri Balaji Provisions": ["fulfilled"] * 3 + ["rejected"],
    "NewCo Supplies (joined this month)": [],  # deliberately no history
}


# Per-listing PromiseGuard settings: (supplier, product) -> safety stock, hours since
# the last physical count. Anand's moong dal is deliberately stale so the Copilot's
# "count stock" action and the planner's 24h exclusion can be demonstrated.
SAFETY_STOCK = {("Anand Wholesale Grains", "Wheat Atta"): 10.0, ("Lakshmi Traders", "Rice"): 40.0}
COUNT_AGE_HOURS = {("Anand Wholesale Grains", "Moong Dal"): 30}

# Seeded deliveries that carry ready-by / dispatch timestamps so the Trust Passport has
# dated evidence: supplier -> (on-time deliveries, late deliveries, invoiced + received).
DATED_HISTORY = {"Lakshmi Traders": (10, 1, 6), "Anand Wholesale Grains": (4, 2, 2), "Sri Balaji Provisions": (3, 0, 0)}


def _seed_history(db, merchant: MerchantProfile, supplier: SupplierProfile, product: Product, outcomes: list[str]) -> None:
    status_map = {
        "fulfilled": AllocationStatus.FULFILLED,
        "short_supply": AllocationStatus.SHORT_SUPPLY,
        "rejected": AllocationStatus.REJECTED,
    }
    for i, outcome in enumerate(outcomes):
        days_ago = 90 - i * 5
        order = Order(
            merchant_id=merchant.id, status=OrderStatus.FULFILLED, objective_profile=ObjectiveProfile.CHEAPEST,
            created_at=_now_minus(days_ago), updated_at=_now_minus(days_ago),
        )
        db.add(order)
        db.flush()
        item = OrderItem(order_id=order.id, product_id=product.id, requested_qty_base_unit=20.0)
        db.add(item)
        db.flush()
        plan = AllocationPlan(
            order_id=order.id, objective_profile=ObjectiveProfile.CHEAPEST, is_selected=True, is_feasible=True,
            replan_reason="initial", created_at=_now_minus(days_ago), updated_at=_now_minus(days_ago),
        )
        db.add(plan)
        db.flush()
        status = status_map[outcome]
        confirmed_qty = 20.0 if outcome == "fulfilled" else (8.0 if outcome == "short_supply" else 0.0)
        alloc = Allocation(
            plan_id=plan.id, order_item_id=item.id, supplier_id=supplier.id, product_id=product.id,
            allocated_qty_base_unit=20.0, unit_price=40.0, pack_count=1, status=status,
            confirmed_qty_base_unit=confirmed_qty, created_at=_now_minus(days_ago), updated_at=_now_minus(days_ago),
        )
        db.add(alloc)
        db.flush()
        event_type = {
            "fulfilled": SupplierEventType.DELIVERED, "short_supply": SupplierEventType.SHORT_SUPPLY,
            "rejected": SupplierEventType.REJECTED,
        }[outcome]
        created = _now_minus(days_ago)
        response_at = created + timedelta(minutes=20 + (i * 7) % 60)
        on_time, late, documented = DATED_HISTORY.get(supplier.business_name, (0, 0, 0))
        fulfilled_index = outcomes[: i + 1].count("fulfilled") - 1
        if outcome == "fulfilled" and fulfilled_index < on_time + late:
            ready_by = created + timedelta(hours=24)
            slip = timedelta(hours=5) if fulfilled_index >= on_time else timedelta(minutes=-60)
            alloc.confirmed_ready_by = ready_by
            alloc.route_duration_minutes = 40.0
            alloc.fulfillment_stage = "delivered"
            db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.CONFIRMED,
                                 payload={"confirmed_qty_base_unit": 20.0}, created_at=response_at))
            db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DISPATCHED, payload={}, created_at=ready_by + slip))
            db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DELIVERED, payload={},
                                 created_at=ready_by + slip + timedelta(minutes=45)))
            if fulfilled_index < documented:
                invoice = Invoice(order_id=order.id, supplier_id=supplier.id, total_amount=20.0 * 40.0,
                                  invoice_number=f"SEED-{supplier.business_name[:3].upper()}-{i}", created_at=ready_by)
                db.add(invoice)
                db.flush()
                db.add(InvoiceItem(invoice_id=invoice.id, product_id=product.id, qty_base_unit=20.0, unit_price=40.0))
                db.add(ReceiptRecord(order_id=order.id, allocation_id=alloc.id, product_id=product.id,
                                     received_qty_base_unit=20.0, received_at=ready_by + slip + timedelta(hours=1)))
            continue
        db.add(SupplierEvent(allocation_id=alloc.id, event_type=event_type, payload={"seeded_history": True}, created_at=response_at))
        if outcome == "short_supply":
            # The partial was disclosed at quote time and the 8 kg actually delivered, so the
            # line is closed rather than left as a live reservation from months ago.
            alloc.status = AllocationStatus.FULFILLED
            alloc.fulfillment_stage = "delivered"
            db.add(SupplierEvent(allocation_id=alloc.id, event_type=SupplierEventType.DELIVERED, payload={"seeded_history": True},
                                 created_at=created + timedelta(days=1)))
    db.flush()


def _seed_promise_scenario(db, merchant: MerchantProfile, supplier: SupplierProfile, product: Product) -> None:
    """DEMO SEED -- PromiseGuard "prevention" moment. Anand has 80 kg Wheat Atta on hand,
    50 kg already committed to one order, 10 kg safety stock, and a new 40 kg request.
    Free to promise (80 - 50 - 10 = 20 kg) is computed live by app.services.promise."""
    inv = db.query(SupplierInventory).filter_by(supplier_id=supplier.id, product_id=product.id).one()
    now = datetime.now(UTC)
    on_hand, committed = 80.0, 50.0
    inv.reported_on_hand_base_unit = on_hand
    inv.stock_qty_base_unit = on_hand - committed
    inv.stock_confirmed_at = now - timedelta(hours=1)
    ceiling = {product.id: round(inv.price_per_base_unit * 1.15, 4)}

    def order_with_line(qty: float, status: AllocationStatus, order_status: OrderStatus, note: str) -> Allocation:
        order = Order(merchant_id=merchant.id, status=order_status, objective_profile=ObjectiveProfile.FASTEST,
                      price_tolerance_pct=15.0, min_reliability=0.3, budget_cap=5000.0, max_suppliers=3,
                      raw_input_text=f"[demo seed] {note}")
        db.add(order)
        db.flush()
        item = OrderItem(order_id=order.id, product_id=product.id, requested_qty_base_unit=qty, notes="demo seed")
        db.add(item)
        db.flush()
        plan = AllocationPlan(order_id=order.id, objective_profile=ObjectiveProfile.FASTEST, is_selected=True,
                              is_feasible=True, replan_reason="initial", total_product_cost=qty * inv.price_per_base_unit,
                              total_cost=qty * inv.price_per_base_unit + 120.0, total_delivery_cost=120.0, supplier_count=1,
                              estimated_delivery_hours=0.8, explanation={"price_ceilings": ceiling, "demo_seed": True})
        db.add(plan)
        db.flush()
        alloc = Allocation(plan_id=plan.id, inventory_id=inv.id, order_item_id=item.id, supplier_id=supplier.id,
                           product_id=product.id, allocated_qty_base_unit=qty, unit_price=inv.price_per_base_unit,
                           pack_count=max(1, int(qty // inv.pack_size)), status=status, route_distance_km=6.1,
                           route_duration_minutes=48.0, route_cost=120.0, confirmation_expires_at=now + timedelta(hours=6))
        db.add(alloc)
        db.flush()
        return alloc

    held = order_with_line(committed, AllocationStatus.CONFIRMED, OrderStatus.CONFIRMED, "50 kg atta already committed")
    held.confirmed_qty_base_unit = committed
    held.confirmed_ready_by = now + timedelta(hours=20)
    held.fulfillment_stage = "reserved"
    db.add(SupplierEvent(allocation_id=held.id, event_type=SupplierEventType.CONFIRMED,
                         payload={"confirmed_qty_base_unit": committed, "seeded_demo": True}, created_at=now - timedelta(hours=2)))
    db.add(CommitmentLedgerEntry(actor_role="system", supplier_id=supplier.id, order_id=held.plan.order_id, allocation_id=held.id,
                                 inventory_id=inv.id, action="commitment_accepted", from_state="proposed", to_state="confirmed",
                                 qty_base_unit=committed, reason="demo seed", payload={"demo_seed": True}))
    order_with_line(40.0, AllocationStatus.PROPOSED, OrderStatus.AWAITING_CONFIRMATION, "40 kg atta request exceeding free-to-promise")
    db.flush()


def run() -> None:
    from app.config import get_settings
    settings = get_settings()
    if not settings.demo_mode or settings.app_env != "local":
        raise RuntimeError("Seed reset is permitted only in local demo mode")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _clear_demo_data(db)

        products_by_name: dict[str, Product] = {}
        for p in PRODUCTS:
            product = Product(name=p["name"], category=p["category"], base_unit=p["base_unit"])
            db.add(product)
            db.flush()
            for alias_text, lang in p["aliases"]:
                db.add(ProductAlias(product_id=product.id, alias_text=alias_text, language=lang))
            products_by_name[p["name"]] = product
        db.flush()

        merchants_by_email: dict[str, MerchantProfile] = {}
        for m in MERCHANTS:
            user = User(email=m["email"], full_name=m["full_name"], role=UserRole.MERCHANT,
                        hashed_password=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
            profile = MerchantProfile(
                user_id=user.id, business_name=m["business_name"], city=m["city"],
                latitude=m["latitude"], longitude=m["longitude"],
            )
            db.add(profile)
            db.flush()
            merchants_by_email[m["email"]] = profile

        suppliers_by_name: dict[str, SupplierProfile] = {}
        for s in SUPPLIERS:
            user = User(email=s["email"], full_name=s["business_name"], role=UserRole.SUPPLIER,
                        hashed_password=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
            profile = SupplierProfile(
                user_id=user.id, business_name=s["business_name"], city=s["city"],
                latitude=s["latitude"], longitude=s["longitude"], delivery_capacity_kg_per_day=s["capacity"],
            )
            db.add(profile)
            db.flush()
            suppliers_by_name[s["business_name"]] = profile

        # admin user for the control tower
        admin_user = User(email="admin@example.com", full_name="Platform Admin", role=UserRole.ADMIN,
                           hashed_password=hash_password(DEMO_PASSWORD))
        db.add(admin_user)

        now = datetime.now(UTC)
        for supplier_name, product_name, brand, pack_size, pack_unit, price, stock, moq in OFFERS:
            key = (supplier_name, product_name)
            db.add(SupplierInventory(
                supplier_id=suppliers_by_name[supplier_name].id, product_id=products_by_name[product_name].id,
                brand=brand, pack_size=pack_size, pack_unit=pack_unit, price_per_base_unit=price,
                stock_qty_base_unit=stock, moq_base_unit=moq, is_available=True, freshness_source="seed",
                safety_stock_base_unit=SAFETY_STOCK.get(key, 0.0), reported_on_hand_base_unit=stock,
                stock_confirmed_at=now - timedelta(hours=COUNT_AGE_HOURS.get(key, 2)),
            ))
        db.flush()

        demo_merchant = merchants_by_email["merchant1@example.com"]
        for supplier_name, outcomes in HISTORY.items():
            if not outcomes:
                continue
            _seed_history(db, demo_merchant, suppliers_by_name[supplier_name], products_by_name["Rice"], outcomes)
        _seed_promise_scenario(db, merchants_by_email["merchant3@example.com"], suppliers_by_name["Anand Wholesale Grains"],
                               products_by_name["Wheat Atta"])

        db.commit()

        for supplier in suppliers_by_name.values():
            recompute_supplier_reliability(db, supplier.id)
        db.commit()

        print(f"Seeded {len(PRODUCTS)} products, {len(MERCHANTS)} merchants, {len(SUPPLIERS)} suppliers, "
              f"{len(OFFERS)} inventory offers.")
        print(f"All demo accounts use password: {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
