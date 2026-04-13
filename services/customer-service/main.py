import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability import create_app, get_logger
from database import get_db, init_db
from models import Customer

log = get_logger()


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("customer-service started")
    yield

app = create_app("Customer Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None


class CustomerResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    address: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(req: CustomerCreate, db: Session = Depends(get_db)):
    existing = db.query(Customer).filter(Customer.email == req.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")

    customer = Customer(**req.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    log.info("customer created", customer_id=customer.id, email=customer.email)
    return _to_response(customer)


@app.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _to_response(customer)


@app.get("/customers", response_model=list[CustomerResponse])
async def list_customers(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    customers = db.query(Customer).offset(skip).limit(limit).all()
    return [_to_response(c) for c in customers]


@app.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: str, req: CustomerCreate, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    log.info("customer updated", customer_id=customer_id)
    return _to_response(customer)


def _to_response(c: Customer) -> dict:
    return {
        "id": c.id,
        "first_name": c.first_name,
        "last_name": c.last_name,
        "email": c.email,
        "phone": c.phone,
        "address": c.address,
        "created_at": c.created_at.isoformat(),
    }
