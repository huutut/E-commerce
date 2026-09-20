from sqlmodel import Session, col, select

from commerce.domain.models import AdminUser, InventoryAdjustment, Product
from commerce.repositories.audit import SYSTEM_ACTOR_EMAIL


def adjust_inventory(
    session: Session,
    *,
    product: Product,
    actor: AdminUser | None,
    change_quantity: int,
    reason: str,
) -> InventoryAdjustment:
    stock_before = product.stock_on_hand
    stock_after = stock_before + change_quantity
    if stock_after < 0:
        raise ValueError("库存不能调整为负数")

    product.stock_on_hand = stock_after
    adjustment = InventoryAdjustment(
        product_id=product.id,
        sku=product.sku,
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else SYSTEM_ACTOR_EMAIL,
        change_quantity=change_quantity,
        stock_before=stock_before,
        stock_after=stock_after,
        reason=reason.strip()[:500],
    )
    session.add(product)
    session.add(adjustment)
    return adjustment


def list_inventory_adjustments(
    session: Session,
    *,
    sku: str,
    limit: int = 20,
) -> list[InventoryAdjustment]:
    statement = (
        select(InventoryAdjustment)
        .where(InventoryAdjustment.sku == sku)
        .order_by(col(InventoryAdjustment.created_at).desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())
