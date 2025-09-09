import hashlib
import sys
import psycopg2
import psycopg2.extras
from supabase import create_client, Client
from math import floor
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
import socket

BUCKET = "divinerayysdiwali2025"

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

# Set your Supabase credentials
SUPABASE_URL = "https://zjgzqudobxmqgulyhgft.supabase.co"   # Replace with your project URL
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqZ3pxdWRvYnhtcWd1bHloZ2Z0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTM1NzY5NSwiZXhwIjoyMDcwOTMzNjk1fQ.CLfTneOENRa0ccIxz3Na1VqLbREdmj5X7ieaWj3OFWw"          # Replace with your API key

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
# Fetch variables
USER = os.getenv("user", "postgres")
PASSWORD = os.getenv("password", "DivineRayys@2025")
HOST = os.getenv("host", "db.zjgzqudobxmqgulyhgft.supabase.co")
PORT = os.getenv("port", "5432")
DBNAME = os.getenv("dbname", "postgres")

# def get_conn():
#     # conn = sqlite3.connect(DB_PATH)
#     # conn.row_factory = sqlite3.Row
#     conn = psycopg2.connect(
#         user=USER,
#         password=PASSWORD,
#         host=HOST,
#         port=PORT,
#         dbname=DBNAME
#     )
#     return conn

def get_conn():
    """
    Try to connect using DATABASE_URL (if present). If that fails or resolves
    only to IPv6, try an IPv4-resolved host literal (works around IPv6 routing).
    Ensures sslmode=require for Supabase.
    """
    database_url = os.getenv("DATABASE_URL")  # if you set this in Render, good
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

    # helper to ensure sslmode in URL
    def ensure_ssl(url):
        if "sslmode=" not in url:
            return url + ("&" if "?" in url else "?") + "sslmode=require"
        return url

    # If DATABASE_URL present, try normal connect first
    if database_url:
        database_url = ensure_ssl(database_url)
        try:
            return psycopg2.connect(database_url, connect_timeout=connect_timeout)
        except Exception:
            # fall through to IPv4 fallback below
            pass

    # Build URL from individual env vars if DATABASE_URL not set
    user = os.getenv("DB_USER") or os.getenv("user")
    password = os.getenv("DB_PASS") or os.getenv("password")
    host = os.getenv("DB_HOST") or os.getenv("host")
    port = os.getenv("DB_PORT") or os.getenv("port") or "5432"
    dbname = os.getenv("DB_NAME") or os.getenv("dbname")

    if not all([user, password, host, dbname]):
        raise RuntimeError("Database config missing. Set DATABASE_URL or DB_USER/DB_PASS/DB_HOST/DB_NAME in env.")

    base_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    url_with_ssl = ensure_ssl(base_url)

    # First try normal connect (may resolve to IPv6 which fails)
    try:
        return psycopg2.connect(url_with_ssl, connect_timeout=connect_timeout)
    except Exception as first_exc:
        # Try IPv4 resolution fallback
        try:
            infos = socket.getaddrinfo(host, int(port), family=socket.AF_INET, type=socket.SOCK_STREAM)
            if not infos:
                raise RuntimeError("No IPv4 address found for host")
            ipv4 = infos[0][4][0]
            # connect to IPv4 literal
            conn = psycopg2.connect(
                user=user,
                password=password,
                host=ipv4,
                port=port,
                dbname=dbname,
                connect_timeout=connect_timeout,
                sslmode="require"
            )
            return conn
        except Exception as ipv4_exc:
            # raise a combined informative error
            raise RuntimeError(
                "Failed to connect to Postgres. Tried normal connect and IPv4 fallback.\n"
                f"Normal error: {first_exc}\nIPv4 fallback error: {ipv4_exc}\n\n"
                "If IPv4 fallback fails, either the host has no A record, or outbound IPv4 is blocked. "
                "Consider using the Supabase HTTP client instead (no port 5432) or check platform networking."
            ) from ipv4_exc


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
    # conn = sqlite3.connect("orders.db")
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(
        "SELECT id FROM orders WHERE status='pending' AND (email=%s OR phone=%s) LIMIT 1",
        (email, phone)
    )
    existing_order = cursor.fetchone()
    if existing_order:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Your order is already submitted. We do not accept multiple orders."
        )

    # Store in DB
    # insert_query = """
    #     INSERT INTO orders (
    #         email, phone, name, addressLine1, addressLine2, landmark,
    #         pincode, city, state, country, quantity, created_at
    #     ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    #     RETURNING id
    # """, (
    #     email, phone, name, addressLine1, addressLine2, landmark,
    #     pincode, city, state, country, quantity, 
    #     datetime.now().isoformat()
    # )
    cursor.execute("""
        INSERT INTO orders (
            email, phone, name, addressLine1, addressLine2, landmark,
            pincode, city, state, country, quantity, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        email, phone, name, addressLine1, addressLine2, landmark,
        pincode, city, state, country, quantity, 
        datetime.now().isoformat()
    ))
    # print(f" Insert query = {insert_query}")
    order_id = cursor.fetchone()["id"]
    conn.commit()

    # Save file
    # payment_proof_path = None
    # if paymentProof:
    #     filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{paymentProof.filename}"
    #     payment_proof_path = os.path.join(UPLOAD_FOLDER, filename)
    #     with open(payment_proof_path, "wb") as buffer:
    #         buffer.write(await paymentProof.read())
    payment_proof_url = None
    if paymentProof:
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{paymentProof.filename}"
        file_bytes = await paymentProof.read()

        # Upload to Supabase bucket
        supabase_path = f"uploads/{order_id}/{filename}"
        try:
            supabase.storage.from_(BUCKET).upload(
                path=supabase_path,
                file=file_bytes,
                file_options={"content-type": paymentProof.content_type}
            )
            # Public URL (if bucket is public)
            payment_proof_url = supabase.storage.from_(BUCKET).get_public_url(supabase_path)
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=500, detail=f"Failed to upload payment proof: {e}")

        # Update row with paymentProof path
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("UPDATE orders SET paymentProof=%s WHERE id=%s", (payment_proof_url, order_id))
        conn.commit()

    return {"message": "Order received successfully", "order_id": order_id, "paymentProof": payment_proof_url}

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
        (order["addressline1"] or "").strip(),
        (order["addressline2"] or "").strip(),
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

# def draw_label_block(c, order, x_left, y_top, slot_width, slot_height):
#     """
#     Draw a single label inside the rectangle defined by:
#       - top-left corner (x_left, y_top)
#       - slot_width (width of the label area)
#       - slot_height (height of the label area)
#     Coordinates: origin is bottom-left; y_top is measured from bottom.
#     We draw top-down starting at y_top.
#     """
#     # Keep font sizes consistent with your single-label version
#     leading = 12
#     name_font = ("Helvetica-Bold", 12)
#     body_font = ("Helvetica", 11)

#     # start drawing from y_top downward (ReportLab coordinates bottom-left)
#     y = y_top

#     # "To," heading
#     c.setFont(name_font[0], name_font[1])
#     # place "To," a little inset from left
#     inset = 4 * mm
#     c.drawString(x_left + inset, y, "To,")
#     y -= leading

#     # Recipient name
#     c.setFont(body_font[0], body_font[1])
#     name_line = (order.get("name") or "").strip()
#     # Draw name with wrapping inside the slot width minus inset
#     maxw = slot_width - (2 * inset)
#     y = draw_wrapped_text_slot(c, name_line, x_left + inset, y, maxw, font_name=body_font[0], font_size=body_font[1], leading=leading)

#     # Address parts
#     addr_parts = [
#         (order.get("addressline1") or "").strip(),
#         (order.get("addressline2") or "").strip(),
#         (order.get("landmark") or "").strip(),
#     ]
#     addr_text = ", ".join([p for p in addr_parts if p])
#     city_state_pin = ", ".join([v for v in [order.get("city"), order.get("state")] if v])
#     if order.get("pincode"):
#         city_state_pin = f"{city_state_pin} - {order.get('pincode')}" if city_state_pin else order.get("pincode")

#     if addr_text:
#         y = draw_wrapped_text_slot(c, addr_text, x_left + inset, y, maxw, font_name=body_font[0], font_size=body_font[1], leading=leading)
#     if city_state_pin:
#         y = draw_wrapped_text_slot(c, city_state_pin, x_left + inset, y, maxw, font_name=body_font[0], font_size=body_font[1], leading=leading)

#     # FROM block at the bottom of the slot (align to slot bottom + inset)
#     # We will draw the FROM block starting from slot bottom + small inset, upwards
#     from_block = FROM_BLOCK  # reuse your constant
#     c.setFont("Helvetica", 10)
#     bottom_y = (y_top - slot_height) + (1.5 * mm) + (len(from_block) * 12)  # compute a baseline to draw upwards
#     # We'll draw lines at increasing y from slot bottom + inset
#     cur_y = (y_top - slot_height) + (4 * mm) + (len(from_block)-1) * 12
#     for line in from_block:
#         c.drawString(x_left + inset, cur_y, line)
#         cur_y -= 12

# def draw_label_block(c, order, x_left, y_top, slot_width, slot_height):
#     """
#     Draw a single label inside the rectangle defined by:
#       - top-left corner (x_left, y_top)
#       - slot_width (width of the label area)
#       - slot_height (height of the label area)
#     Ensures the FROM block occupies reserved bottom space and body text won't overlap it.
#     """
#     leading = 12
#     name_font = ("Helvetica-Bold", 12)
#     body_font = ("Helvetica", 11)
#     inset = 4 * mm
#     gap_between_body_and_from = 3 * mm

#     # compute FROM block height (approx)
#     from_lines = FROM_BLOCK  # list of strings
#     from_line_height = 12  # same as earlier; adjust if desired
#     from_height = len(from_lines) * from_line_height

#     # Reserve bottom area for FROM block (inset + from_height + small gap)
#     reserved_bottom = inset + from_height + gap_between_body_and_from

#     # compute minimum Y the body may go down to
#     slot_bottom_y = (y_top - slot_height)
#     min_allowed_y_for_body = slot_bottom_y + reserved_bottom

#     # Start drawing header & body from y_top downward
#     y = y_top

#     # "To," heading
#     c.setFont(name_font[0], name_font[1])
#     c.drawString(x_left + inset, y, "To,")
#     y -= leading

#     # Recipient name
#     c.setFont(body_font[0], body_font[1])
#     name_line = (order.get("name") or "").strip()
#     maxw = slot_width - (2 * inset)
#     y = draw_wrapped_text_slot(
#         c, name_line, x_left + inset, y,
#         maxw, min_allowed_y_for_body,
#         font_name=body_font[0], font_size=body_font[1], leading=leading
#     )

#     # Address parts
#     addr_parts = [
#         (order.get("addressline1") or "").strip(),
#         (order.get("addressline2") or "").strip(),
#         (order.get("landmark") or "").strip(),
#     ]
#     addr_text = ", ".join([p for p in addr_parts if p])
#     if addr_text:
#         y = draw_wrapped_text_slot(
#             c, addr_text, x_left + inset, y,
#             maxw, min_allowed_y_for_body,
#             font_name=body_font[0], font_size=body_font[1], leading=leading
#         )

#     # City/State + pincode
#     city_state_pin = ", ".join([v for v in [order.get("city"), order.get("state")] if v])
#     if order.get("pincode"):
#         city_state_pin = f"{city_state_pin} - {order.get('pincode')}" if city_state_pin else order.get("pincode")

#     if city_state_pin:
#         y = draw_wrapped_text_slot(
#             c, city_state_pin, x_left + inset, y,
#             maxw, min_allowed_y_for_body,
#             font_name=body_font[0], font_size=body_font[1], leading=leading
#         )

#     # Draw FROM block strictly inside reserved bottom area.
#     # We'll draw FROM lines starting from slot bottom + inset and going upwards.
#     # compute starting y for FROM drawing (topmost line y coordinate)
#     # slot_bottom_y + inset is the baseline for the FIRST from line (bottom-most),
#     # but we want to draw lines from top to bottom inside that reserved area.
#     # So set start_y = slot_bottom_y + inset + (from_height - from_line_height)
#     start_y = slot_bottom_y + inset + (from_height - from_line_height)

#     c.setFont("Helvetica", 10)
#     for i, line in enumerate(from_lines):
#         # draw each line moving downward
#         line_y = start_y - i * from_line_height
#         # ensure this y is inside the slot (safety)
#         if line_y < slot_bottom_y + inset - 1:
#             # if somehow it would go outside, skip (safety)
#             continue
#         c.drawString(x_left + inset, line_y, line)

def draw_label_block(c, order, x_left, y_top, slot_width, slot_height):
    """
    Draw a single label in the slot rectangle (x_left, y_top) with slot_width x slot_height.
    Ensures FROM block is wrapped to slot_width and body text doesn't overlap it.
    """
    # visual metrics
    leading = 12
    name_font = ("Helvetica-Bold", 12)
    body_font = ("Helvetica", 11)
    inset = 4 * mm
    gap_between_body_and_from = 3 * mm
    from_font = ("Helvetica", 10)
    from_line_height = 12  # vertical spacing for FROM lines

    # Prepare FROM block wrapped to slot width
    maxw = slot_width - 2 * inset
    raw_from_lines = FROM_BLOCK if isinstance(FROM_BLOCK, (list, tuple)) else [FROM_BLOCK]
    wrapped_from_lines = []
    for raw in raw_from_lines:
        if not raw:
            continue
        # simpleSplit returns wrapped lines for the available width
        wrapped = simpleSplit(raw, from_font[0], from_font[1], maxw)
        if wrapped:
            wrapped_from_lines.extend(wrapped)
        else:
            wrapped_from_lines.append(raw)

    from_height = len(wrapped_from_lines) * from_line_height

    # Reserve bottom area for FROM block + inset + small gap
    reserved_bottom = inset + from_height + gap_between_body_and_from

    # Compute boundaries
    slot_bottom_y = y_top - slot_height
    min_allowed_y_for_body = slot_bottom_y + reserved_bottom

    # Start drawing from top
    y = y_top

    # "To," heading
    c.setFont(name_font[0], name_font[1])
    c.drawString(x_left + inset, y, "To,")
    y -= leading

    # Recipient name
    c.setFont(body_font[0], body_font[1])
    name_line = (order.get("name") or "").strip()
    y = draw_wrapped_text_slot(
        c, name_line, x_left + inset, y,
        maxw, min_allowed_y_for_body,
        font_name=body_font[0], font_size=body_font[1], leading=leading
    )

    # Address fields (joined)
    addr_parts = [
        (order.get("addressline1") or "").strip(),
        (order.get("addressline2") or "").strip(),
        (order.get("landmark") or "").strip(),
    ]
    addr_text = ", ".join([p for p in addr_parts if p])
    if addr_text:
        y = draw_wrapped_text_slot(
            c, addr_text, x_left + inset, y,
            maxw, min_allowed_y_for_body,
            font_name=body_font[0], font_size=body_font[1], leading=leading
        )

    # city/state/pincode
    city_state_pin = ", ".join([v for v in [order.get("city"), order.get("state")] if v])
    if order.get("pincode"):
        city_state_pin = f"{city_state_pin} - {order.get('pincode')}" if city_state_pin else order.get("pincode")

    if city_state_pin:
        y = draw_wrapped_text_slot(
            c, city_state_pin, x_left + inset, y,
            maxw, min_allowed_y_for_body,
            font_name=body_font[0], font_size=body_font[1], leading=leading
        )

    # Now draw the FROM block inside the reserved bottom area.
    # We'll draw from top-to-bottom inside that reserved area.
    c.setFont(from_font[0], from_font[1])

    # compute starting y for first FROM line (topmost of FROM block)
    # topmost_from_y = slot_bottom_y + reserved_bottom - (inset) - (from_line_height - (from_line_height))
    # simpler: position first wrapped_from_lines[0] at slot_bottom_y + reserved_bottom - (from_line_height)
    topmost_from_y = slot_bottom_y + inset + from_height - from_line_height
    # Draw each wrapped FROM line in order
    for i, line in enumerate(wrapped_from_lines):
        line_y = topmost_from_y - i * from_line_height
        # safety clamp: do not draw below slot bottom + inset
        if line_y < slot_bottom_y + inset - 1:
            continue
        c.drawString(x_left + inset, line_y, line)

# def draw_wrapped_text_slot(c, text, x, y, max_width, font_name="Helvetica", font_size=11, leading=14):
#     """
#     Like draw_wrapped_text but constrained to a slot; returns new y position AFTER drawing.
#     Uses reportlab.lib.utils.simpleSplit like earlier helper.
#     """
#     c.setFont(font_name, font_size)
#     lines = simpleSplit(text, font_name, font_size, max_width)
#     for i, line in enumerate(lines):
#         c.drawString(x, y - i * leading, line)
#     return y - (len(lines) * leading)

# def draw_wrapped_text_slot(c, text, x, y, max_width, min_y, font_name="Helvetica", font_size=11, leading=14):
#     """
#     Draw wrapped text starting at y and NOT going below min_y.
#     If text lines exceed available space, truncate and append '...'.
#     Returns new y after drawing.
#     - c: canvas
#     - text: string
#     - x: left x coordinate
#     - y: start y (top)
#     - max_width: maximum width for wrapping
#     - min_y: minimum allowed y (bottom boundary inside slot)
#     """
#     c.setFont(font_name, font_size)
#     lines = simpleSplit(text, font_name, font_size, max_width)

#     # compute how many lines fit between y and min_y
#     available_height = y - min_y
#     if available_height <= 0:
#         # no room
#         return min_y

#     max_lines = max(0, floor(available_height / leading))

#     if len(lines) == 0:
#         return y

#     if len(lines) > max_lines:
#         # truncate and add ellipsis to last allowed line (try to fit)
#         allowed = lines[:max_lines]
#         if allowed:
#             last = allowed[-1]
#             # try to trim last line to append '...'
#             # simple approach: trim characters until it fits with "..."
#             ell = "..."
#             while simpleSplit(last + ell, font_name, font_size, max_width) and simpleSplit(last + ell, font_name, font_size, max_width)[-1] != (last + ell):
#                 # break if something odd (safety)
#                 break
#             allowed[-1] = (allowed[-1].rstrip() + ell)
#         lines_to_draw = allowed
#     else:
#         lines_to_draw = lines

#     for i, line in enumerate(lines_to_draw):
#         c.drawString(x, y - i * leading, line)

#     return y - (len(lines_to_draw) * leading)

def draw_wrapped_text_slot(c, text, x, y, max_width, min_y, font_name="Helvetica", font_size=11, leading=14):
    """
    Draw wrapped text starting at y and NOT going below min_y.
    If text lines exceed available space, truncate and append '...'.
    Returns new y after drawing.
    """
    if not text:
        return y
    c.setFont(font_name, font_size)
    lines = simpleSplit(text, font_name, font_size, max_width)

    available_height = y - min_y
    if available_height <= 0:
        return min_y

    max_lines = max(0, floor(available_height / leading))

    if len(lines) == 0:
        return y

    if len(lines) > max_lines and max_lines > 0:
        # keep lines up to max_lines, add ellipsis to last line
        allowed = lines[:max_lines]
        last = allowed[-1]
        ell = "..."
        # Try to trim last so ellipsis fits. We'll simply append ellipses; ReportLab will clip visually if still too long.
        allowed[-1] = (last.rstrip() + ell)
        lines_to_draw = allowed
    else:
        lines_to_draw = lines[:max_lines] if max_lines > 0 else []

    for i, line in enumerate(lines_to_draw):
        c.drawString(x, y - i * leading, line)

    return y - (len(lines_to_draw) * leading)




@app.get("/orders")
def get_orders():
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return {"orders": rows}
# def generate_label_pdf(order):
#     file_path = os.path.join(LABEL_FOLDER, f"label_{order['id']}.pdf")
#     c = canvas.Canvas(file_path, pagesize=A6)
#     draw_label_page(c, order)
#     c.showPage()
#     c.save()
#     return file_path

def generate_label_pdf(order):
    """
    Keep single-label PDF generation for the single-order endpoint unchanged.
    We'll draw one half-width label centered/lefted on the page for consistency.
    """
    file_path = os.path.join(LABEL_FOLDER, f"label_{order['id']}.pdf")
    c = canvas.Canvas(file_path, pagesize=A6)
    width, height = A6
    margin = 8 * mm
    # use half slot width for single label generation for visual parity
    gutter = 4 * mm
    slot_width = (width - 2 * margin - gutter) / 2.0
    slot_height = height - 2 * margin
    # place single label in the left slot (match bulk behaviour)
    x_left = margin
    y_top = height - margin
    draw_label_block(c, order, x_left, y_top, slot_width, slot_height)
    c.showPage()
    c.save()
    return file_path

# def generate_bulk_labels(order_ids):
#     ts = datetime.now().strftime("%Y%m%d_%H%M%S")
#     pdf_path = os.path.join(LABEL_FOLDER, f"labels_bulk_{ts}.pdf")
#     c = canvas.Canvas(pdf_path, pagesize=A6)
#     conn = get_conn()
#     cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
#     for oid in order_ids:
#         cur.execute("SELECT * FROM orders WHERE id=%s", (oid,))
#         row = cur.fetchone()
#         if not row:
#             continue
#         draw_label_page(c, row)
#         c.showPage()
#     conn.close()
#     c.save()
#     return pdf_path

def generate_bulk_labels(order_ids):
    """
    Generates a PDF with two half-width labels per A6 page (left and right).
    If odd number of orders, the final page will contain the last label in the left slot.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(LABEL_FOLDER, f"labels_bulk_{ts}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=A6)
    width, height = A6

    # margins / gutter
    margin = 8 * mm
    gutter = 4 * mm  # space between two half-width labels

    # compute slot sizes
    usable_width = width - 2 * margin - gutter
    slot_width = usable_width / 2.0
    slot_height = height - 2 * margin

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # walk in steps of 2 and place two labels per page
    i = 0
    n = len(order_ids)
    while i < n:
        # New A6 page for every pair
        # left slot (always)
        oid_left = order_ids[i]
        cur.execute("SELECT * FROM orders WHERE id=%s", (oid_left,))
        left_row = cur.fetchone()
        if left_row:
            x_left = margin
            y_top = height - margin
            draw_label_block(c, dict(left_row), x_left, y_top, slot_width, slot_height)

        # right slot (if exists)
        if i + 1 < n:
            oid_right = order_ids[i + 1]
            cur.execute("SELECT * FROM orders WHERE id=%s", (oid_right,))
            right_row = cur.fetchone()
            if right_row:
                x_right = margin + slot_width + gutter
                y_top = height - margin
                draw_label_block(c, dict(right_row), x_right, y_top, slot_width, slot_height)

        # --- add dashed vertical line between slots ---
        divider_x = margin + slot_width + (gutter / 2.0)
        c.setDash(3, 3)  # dash pattern: 3 on, 3 off
        c.line(divider_x, margin, divider_x, height - margin)
        c.setDash()  # reset to solid

        c.showPage()
        i += 2

    conn.close()
    c.save()
    return pdf_path

# Endpoint to generate and download label for a single order
@app.get("/orders/{order_id}/label")
def get_order_label(order_id: int):
    conn = get_conn()
    # conn.row_factory = sqlite3.Row
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
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
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders WHERE status='pending'")
    row = cursor.fetchone()
    pending_count, pending_qty = row["count"], row["qty"]

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders WHERE status='shipped'")
    row = cursor.fetchone()
    shipped_count, shipped_qty = row["count"], row["qty"]

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders WHERE status='cancelled'")
    row = cursor.fetchone()
    cancelled_count, cancelled_qty = row["count"], row["qty"]

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders")
    row = cursor.fetchone()
    total_count, total_qty = row["count"], row["qty"]

    cursor.execute("SELECT * FROM orders WHERE status='pending'")
    orders = cursor.fetchall()

    conn.close()

    counts = {
        "pending": pending_count,
        "shipped": shipped_count,
        "cancelled": cancelled_count,
    }

    stats = {
        "orders": {
            "pending": pending_count,
            "shipped": shipped_count,
            "cancelled": cancelled_count,
            "all": total_count,
        },
        "qty": {
            "pending": pending_qty,
            "shipped": shipped_qty,
            "cancelled": cancelled_qty,
            "all": total_qty,
        }
    }

    return templates.TemplateResponse(
        "admin_orders.html",
        {
            "request": request,
            "stats": stats,
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
    # conn = sqlite3.connect(DB_PATH)
    # conn.row_factory = sqlite3.Row
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    base = "SELECT * FROM orders"
    where = []
    params = []

    if status:
        where.append("status = %s")
        params.append(status)

    if q:
        where.append("(phone LIKE %s OR email LIKE %s OR name LIKE %s)")
        like = f"%{q}%"
        params.extend([like, like, like])

    where_clause = (" WHERE " + " AND ".join(where)) if where else ""
    order_clause = " ORDER BY id DESC"
    limit_clause = " LIMIT %s OFFSET %s"
    params.extend([page_size, offset])

    cursor.execute(base + where_clause + order_clause + limit_clause, params)
    rows = cursor.fetchall()

    # Count total for pagination
    count_sql = "SELECT COUNT(*) as count FROM orders" + where_clause
    cursor.execute(count_sql, params[:-2])  # exclude limit/offset
    total = cursor.fetchone()["count"]

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
        cur.execute("SELECT COUNT(*) AS c FROM orders WHERE status=%s", (st,))
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

    # conn = sqlite3.connect(DB_PATH)
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    placeholders = ",".join("%s" for _ in order_ids)

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
    cur.execute("UPDATE orders SET status='cancelled' WHERE id=%s", (order_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

@app.get("/admin/orders/{order_id}/label")
def admin_single_label(request: Request, order_id: int):
    if not is_logged_in(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return get_order_label(order_id)

@app.get("/admin/orders/{order_id}/screenshot")
async def get_order_screenshot(order_id: str):
    try:
        # list files in /uploads/{order_id}
        files = supabase.storage.from_(BUCKET).list(f"uploads/{order_id}")
        if not files:
            raise HTTPException(status_code=404, detail="Payment screenshot not found")

        # take first image file (you can improve by filtering for png/jpg/pdf etc.)
        file_name = files[0]["name"]
        file_path = f"uploads/{order_id}/{file_name}"

        # generate signed URL valid for 1 hour
        signed_url = supabase.storage.from_(BUCKET).create_signed_url(file_path, 3600)

        return {"url": signed_url["signedURL"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))