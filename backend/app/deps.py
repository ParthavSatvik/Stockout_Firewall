from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.core import MerchantProfile, SupplierProfile, User, UserRole
from app.security import get_current_user


def get_merchant_profile(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> MerchantProfile:
    if user.role != UserRole.MERCHANT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Merchant role required")
    profile = db.query(MerchantProfile).filter(MerchantProfile.user_id == user.id).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Merchant profile not found")
    return profile


def get_supplier_profile(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SupplierProfile:
    if user.role != UserRole.SUPPLIER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Supplier role required")
    profile = db.query(SupplierProfile).filter(SupplierProfile.user_id == user.id).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier profile not found")
    return profile


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user
