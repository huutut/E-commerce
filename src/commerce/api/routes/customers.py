from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from commerce.api.deps import SessionDep, api_key_dep
from commerce.domain.models import Customer
from commerce.domain.schemas import CustomerCreate, CustomerRead

router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(api_key_dep)])


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, session: SessionDep) -> Customer:
    customer = Customer(email=payload.email, full_name=payload.full_name)
    session.add(customer)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Customer email already exists.") from exc
    session.refresh(customer)
    return customer
