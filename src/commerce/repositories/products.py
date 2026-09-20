from sqlmodel import Session, col, select

from commerce.domain.models import Product, ProductStatus


def get_product_by_sku(session: Session, sku: str) -> Product | None:
    statement = select(Product).where(Product.sku == sku)
    return session.exec(statement).first()


def list_active_products(
    session: Session,
    *,
    query: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Product]:
    statement = select(Product).where(Product.status == ProductStatus.ACTIVE)
    if query:
        search = f"%{query}%"
        statement = statement.where(
            col(Product.sku).ilike(search)
            | col(Product.name).ilike(search)
            | col(Product.description).ilike(search)
        )
    if category:
        statement = statement.where(Product.category == category)
    statement = statement.offset(offset).limit(limit).order_by(col(Product.created_at).desc())
    return list(session.exec(statement).all())


def list_products(
    session: Session,
    *,
    query: str | None = None,
    category: str | None = None,
    status: ProductStatus | None = None,
    low_stock: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Product]:
    statement = select(Product)
    if query:
        search = f"%{query}%"
        statement = statement.where(
            col(Product.sku).ilike(search)
            | col(Product.name).ilike(search)
            | col(Product.description).ilike(search)
        )
    if category:
        statement = statement.where(Product.category == category)
    if status:
        statement = statement.where(Product.status == status)
    if low_stock:
        statement = statement.where(col(Product.stock_on_hand) <= col(Product.low_stock_threshold))
    statement = statement.offset(offset).limit(limit).order_by(col(Product.created_at).desc())
    return list(session.exec(statement).all())


def list_low_stock_products(
    session: Session,
    *,
    limit: int = 10,
) -> list[Product]:
    statement = (
        select(Product)
        .where(col(Product.stock_on_hand) <= col(Product.low_stock_threshold))
        .order_by(col(Product.stock_on_hand), col(Product.created_at).desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())
