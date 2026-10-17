from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_merchant_profile
from app.models.catalog import Product, SupplierInventory, SurplusListing, SurplusOffer
from app.models.core import MerchantProfile, SupplierProfile, User, UserRole
from app.schemas.catalog import (
    SupplierInventoryRead,
    SurplusListingCreate,
    SurplusListingRead,
    SurplusOfferCreate,
    SurplusOfferRead,
)
from app.security import get_current_user
from app.services.reliability import get_or_default_reliability

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/offers", response_model=list[SupplierInventoryRead])
def list_offers(
    product_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    merchant: MerchantProfile = Depends(get_merchant_profile),
) -> list[SupplierInventoryRead]:
    """Market view for merchants: every active supplier listing (or one product's), with
    the quantity actually available to new orders (free to promise -- never safety stock or
    stock already promised), price, MOQ, count freshness and reliability evidence."""
    from app.services.promise import position_for

    q = (
        db.query(SupplierInventory, SupplierProfile, Product)
        .join(SupplierProfile, SupplierInventory.supplier_id == SupplierProfile.id)
        .join(Product, SupplierInventory.product_id == Product.id)
        .filter(SupplierProfile.is_active.is_(True), SupplierInventory.is_available.is_(True))
    )
    if product_id:
        q = q.filter(SupplierInventory.product_id == product_id)
    out = []
    for inv, supplier, product in q.all():
        stat = get_or_default_reliability(db, supplier.id)
        pos = position_for(db, inv)
        out.append(
            SupplierInventoryRead(
                id=inv.id, supplier_id=supplier.id, supplier_name=supplier.business_name,
                product_id=product.id, product_name=product.name, brand=inv.brand, pack_size=inv.pack_size,
                pack_unit=inv.pack_unit, price_per_base_unit=inv.price_per_base_unit,
                stock_qty_base_unit=round(pos.free_to_promise, 3), moq_base_unit=inv.moq_base_unit,
                is_available=inv.is_available, freshness_source=pos.freshness["status"],
                reliability_score=stat.reliability_score, reliability_confidence=stat.confidence,
                reliability_sample_size=stat.sample_size, free_to_promise_base_unit=round(pos.free_to_promise, 3),
                stock_confirmed_at=inv.stock_confirmed_at,
            )
        )
    out.sort(key=lambda o: (o.product_name, o.price_per_base_unit))
    return out


def _offer_to_read(offer: SurplusOffer, db: Session) -> SurplusOfferRead:
    who = db.get(User, offer.offerer_user_id)
    name = who.full_name if who else ""
    if who and who.role == UserRole.MERCHANT and who.merchant_profile:
        name = who.merchant_profile.business_name
    elif who and who.role == UserRole.SUPPLIER and who.supplier_profile:
        name = who.supplier_profile.business_name
    return SurplusOfferRead(id=offer.id, listing_id=offer.listing_id, offerer_user_id=offer.offerer_user_id,
                            qty_requested_base_unit=offer.qty_requested_base_unit,
                            offered_price_per_base_unit=offer.offered_price_per_base_unit, status=offer.status, offerer_name=name)


def _listing_to_read(listing: SurplusListing, product: Product, db: Session, user: User | None = None) -> SurplusListingRead:
    if listing.lister_merchant_id:
        m = db.get(MerchantProfile, listing.lister_merchant_id)
        lister_type, lister_name = "merchant", (m.business_name if m else "Unknown merchant")
    else:
        s = db.get(SupplierProfile, listing.lister_supplier_id)
        lister_type, lister_name = "supplier", (s.business_name if s else "Unknown supplier")
    return SurplusListingRead(
        id=listing.id, product_id=product.id, product_name=product.name, qty_base_unit=listing.qty_base_unit,
        asking_price_per_base_unit=listing.asking_price_per_base_unit, status=listing.status,
        lister_type=lister_type, lister_name=lister_name,
        is_mine=bool(user and _owns_listing(listing, user, db)),
        pending_offer_count=db.query(SurplusOffer).filter(SurplusOffer.listing_id == listing.id, SurplusOffer.status == "pending").count(),
        my_offer=next((_offer_to_read(o, db) for o in db.query(SurplusOffer).filter(
            SurplusOffer.listing_id == listing.id, SurplusOffer.offerer_user_id == user.id).order_by(SurplusOffer.created_at.desc())), None) if user else None,
    )


@router.get("/surplus", response_model=list[SurplusListingRead])
def list_surplus(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[SurplusListingRead]:
    """Dead-Stock Rescue Exchange: open listings from everyone, plus your own closed ones
    (so a lister sees what was matched) and listings you have made an offer on."""
    rows = (
        db.query(SurplusListing, Product)
        .join(Product, SurplusListing.product_id == Product.id)
        .order_by(SurplusListing.created_at.desc())
        .all()
    )
    out = []
    for s, p in rows:
        view = _listing_to_read(s, p, db, user)
        if s.status == "open" or view.is_mine or view.my_offer is not None:
            out.append(view)
    return out


@router.post("/surplus", response_model=SurplusListingRead, status_code=status.HTTP_201_CREATED)
def create_surplus_listing(
    payload: SurplusListingCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SurplusListingRead:
    """Either a merchant (excess stock) or a supplier (overstock) can list surplus."""
    product = db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")

    listing = SurplusListing(
        product_id=payload.product_id, qty_base_unit=payload.qty_base_unit,
        asking_price_per_base_unit=payload.asking_price_per_base_unit,
    )
    if user.role == UserRole.MERCHANT:
        profile = db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).first()
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Merchant profile not found")
        listing.lister_merchant_id = profile.id
    elif user.role == UserRole.SUPPLIER:
        profile = db.query(SupplierProfile).filter(SupplierProfile.user_id == user.id).first()
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier profile not found")
        listing.lister_supplier_id = profile.id
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only merchants and suppliers can list surplus")

    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _listing_to_read(listing, product, db, user)


def _owner_user_id(listing: SurplusListing, db: Session) -> str | None:
    if listing.lister_merchant_id:
        m = db.get(MerchantProfile, listing.lister_merchant_id)
        return m.user_id if m else None
    s = db.get(SupplierProfile, listing.lister_supplier_id) if listing.lister_supplier_id else None
    return s.user_id if s else None


def _owns_listing(listing: SurplusListing, user: User, db: Session) -> bool:
    if listing.lister_merchant_id:
        m = db.get(MerchantProfile, listing.lister_merchant_id)
        return m is not None and m.user_id == user.id
    if listing.lister_supplier_id:
        s = db.get(SupplierProfile, listing.lister_supplier_id)
        return s is not None and s.user_id == user.id
    return False


@router.post("/surplus/{listing_id}/offers", response_model=SurplusOfferRead, status_code=status.HTTP_201_CREATED)
def make_surplus_offer(
    listing_id: str, payload: SurplusOfferCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> SurplusOffer:
    listing = db.get(SurplusListing, listing_id)
    if listing is None or listing.status != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Open listing not found")
    if _owns_listing(listing, user, db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot make an offer on your own listing")
    if payload.qty_requested_base_unit > listing.qty_base_unit + 1e-6:
        raise HTTPException(422, f"Only {listing.qty_base_unit:g} is listed")

    # One live offer per buyer per listing: a new offer revises the pending one.
    offer = db.query(SurplusOffer).filter(SurplusOffer.listing_id == listing_id, SurplusOffer.offerer_user_id == user.id,
                                          SurplusOffer.status == "pending").first()
    if offer is None:
        offer = SurplusOffer(listing_id=listing_id, offerer_user_id=user.id)
        db.add(offer)
    offer.qty_requested_base_unit = payload.qty_requested_base_unit
    offer.offered_price_per_base_unit = payload.offered_price_per_base_unit
    from app.services.notify import notify
    owner = _owner_user_id(listing, db)
    if owner:
        notify(db, owner, "dead_stock", "New dead-stock offer",
               f"Offer for {offer.qty_requested_base_unit:g} {listing.product.base_unit} {listing.product.name} at Rs.{offer.offered_price_per_base_unit:g}.")
    db.commit()
    db.refresh(offer)
    return _offer_to_read(offer, db)


@router.get("/surplus/{listing_id}/offers", response_model=list[SurplusOfferRead])
def list_surplus_offers(
    listing_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[SurplusOffer]:
    listing = db.get(SurplusListing, listing_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
    if not _owns_listing(listing, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the lister can view offers")
    offers = db.query(SurplusOffer).filter(SurplusOffer.listing_id == listing_id).order_by(SurplusOffer.created_at).all()
    return [_offer_to_read(o, db) for o in offers]


@router.post("/surplus/offers/{offer_id}/accept", response_model=SurplusOfferRead)
def accept_surplus_offer(offer_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> SurplusOffer:
    offer = db.get(SurplusOffer, offer_id)
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    listing = db.get(SurplusListing, offer.listing_id)
    if listing is None or not _owns_listing(listing, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the lister can accept an offer")
    if offer.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Offer is already {offer.status}")

    offer.status = "accepted"
    listing.status = "matched"
    for other in db.query(SurplusOffer).filter(SurplusOffer.listing_id == listing.id, SurplusOffer.id != offer.id):
        if other.status == "pending":
            other.status = "declined"
    from app.services.notify import notify
    notify(db, offer.offerer_user_id, "dead_stock", "Dead-stock offer accepted",
           f"Your offer for {offer.qty_requested_base_unit:g} {listing.product.base_unit} {listing.product.name} at Rs.{offer.offered_price_per_base_unit:g} was accepted.")
    db.commit()
    db.refresh(offer)
    return _offer_to_read(offer, db)


@router.post("/surplus/offers/{offer_id}/decline", response_model=SurplusOfferRead)
def decline_surplus_offer(offer_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> SurplusOfferRead:
    offer = db.get(SurplusOffer, offer_id)
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    listing = db.get(SurplusListing, offer.listing_id)
    if listing is None or not _owns_listing(listing, user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the lister can decline an offer")
    if offer.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Offer is already {offer.status}")
    offer.status = "declined"
    db.commit()
    return _offer_to_read(offer, db)
