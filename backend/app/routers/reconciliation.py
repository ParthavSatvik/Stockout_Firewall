from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile, get_supplier_profile
from app.models.catalog import Product
from app.models.core import MerchantProfile, SupplierProfile
from app.models.ops import Invoice, InvoiceItem, ReceiptRecord
from app.models.orders import Allocation, AllocationPlan, Order, OrderItem
from app.schemas.orders import InvoiceCreate, ReceiptCreate, ReconciliationLine, ReconciliationResponse

router = APIRouter(prefix="/api/orders", tags=["reconciliation"])

PRICE_DISCREPANCY_TOLERANCE_PCT = 2.0


@router.post("/{order_id}/invoices", status_code=status.HTTP_201_CREATED)
def upload_invoice(
    order_id: str, payload: InvoiceCreate, db: Session = Depends(get_db),
    supplier: SupplierProfile = Depends(get_supplier_profile),
) -> dict:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    has_allocation = db.query(Allocation).join(
        Allocation.plan
    ).filter(Allocation.supplier_id == supplier.id, AllocationPlan.order_id == order_id, AllocationPlan.is_selected.is_(True)).first()
    if has_allocation is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No allocation for this supplier on this order")

    if payload.order_id != order_id or any(i.product_id not in {x.product_id for x in order.items} for i in payload.items):
        raise HTTPException(422, "Invoice does not match this order")
    invoice = Invoice(order_id=order_id, supplier_id=supplier.id, invoice_number=payload.invoice_number)
    db.add(invoice)
    db.flush()
    total = 0.0
    for item in payload.items:
        db.add(InvoiceItem(invoice_id=invoice.id, product_id=item.product_id, qty_base_unit=item.qty_base_unit, unit_price=item.unit_price))
        total += item.qty_base_unit * item.unit_price
    invoice.total_amount = round(total, 2)
    db.commit()
    return {"invoice_id": invoice.id, "total_amount": invoice.total_amount}


@router.post("/{order_id}/receipts", status_code=status.HTTP_201_CREATED)
def record_receipt(
    order_id: str, payload: ReceiptCreate, db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> dict:
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    allocation = db.get(Allocation, payload.allocation_id)
    if not allocation or allocation.plan.order_id != order_id or allocation.product_id != payload.product_id or not allocation.plan.is_selected:
        raise HTTPException(422, "Receipt allocation/product must belong to the selected order plan")
    if db.query(ReceiptRecord).filter(ReceiptRecord.allocation_id == allocation.id).first():
        raise HTTPException(409, "Receipt already recorded for this allocation")
    receipt = ReceiptRecord(
        order_id=order_id, allocation_id=payload.allocation_id, product_id=payload.product_id,
        received_qty_base_unit=payload.received_qty_base_unit,
    )
    db.add(receipt)
    db.commit()
    return {"receipt_id": receipt.id}


@router.get("/{order_id}/reconciliation", response_model=ReconciliationResponse)
def reconcile_order(
    order_id: str, db: Session = Depends(get_db), merchant: MerchantProfile = Depends(get_merchant_profile)
) -> ReconciliationResponse:
    """Order Truth Engine: compares what was ordered, what was invoiced, and what was
    actually received, and flags missing goods, unexpected prices and billing gaps."""
    order = db.get(Order, order_id)
    if order is None or order.merchant_id != merchant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    invoices = db.query(Invoice).filter(Invoice.order_id == order_id).all()
    invoice_items: list[InvoiceItem] = [ii for inv in invoices for ii in inv.items]
    receipts = db.query(ReceiptRecord).filter(ReceiptRecord.order_id == order_id).all()

    selected_plan = next((p for p in order.plans if p.is_selected), None)
    allocations = selected_plan.allocations if selected_plan else []

    lines = []
    has_discrepancies = False
    for item in items:
        product = db.get(Product, item.product_id)
        invoiced_qty = sum(ii.qty_base_unit for ii in invoice_items if ii.product_id == item.product_id)
        received_qty = sum(r.received_qty_base_unit for r in receipts if r.product_id == item.product_id)
        invoice_prices = [ii.unit_price for ii in invoice_items if ii.product_id == item.product_id]
        invoiced_unit_price = sum(invoice_prices) / len(invoice_prices) if invoice_prices else None
        alloc_prices = [a.unit_price for a in allocations if a.product_id == item.product_id]
        allocated_unit_price = sum(alloc_prices) / len(alloc_prices) if alloc_prices else None

        ordered_vs_invoiced_diff = round(invoiced_qty - item.requested_qty_base_unit, 3)
        invoiced_vs_received_diff = round(received_qty - invoiced_qty, 3)
        price_diff = None
        flags = []
        if invoiced_unit_price is not None and allocated_unit_price is not None:
            price_diff = round(invoiced_unit_price - allocated_unit_price, 2)
            if abs(price_diff) > allocated_unit_price * (PRICE_DISCREPANCY_TOLERANCE_PCT / 100.0):
                flags.append("unexpected_price")
        if abs(ordered_vs_invoiced_diff) > 1e-6:
            flags.append("ordered_invoiced_mismatch")
        if abs(invoiced_vs_received_diff) > 1e-6:
            flags.append("invoiced_received_mismatch")
        if invoice_prices and received_qty < invoiced_qty - 1e-6:
            flags.append("missing_goods")

        if flags:
            has_discrepancies = True

        lines.append(
            ReconciliationLine(
                product_id=item.product_id, product_name=product.name if product else item.product_id,
                ordered_qty=item.requested_qty_base_unit, invoiced_qty=round(invoiced_qty, 3),
                received_qty=round(received_qty, 3), ordered_vs_invoiced_diff=ordered_vs_invoiced_diff,
                invoiced_vs_received_diff=invoiced_vs_received_diff, invoiced_unit_price=invoiced_unit_price,
                allocated_unit_price=allocated_unit_price, price_diff=price_diff, flags=flags,
            )
        )

    return ReconciliationResponse(order_id=order_id, lines=lines, has_discrepancies=has_discrepancies)
