from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Order
from app.labels import ORDER_LABELS

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("/orders", response_class=HTMLResponse)
def get_admin_orders(request: Request, db: Session = Depends(get_db)):
    # Query order counts
    pending_count = db.query(Order).filter(Order.status == "pending").count()
    shipped_count = db.query(Order).filter(Order.status == "shipped").count()
    cancelled_count = db.query(Order).filter(Order.status == "cancelled").count()
    all_count = db.query(Order).count()

    # Query quantity counts
    total_quantities = (
        db.query(Order.product_name, db.func.sum(Order.quantity))
        .group_by(Order.product_name)
        .all()
    )

    stats = {
        "orders": {
            "pending": pending_count,
            "shipped": shipped_count,
            "cancelled": cancelled_count,
            "all": all_count,
        },
        "quantities": dict(total_quantities),
    }

    return templates.TemplateResponse(
        "admin_orders.html",
        {"request": request, "stats": stats, "labels": ORDER_LABELS},
    )
