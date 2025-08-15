import hashlib
import sys

# Fix for ReportLab md5 issue on Python 3.12 Windows
if sys.version_info >= (3, 7):
    orig_md5 = hashlib.md5

    def md5_patch(*args, **kwargs):
        if 'usedforsecurity' in kwargs:
            kwargs.pop('usedforsecurity')
        return orig_md5(*args, **kwargs)

    hashlib.md5 = md5_patch

from fastapi import FastAPI, UploadFile, Form, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
import sqlite3
import os
from datetime import datetime
import re
import requests
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A6
from reportlab.lib.utils import simpleSplit
import qrcode
from io import BytesIO
from PIL import Image
from reportlab.lib.units import mm
import textwrap
from typing import List

app = FastAPI()

# Session secret
SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "dev-secret-change-me")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")

# Allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your frontend's URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Ensure uploads folder exists
UPLOAD_FOLDER = "uploads"
LABEL_FOLDER = "labels"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LABEL_FOLDER, exist_ok=True)

# -------------------------------------------
# DB init + migration
# -------------------------------------------
DB_PATH = "orders.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            phone TEXT,
            name TEXT,
            addressLine1 TEXT,
            addressLine2 TEXT,
            landmark TEXT,
            pincode TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            quantity INTEGER,
            paymentProof TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    # Add "status" column (pending/shipped/cancelled) if missing
    cursor.execute("PRAGMA table_info(orders)")
    cols = [row[1] for row in cursor.fetchall()]
    if "status" not in cols:
        cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'pending'")
        conn.commit()

    # Helpful indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    conn.commit()
    conn.close()

init_db()

# Validation helper
def validate_order_data(email, phone, name, addressLine1, pincode, city, state, quantity, paymentProof):
    print("Validating email")
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    print("Validating phone number")
    if not re.match(r"^\d{10}$", phone):
        raise HTTPException(status_code=400, detail="Phone must be exactly 10 digits")

    print("Validating name")
    if not re.match(r"^[A-Za-z\s]{2,50}$", name):
        raise HTTPException(status_code=400, detail="Name should be 2-50 letters only")

    print("Validating addressline1")
    if len(addressLine1.strip()) < 5:
        raise HTTPException(status_code=400, detail="Address must be at least 5 characters")

    print("Validating pincode")
    if not re.match(r"^[1-9][0-9]{5}$", pincode):
        raise HTTPException(status_code=400, detail="Invalid pincode format")

    print("Validating city and state")
    if not city.strip():
        raise HTTPException(status_code=400, detail="City cannot be blank")
    if not state.strip():
        raise HTTPException(status_code=400, detail="State cannot be blank")

    if not (1 <= quantity <= 999):
        raise HTTPException(status_code=400, detail="Quantity must be between 1 and 999")

    if not paymentProof:
        raise HTTPException(status_code=400, detail="Payment proof is required")
    if paymentProof.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Payment proof must be under 5MB")


@app.post("/orders")
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
    # Run validations
    print("Running validations")
    validate_order_data(email, phone, name, addressLine1, pincode, city, state, quantity, paymentProof)
    print("Validations completed")

    # Check if this phone or email already exists in DB
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM orders WHERE status='pending' AND (email=? OR phone=?) LIMIT 1",
        (email, phone)
    )
    existing_order = cursor.fetchone()
    if existing_order:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Your order is already submitted. We do not accept multiple orders."
        )

    # Save file
    payment_proof_path = None
    if paymentProof:
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{paymentProof.filename}"
        payment_proof_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(payment_proof_path, "wb") as buffer:
            buffer.write(await paymentProof.read())

    # Store in DB
    cursor.execute("""
        INSERT INTO orders (
            email, phone, name, addressLine1, addressLine2, landmark,
            pincode, city, state, country, quantity, paymentProof, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email, phone, name, addressLine1, addressLine2, landmark,
        pincode, city, state, country, quantity, payment_proof_path,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

    return {"message": "Order received successfully"}

# ---------- Label Generation ----------
FROM_BLOCK = [
    "From :",
    "Mayank Lalwani,",
    "Scheme 103, Indore,",
    "Mobile: +91-7045494748,",
    "Indore, Madhya Pradesh - 452001",
]

def draw_wrapped_text(c, text, x, y, max_width, font_name="Helvetica", font_size=11, leading=14):
    """
    Draws text with word wrapping starting at (x,y); y decreases downward.
    """
    c.setFont(font_name, font_size)
    lines = simpleSplit(text, font_name, font_size, max_width)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * leading, line)
    return y - (len(lines) * leading)

def draw_label_page(c, order):
    # Page size A6: 105mm × 148mm, origin bottom-left
    width, height = A6
    margin = 8 * mm
    x_left = margin
    y_top  = height - margin

    # "To," block at TOP-LEFT
    y = y_top
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_left, y, "To,")
    y -= 14

    # Recipient details (wrapped)
    maxw = width - 2 * margin
    c.setFont("Helvetica", 11)

    name_line = (order["name"] or "").strip()
    y = draw_wrapped_text(c, name_line, x_left, y, maxw)

    addr_parts = [
        (order["addressLine1"] or "").strip(),
        (order["addressLine2"] or "").strip(),
        (order["landmark"] or "").strip(),
    ]
    addr_text = ", ".join([p for p in addr_parts if p])
    city_state_pin = ", ".join([v for v in [order["city"], order["state"]] if v])
    if order["pincode"]:
        city_state_pin = f"{city_state_pin} - {order['pincode']}" if city_state_pin else order["pincode"]

    if addr_text:
        y = draw_wrapped_text(c, addr_text, x_left, y, maxw)
    if city_state_pin:
        y = draw_wrapped_text(c, city_state_pin, x_left, y, maxw)

    # FROM block at BOTTOM-LEFT
    y_bottom = margin + (len(FROM_BLOCK) * 12)  # rough height
    # draw from at true bottom-left, rising upward
    y_from = margin + (len(FROM_BLOCK) - 1) * 12
    c.setFont("Helvetica", 10)
    for line in FROM_BLOCK:
        # c.drawString(x_left, margin + y_from)
        c.drawString(x_left, margin + y_from, line)
        y_from -= 12

@app.get("/orders")
def get_orders():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return {"orders": rows}
def generate_label_pdf(order):
    file_path = os.path.join(LABEL_FOLDER, f"label_{order['id']}.pdf")
    c = canvas.Canvas(file_path, pagesize=A6)
    draw_label_page(c, order)
    c.showPage()
    c.save()
    return file_path

# Helper: generate PDF label for an order
# def generate_label_pdf(order):
#     file_path = os.path.join(LABEL_FOLDER, f"label_{order['id']}.pdf")
#     c = canvas.Canvas(file_path, pagesize=A6)
#     width, height = A6  # width and height in points
#     c.setFont("Helvetica-Bold", 12)
#     x_start = 10
#     y_start = height - 20  # Start near top
#     line_height = 14

#     # "To," instead of Order ID
#     c.drawString(x_start, y_start, "To,")
#     y_start -= line_height

#     # Name
#     c.setFont("Helvetica", 12)
#     c.drawString(x_start, y_start, order['name'])
#     y_start -= line_height

#     # Phone
#     c.drawString(x_start, y_start, f"Phone: {order['phone']}")
#     y_start -= line_height

#     # Address with word wrap
#     full_address = f"{order['addressLine1']} {order.get('addressLine2','')} {order.get('landmark','')}, {order['city']}, {order['state']} - {order['pincode']}"
#     wrapped_address = textwrap.wrap(full_address, width=35)  # Adjust width as needed
#     for line in wrapped_address:
#         c.drawString(x_start, y_start, line)
#         y_start -= line_height

#     # Draw order details
#     # c.drawString(20, 150, f"Order ID: {order['id']}")
#     # c.drawString(20, 135, f"Name: {order['name']}")
#     # c.drawString(20, 120, f"Phone: {order['phone']}")
#     # c.drawString(20, 105, f"Address: {order['addressLine1']} {order['addressLine2']}")
#     # c.drawString(20, 90, f"Landmark: {order['landmark']}")
#     # c.drawString(20, 75, f"City: {order['city']}, {order['state']}")
#     # c.drawString(20, 60, f"Pincode: {order['pincode']}")
#     # c.drawString(20, 45, f"Quantity: {order['quantity']}")

#     # Bottom-left fixed text
#     bottom_text = """From :
#     Mayank Lalwani,
#     Scheme 103, Indore,
#     Mobile: +91-7045494748,
#     Indore, Madhya Pradesh - 452001"""
    
#     c.setFont("Helvetica", 10)
#     for idx, line in enumerate(bottom_text.split('\n')):
#         c.drawString(x_start, 20 + (len(bottom_text.split('\n')) - idx - 1) * line_height, line)

#     c.save()

#     # Optional: generate QR code with order ID
#     # qr = qrcode.QRCode(box_size=2, border=1)
#     # qr.add_data(f"OrderID:{order['id']}")
#     # qr.make(fit=True)
#     # img = qr.make_image(fill_color="black", back_color="white")
#     # # Convert to RGB for ReportLab
#     # img = img.convert("RGB")
#     # # qr_buffer = BytesIO()
#     # # img.save(qr_buffer, format="PNG")
#     # # qr_buffer.seek(0)
#     # # Wrap with ImageReader
#     # qr_image = ImageReader(img)
#     # c.drawImage(qr_image, 150, 60, width=50, height=50)
#     # # c.drawImage(qr_buffer, 150, 60, width=50, height=50)

#     # c.save()
#     return file_path

def generate_bulk_labels(order_ids):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(LABEL_FOLDER, f"labels_bulk_{ts}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=A6)
    conn = get_conn()
    cur = conn.cursor()
    for oid in order_ids:
        cur.execute("SELECT * FROM orders WHERE id=?", (oid,))
        row = cur.fetchone()
        if not row:
            continue
        draw_label_page(c, row)
        c.showPage()
    conn.close()
    c.save()
    return pdf_path

# Endpoint to generate and download label for a single order
@app.get("/orders/{order_id}/label")
def get_order_label(order_id: int):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order_row  = cursor.fetchone()
    conn.close()

    if not order_row :
        raise HTTPException(status_code=404, detail="Order not found")

    # Convert Row to dict
    order = dict(order_row)

    # Generate PDF
    label_path = generate_label_pdf(order)
    return FileResponse(label_path, media_type="application/pdf", filename=f"label_{order_id}.pdf")

# ============================================================
#                    ADMIN DASHBOARD
# ============================================================

# Admin credentials (use env in prod)
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
SESSION_COOKIE = "admin_session"

def is_logged_in(request: Request) -> bool:
    return request.cookies.get(SESSION_COOKIE) == "1"

def require_admin(request: Request):
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

def require_admin(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---- Login pages ----
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})

@app.post("/admin/login")
async def admin_login(request: Request):
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "").strip()
    if username == ADMIN_USER and password == ADMIN_PASS:
        request.session["admin"] = True
        resp = RedirectResponse(url="/admin/orders", status_code=303)
        # simplest possible session flag
        resp.set_cookie(SESSION_COOKIE, "1", httponly=True, samesite="lax")
        return resp
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Invalid credentials"}, status_code=401)

@app.get("/admin/logout")
def admin_logout(request: Request):
    resp = RedirectResponse(url="/admin/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp

# ---- Dashboard page ----
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse(url="/admin/login", status_code=302)
    # return templates.TemplateResponse("admin_orders.html", {"request": request})
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='pending'")
    pending_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='shipped'")
    shipped_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='cancelled'")
    cancelled_count = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM orders WHERE status='pending'")
    orders = cursor.fetchall()

    conn.close()

    counts = {
        "pending": pending_count,
        "shipped": shipped_count,
        "cancelled": cancelled_count
    }

    return templates.TemplateResponse(
        "admin_orders.html",
        {
            "request": request,
            "counts": counts,
            "orders": orders
        }
    )

# ---- Data API for the dashboard table ----
@app.get("/admin/orders")
def admin_list_orders(
    request: Request,
    status: str = "pending",
    q: str = "",
    page: int = 1,
    page_size: int = 20
):
    require_admin(request)

    offset = max(0, (page - 1) * page_size)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    base = "SELECT * FROM orders"
    where = []
    params = []

    if status:
        where.append("status = ?")
        params.append(status)

    if q:
        where.append("(phone LIKE ? OR email LIKE ? OR name LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where_clause = (" WHERE " + " AND ".join(where)) if where else ""
    order_clause = " ORDER BY id DESC"
    limit_clause = " LIMIT ? OFFSET ?"
    params.extend([page_size, offset])

    cursor.execute(base + where_clause + order_clause + limit_clause, params)
    rows = cursor.fetchall()

    # Count total for pagination
    count_sql = "SELECT COUNT(*) FROM orders" + where_clause
    cursor.execute(count_sql, params[:-2])  # exclude limit/offset
    total = cursor.fetchone()[0]

    conn.close()

    return templates.TemplateResponse(
        "admin_orders_filtered.html",
        {
            "request": request,
            "orders": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "status": status,
            "q": q
        }
    )

def get_status_counts():
    conn = get_conn()
    cur = conn.cursor()
    res = {}
    for st in ("pending", "shipped", "cancelled"):
        cur.execute("SELECT COUNT(*) AS c FROM orders WHERE status=?", (st,))
        res[st] = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM orders")
    res["all"] = cur.fetchone()["c"]
    conn.close()
    return res

# ---- Update status ----
@app.post("/admin/orders/{order_id}/status")
def admin_update_status(order_id: int, request: Request, status: str = Form(...)):
    require_admin(request)

    if status not in ("pending", "shipped", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()

    return {"ok": True}

# Optional: quick health ping
@app.get("/admin/ping")
def admin_ping():
    return {"ok": True}

@app.post("/admin/orders/bulk-action")
async def admin_bulk_action(
    request: Request,
    action: str = Form(...),
    order_ids: List[int] = Form(default=[]),
):
    if not is_logged_in(request):
        return RedirectResponse(url="/admin/login", status_code=303)

    if not order_ids:
        return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

    conn = get_conn()
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in order_ids)

    if action == "mark_shipped":
        cur.execute(f"UPDATE orders SET status='shipped' WHERE id IN ({placeholders})", order_ids)
        conn.commit()
        conn.close()
        return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

    elif action == "cancel":
        cur.execute(f"UPDATE orders SET status='cancelled' WHERE id IN ({placeholders})", order_ids)
        conn.commit()
        conn.close()
        return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

    elif action == "generate_labels":
        conn.close()
        pdf_path = generate_bulk_labels(order_ids)
        return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))

    conn.close()
    return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

@app.post("/admin/orders/{order_id}/cancel")
def admin_cancel_single(request: Request, order_id: int):
    if not is_logged_in(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

@app.get("/admin/orders/{order_id}/label")
def admin_single_label(request: Request, order_id: int):
    if not is_logged_in(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return get_order_label(order_id)