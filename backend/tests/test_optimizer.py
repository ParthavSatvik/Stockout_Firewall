from app.services.optimizer import (
    ItemRequest,
    OfferCandidate,
    OptimizerPolicy,
    SupplierCapacity,
    solve_allocation,
)


def make_offer(offer_id, supplier_id, product_id="rice", price=40.0, stock=200.0, pack=25.0,
                moq=0.0, reliability=0.9, distance=5.0):
    return OfferCandidate(
        offer_id=offer_id,
        supplier_id=supplier_id,
        supplier_name=supplier_id,
        product_id=product_id,
        pack_size_base_unit=pack,
        price_per_base_unit=price,
        stock_qty_base_unit=stock,
        moq_base_unit=moq,
        reliability_score=reliability,
        reliability_confidence="high",
        distance_km=distance,
    )


def test_basic_feasible_allocation_meets_full_quantity():
    items = [ItemRequest("item1", "rice", "Rice", 100.0, True)]
    offers = {"rice": [make_offer("o1", "s1", price=38.0, stock=200.0)]}
    capacities = {"s1": SupplierCapacity("s1", 1000.0)}
    policy = OptimizerPolicy("cheapest", budget_cap=None, price_tolerance_pct=10, min_reliability=0.5, max_suppliers=4)

    result = solve_allocation(items, offers, capacities, policy)

    assert result.is_feasible
    assert sum(a.allocated_qty_base_unit for a in result.allocations) >= 100.0
    assert result.shortfall_by_item["item1"] == 0.0


def test_insufficient_stock_produces_partial_basket_not_hard_failure():
    items = [ItemRequest("item1", "rice", "Rice", 100.0, True)]
    offers = {"rice": [make_offer("o1", "s1", price=38.0, stock=40.0, pack=25.0)]}
    capacities = {"s1": SupplierCapacity("s1", 1000.0)}
    policy = OptimizerPolicy("cheapest", budget_cap=None, price_tolerance_pct=10, min_reliability=0.5, max_suppliers=4)

    result = solve_allocation(items, offers, capacities, policy)

    assert not result.is_feasible
    assert result.shortfall_by_item["item1"] > 0
    assert len(result.allocations) >= 1  # still returns the best partial basket
    assert result.infeasible_reasons


def test_failover_reallocates_remaining_shortfall_to_second_supplier():
    """Mirrors the core demo scenario: primary confirms 40 of 100kg then fails;
    the remaining 60kg must be sourced from an alternative supplier."""
    items = [ItemRequest("item1", "rice", "Rice", 60.0, True)]
    offers = {
        "rice": [
            make_offer("o1", "primary", price=38.0, stock=5.0),  # primary nearly exhausted after failure
            make_offer("o2", "backup", price=41.0, stock=200.0, reliability=0.85),
        ]
    }
    capacities = {"primary": SupplierCapacity("primary", 1000.0), "backup": SupplierCapacity("backup", 1000.0)}
    policy = OptimizerPolicy("cheapest", budget_cap=None, price_tolerance_pct=15, min_reliability=0.5, max_suppliers=4)

    result = solve_allocation(items, offers, capacities, policy)

    assert result.is_feasible
    backup_alloc = [a for a in result.allocations if a.supplier_id == "backup"]
    assert backup_alloc
    assert sum(a.allocated_qty_base_unit for a in result.allocations) >= 60.0


def test_reliability_filter_excludes_low_reliability_supplier():
    items = [ItemRequest("item1", "rice", "Rice", 50.0, True)]
    offers = {"rice": [make_offer("o1", "s1", price=35.0, stock=100.0, reliability=0.3)]}
    capacities = {"s1": SupplierCapacity("s1", 1000.0)}
    policy = OptimizerPolicy("cheapest", budget_cap=None, price_tolerance_pct=10, min_reliability=0.6, max_suppliers=4)

    result = solve_allocation(items, offers, capacities, policy)

    assert not result.is_feasible
    assert not result.allocations
    assert any("reliability" in r for r in result.infeasible_reasons)


def test_price_tolerance_excludes_expensive_offer():
    items = [ItemRequest("item1", "rice", "Rice", 50.0, True)]
    offers = {
        "rice": [
            make_offer("o1", "cheap", price=35.0, stock=10.0),
            make_offer("o2", "expensive", price=60.0, stock=100.0),
        ]
    }
    capacities = {"cheap": SupplierCapacity("cheap", 1000.0), "expensive": SupplierCapacity("expensive", 1000.0)}
    policy = OptimizerPolicy("cheapest", budget_cap=None, price_tolerance_pct=10, min_reliability=0.5, max_suppliers=4)

    result = solve_allocation(items, offers, capacities, policy)

    used_suppliers = {a.supplier_id for a in result.allocations}
    assert "expensive" not in used_suppliers


def test_budget_cap_is_respected():
    items = [ItemRequest("item1", "rice", "Rice", 100.0, True)]
    offers = {"rice": [make_offer("o1", "s1", price=50.0, stock=200.0, pack=25.0)]}
    capacities = {"s1": SupplierCapacity("s1", 1000.0)}
    policy = OptimizerPolicy("cheapest", budget_cap=1000.0, price_tolerance_pct=10, min_reliability=0.5, max_suppliers=4)

    result = solve_allocation(items, offers, capacities, policy)

    assert result.total_product_cost <= 1000.0 + 1e-6


def test_max_suppliers_constraint_limits_supplier_count():
    items = [
        ItemRequest("item1", "rice", "Rice", 30.0, True),
        ItemRequest("item2", "atta", "Atta", 30.0, True),
        ItemRequest("item3", "dal", "Dal", 30.0, True),
    ]
    offers = {
        "rice": [make_offer("o1", "s1", product_id="rice", price=40, stock=100, pack=25)],
        "atta": [make_offer("o2", "s2", product_id="atta", price=35, stock=100, pack=25)],
        "dal": [make_offer("o3", "s3", product_id="dal", price=90, stock=100, pack=25)],
    }
    capacities = {s: SupplierCapacity(s, 1000.0) for s in ("s1", "s2", "s3")}
    policy = OptimizerPolicy("cheapest", budget_cap=None, price_tolerance_pct=10, min_reliability=0.5, max_suppliers=2)

    result = solve_allocation(items, offers, capacities, policy)

    used_suppliers = {a.supplier_id for a in result.allocations}
    assert len(used_suppliers) <= 2
