from fastapi import APIRouter, Form, UploadFile, HTTPException
from datetime import datetime
import psycopg2.extras

from app.database import get_conn
from app.validation import validate_order_data
from app.config import supabase, BUCKET

router = APIRouter()

@router.post("/orders")
async def create_order(
    email: str = Form(...),
    phone: str = Form(...),
    name: str = Form(...),
    addressLine1: str = Form(...),
    addressLine2: str = Form(""),
    landmark: str = Form(""),
    pincode: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    country: str = Form("India"),
    quantity: int = Form(...),
    paymentProof: UploadFile = None
):
    validate_order_data(email, phone, name, addressLine1, pincode, city, state, quantity, paymentProof)

    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        "SELECT id FROM orders WHERE status='pending' AND (email=%s OR phone=%s) LIMIT 1",
        (email, phone)
    )
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Duplicate order")

    cursor.execute("""
        INSERT INTO orders (
            email, phone, name, addressLine1, addressLine2, landmark,
            pincode, city, state, country, quantity, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        email, phone, name, addressLine1, addressLine2, landmark,
        pincode, city, state, country, quantity,
        datetime.now()
    ))
    order_id = cursor.fetchone()["id"]
    conn.commit()

    payment_proof_url = None
    if paymentProof:
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{paymentProof.filename}"
        file_bytes = await paymentProof.read()
        supabase_path = f"uploads/{order_id}/{filename}"

        supabase.storage.from_(BUCKET).upload(
            path=supabase_path,
            file=file_bytes,
            file_options={"content-type": paymentProof.content_type}
        )
        payment_proof_url = supabase.storage.from_(BUCKET).get_public_url(supabase_path)

        cursor.execute("UPDATE orders SET paymentProof=%s WHERE id=%s", (payment_proof_url, order_id))
        conn.commit()

    conn.close()
    return {"message": "Order received", "order_id": order_id, "paymentProof": payment_proof_url}
