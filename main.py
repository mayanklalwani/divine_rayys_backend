import hashlib
import sys
import psycopg2
import psycopg2.extras
from supabase import create_client, Client
from math import floor
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.lib.pagesizes import A4, landscape
import socket
import os
import uvicorn
import logging
from urllib.parse import quote_plus, urlparse, urlunparse
from app.routes.debug import router as debug_router

logging.basicConfig(
    level=getattr(logging, "INFO", logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

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
import httpx
import json
import types

# Set your Supabase credentials
SUPABASE_URL = "https://zjgzqudobxmqgulyhgft.supabase.co"   # Replace with your project URL
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqZ3pxdWRvYnhtcWd1bHloZ2Z0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTM1NzY5NSwiZXhwIjoyMDcwOTMzNjk1fQ.CLfTneOENRa0ccIxz3Na1VqLbREdmj5X7ieaWj3OFWw"          # Replace with your API key

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# def _unpack_supabase_response(res):
#     """
#     Return (data, error) for many supabase client shapes, including httpx.Response.
#     """
#     # httpx.Response (requests-like)
#     if isinstance(res, httpx.Response):
#         # treat 2xx as success; try to parse JSON body
#         try:
#             body = res.json()
#         except Exception:
#             body = None
#         if 200 <= res.status_code < 300:
#             # success: body may contain {"data": ...} or be the raw result
#             if isinstance(body, dict) and "data" in body:
#                 return body.get("data"), None
#             return body or None, None
#         else:
#             # non-2xx -> try to extract error
#             err = None
#             if isinstance(body, dict):
#                 err = body.get("error") or body.get("message") or json.dumps(body)
#             else:
#                 err = f"HTTP {res.status_code}: {res.text[:200]}"
#             return None, err

#     # object-like (many supabase-py versions)
#     if hasattr(res, "data") or hasattr(res, "error"):
#         data = getattr(res, "data", None)
#         err = getattr(res, "error", None)
#         if err is None and hasattr(res, "status_code") and getattr(res, "status_code") not in (200, 201, None):
#             err = getattr(res, "message", None) or getattr(res, "error_message", None) or str(res)
#         return data, err

#     # dict-like
#     if isinstance(res, dict):
#         data = res.get("data") or res.get("body") or res.get("result")
#         err = res.get("error") or res.get("message")
#         return data, err

#     # tuple/list-like
#     if isinstance(res, (list, tuple)) and len(res) >= 1:
#         return res[0], None

#     # unknown shape
#     try:
#         info = {"type": str(type(res)), "repr": repr(res)[:200], "dir": sorted([d for d in dir(res) if not d.startswith("_")])[:60]}
#     except Exception:
#         info = {"type": str(type(res))}
#     return None, f"Unexpected Supabase response shape: {info}"

def _parse_iso_datetime(val):
    """
    Convert ISO-like timestamp strings to datetime if possible.
    Handles "YYYY-MM-DDTHH:MM:SS", with optional fractional seconds and trailing 'Z' or timezone.
    If parsing fails or val is already a datetime, returns val unchanged.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if not isinstance(val, str):
        return val
    s = val
    # Convert trailing Z -> +00:00 for fromisoformat
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # If there is a space between date/time instead of T, replace with T
    if " " in s and "T" not in s:
        s = s.replace(" ", "T")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # Try a few common formats as fallback
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt)
            except Exception:
                continue
    # give up and return original string
    return val

def _unpack_supabase_response(res):
    """
    Return (data, error). Handles:
      - httpx.Response
      - objects with .data/.error
      - dict-like
      - tuple/list-like
      - storage UploadResponse-like objects (path/full_path)
    """
    # httpx.Response (requests-like)
    if isinstance(res, httpx.Response):
        try:
            body = res.json()
        except Exception:
            body = None
        if 200 <= res.status_code < 300:
            if isinstance(body, dict) and "data" in body:
                return body.get("data"), None
            return body or None, None
        else:
            if isinstance(body, dict):
                err = body.get("error") or body.get("message") or json.dumps(body)
            else:
                err = f"HTTP {res.status_code}: {res.text[:200]}"
            return None, err

    # storage UploadResponse-like objects (storage3.types.UploadResponse)
    # Many such objects expose attributes: path, full_path, fullPath, etc.
    for attr_name in ("path", "full_path", "fullPath", "fullPath"):
        if hasattr(res, attr_name):
            # Build a simple dict representing the upload result
            try:
                path_val = getattr(res, "path", None)
                full_path_val = getattr(res, "full_path", None) or getattr(res, "fullPath", None) or getattr(res, "full_path", None)
            except Exception:
                path_val = None
                full_path_val = None
            data = {"path": path_val, "full_path": full_path_val}
            return data, None

    # object-like (many supabase-py versions)
    if hasattr(res, "data") or hasattr(res, "error"):
        data = getattr(res, "data", None)
        err = getattr(res, "error", None)
        if err is None and hasattr(res, "status_code") and getattr(res, "status_code") not in (200, 201, None):
            err = getattr(res, "message", None) or getattr(res, "error_message", None) or str(res)
        return data, err

    # dict-like
    if isinstance(res, dict):
        data = res.get("data") or res.get("body") or res.get("result")
        err = res.get("error") or res.get("message")
        return data, err

    # tuple/list-like
    if isinstance(res, (list, tuple)) and len(res) >= 1:
        return res[0], None

    # unknown shape -> useful debug info
    try:
        info = {"type": str(type(res)), "repr": repr(res)[:200], "dir": sorted([d for d in dir(res) if not d.startswith("_")])[:60]}
    except Exception:
        info = {"type": str(type(res))}
    return None, f"Unexpected Supabase response shape: {info}"

def _extract_public_url_from_response(pub_res):
    """
    Return a URL string from various shapes:
      - httpx.Response with JSON body
      - dict-like with data/publicURL
      - object with attributes
    """
    if pub_res is None:
        return None

    # httpx.Response
    if isinstance(pub_res, httpx.Response):
        try:
            body = pub_res.json()
        except Exception:
            body = None
        # some responses contain {"publicURL": "..."} or {"data": {"publicURL": "..."}}
        if isinstance(body, dict):
            if "publicURL" in body:
                return body["publicURL"]
            if "public_url" in body:
                return body["public_url"]
            if "data" in body and isinstance(body["data"], dict):
                for k in ("publicURL", "public_url", "signedURL", "url"):
                    if k in body["data"]:
                        return body["data"][k]
        # fallback: search text
        text = pub_res.text or ""
        if "http" in text:
            import re
            m = re.search(r"https?://[^\s'\"]+", text)
            if m:
                return m.group(0)
        return None

    # dict-like or object with .get/.data
    if isinstance(pub_res, dict):
        for k in ("publicURL", "public_url", "url", "signedURL", "signed_url"):
            if k in pub_res:
                return pub_res[k]
        if "data" in pub_res and isinstance(pub_res["data"], dict):
            for k in ("publicURL", "public_url", "url", "signedURL"):
                if k in pub_res["data"]:
                    return pub_res["data"][k]

    if hasattr(pub_res, "data"):
        data = getattr(pub_res, "data")
        if isinstance(data, dict):
            for k in ("publicURL", "public_url", "url", "signedURL"):
                if k in data:
                    return data[k]
    # last resort: str()
    s = str(pub_res)
    if "http" in s:
        import re
        m = re.search(r"https?://[^\s'\"]+", s)
        if m:
            return m.group(0)
    return None

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

app.include_router(debug_router)

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

def get_conn():
    """
    IPv4-first DB connector:
     - Try all IPv4 addresses for HOST first (connect to IPv4 literal).
     - If IPv4 attempts fail, try connecting using the hostname (system default).
     - Finally try IPv6 addresses (explicit) before giving up.
    """
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

    user = USER
    password = PASSWORD
    host = HOST
    port = int(PORT or 5432)
    dbname = DBNAME

    last_exc = None

    # 1) Resolve IPv4 addresses and try them first
    try:
        infos4 = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        infos4 = []
        logger.error("IPv4 resolution failed for %s: %s", host, e)

    if infos4:
        for info in infos4:
            ipv4 = info[4][0]
            try:
                logger.info("Attempting connect to IPv4 %s:%s", ipv4, port)
                return psycopg2.connect(
                    user=user,
                    password=password,
                    host=ipv4,
                    port=str(port),
                    dbname=dbname,
                    connect_timeout=connect_timeout,
                    sslmode="require",
                )
            except Exception as e:
                logger.warning("Connect to IPv4 %s failed: %s", ipv4, e)
                last_exc = e

    # 2) Fall back to hostname (let libpq choose; may try IPv6)
    try:
        logger.info("Attempting connect to hostname %s:%s", host, port)
        return psycopg2.connect(
            user=user,
            password=password,
            host=host,
            port=str(port),
            dbname=dbname,
            connect_timeout=connect_timeout,
            sslmode="require",
        )
    except Exception as e:
        logger.warning("Connect to hostname %s failed: %s", host, e)
        last_exc = e

    # 3) Try IPv6 explicit addresses (useful if IPv4 attempts failed but IPv6 works)
    try:
        infos6 = socket.getaddrinfo(host, port, family=socket.AF_INET6, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        infos6 = []
        logger.debug("IPv6 resolution failed for %s: %s", host, e)

    if infos6:
        for info in infos6:
            ipv6 = info[4][0]
            try:
                logger.info("Attempting connect to IPv6 %s:%s", ipv6, port)
                return psycopg2.connect(
                    user=user,
                    password=password,
                    host=ipv6,
                    port=str(port),
                    dbname=dbname,
                    connect_timeout=connect_timeout,
                    sslmode="require",
                )
            except Exception as e:
                logger.warning("Connect to IPv6 %s failed: %s", ipv6, e)
                last_exc = e

    # Nothing worked — raise informative error
    raise RuntimeError(
        f"Failed to connect to Postgres (host={host!r}, port={port}). "
        "Tried IPv4 addresses, hostname, and IPv6 addresses. See logs for details."
    ) from last_exc

# Validation helper
def validate_order_data(phone, name, addressLine1, pincode, city, state, quantity, paymentProof):
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
    # Validations (keep your existing check)
    validate_order_data(phone, name, addressLine1, pincode, city, state, quantity, paymentProof)

    # ---- 1) check existing pending order by email or phone ----
    try:
        res_phone = supabase.table("orders").select("id").eq("phone", phone).eq("status", "pending").limit(1).execute()
        data_p, err_p = _unpack_supabase_response(res_phone)
        if err_p:
            logger.error("Supabase error while checking phone: %s", err_p)
            raise HTTPException(status_code=500, detail=f"Supabase check failed: {err_p}")
        if data_p and len(data_p) > 0:
            raise HTTPException(status_code=400, detail="Your order is already submitted. We do not accept multiple orders.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error during existence check: %s", e)
        raise HTTPException(status_code=500, detail=f"Supabase check failed: {e}")

    # ---- 2) insert order row ----
    now_iso = datetime.now().isoformat()
    payload = {
        "phone": phone,
        "name": name,
        "addressline1": addressLine1,
        "addressline2": addressLine2,
        "landmark": landmark,
        "pincode": pincode,
        "city": city,
        "state": state,
        "country": country,
        "quantity": quantity,
        "status": "pending",
        "created_at": now_iso,
    }

    try:
        ins = supabase.table("orders").insert(payload).execute()
        ins_data, ins_err = _unpack_supabase_response(ins)
        if ins_err:
            logger.error("Supabase insert error: %s", ins_err)
            raise HTTPException(status_code=500, detail=f"Failed to create order: {ins_err}")
        if not ins_data or len(ins_data) == 0:
            logger.error("Supabase insert returned no data: %s", repr(ins))
            raise HTTPException(status_code=500, detail="Failed to create order (no row returned).")
        order_id = ins_data[0].get("id")
        if order_id is None:
            # attempt to read 'id' with varying keys
            order_id = ins_data[0].get("order_id") or ins_data[0].get("ID") or ins_data[0].get("Id")
        if order_id is None:
            logger.error("Could not determine inserted order id from response: %s", ins_data[0])
            raise HTTPException(status_code=500, detail="Failed to determine order id after insert.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Insert failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create order: {e}")

    # ---- 3) upload payment proof if present ----
    payment_proof_url = None
    if paymentProof:
        try:
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{paymentProof.filename}"
            file_bytes = await paymentProof.read()
            supabase_path = f"uploads/{order_id}/{filename}"

            # upload (some supabase clients raise on failure; some return dict)
            upload_res = supabase.storage.from_(BUCKET).upload(path=supabase_path, file=file_bytes, file_options={"content-type": paymentProof.content_type})
            # If upload returns an error shape, try to detect it:
            up_data, up_err = _unpack_supabase_response(upload_res)
            # If _unpack reported an error, fail. Otherwise proceed.
            if up_err:
                logger.error("Storage upload reported error: %s ; upload_res_repr=%s", up_err, repr(upload_res)[:400])
                raise HTTPException(status_code=500, detail=f"Failed to upload payment proof: {up_err}")

            # If upload returned data with full_path/path, try to construct public URL
            uploaded_path = None
            if isinstance(up_data, dict):
                uploaded_path = up_data.get("full_path") or up_data.get("fullPath") or up_data.get("path")
            # Some clients returned the data directly (e.g. dict) or None; fallback to known supabase_path
            if not uploaded_path:
                uploaded_path = supabase_path  # fallback

            try:
                # get public URL (various shapes)
                pub_res = supabase.storage.from_(BUCKET).get_public_url(supabase_path)
                payment_proof_url = _extract_public_url_from_response(pub_res)
            except Exception as e:
                logger.debug("get_public_url call failed: %s", e)
                payment_proof_url = None

            if not payment_proof_url:
                # fallback to signed url (1 hour)
                try:
                    signed_res = supabase.storage.from_(BUCKET).create_signed_url(supabase_path, 3600)
                    signed_data, signed_err = _unpack_supabase_response(signed_res)
                    if signed_err:
                        logger.warning("Signed URL call returned error: %s, resp=%s", signed_err, repr(signed_res)[:400])
                    # signed_data may be dict with {'signedURL': '...'} or httpx.Response - handle both
                    if isinstance(signed_res, httpx.Response):
                        payment_proof_url = _extract_public_url_from_response(signed_res)
                    elif isinstance(signed_data, dict):
                        payment_proof_url = signed_data.get("signedURL") or signed_data.get("signed_url") or signed_data.get("url")
                    else:
                        payment_proof_url = _extract_public_url_from_response(signed_res)
                except Exception as se:
                    logger.warning("Failed to create signed url fallback: %s", se)
                    payment_proof_url = None

            # if still missing, continue but log
            if not payment_proof_url:
                logger.warning("Could not extract public URL after upload. upload_res=%s pub_res=%s", repr(upload_res), repr(pub_res))

            # update the row with paymentProof (if url found)
            if payment_proof_url:
                upd = supabase.table("orders").update({"paymentproof": payment_proof_url}).eq("id", order_id).execute()
                upd_d, upd_err = _unpack_supabase_response(upd)
                if upd_err:
                    logger.error("Failed to update order with paymentProof: %s", upd_err)
                    # not fatal for the order; but inform client
                    raise HTTPException(status_code=500, detail=f"Uploaded payment proof but failed to record it: {upd_err}")

        except HTTPException:
            # bubble up intentionally thrown HTTPExceptions
            raise
        except Exception as e:
            logger.exception("Failed to upload payment proof or update row: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to upload payment proof: {e}")

    # success
    return {"message": "Order received successfully", "order_id": order_id, "paymentProof": payment_proof_url, "quantity": quantity}

# ---------- Label Generation ----------
FROM_BLOCK = [
    "From :",
    "Kaillash Rrohida,",
    "Indore,",
    "Mobile: +91-9893270011",
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
#     Draw a single label in the slot rectangle (x_left, y_top) with slot_width x slot_height.
#     Ensures FROM block is wrapped to slot_width and body text doesn't overlap it.
#     """
#     # visual metrics
#     leading = 12
#     name_font = ("Helvetica-Bold", 12)
#     body_font = ("Helvetica", 11)
#     inset = 4 * mm
#     gap_between_body_and_from = 3 * mm
#     from_font = ("Helvetica", 10)
#     from_line_height = 12  # vertical spacing for FROM lines

#     # Prepare FROM block wrapped to slot width
#     maxw = slot_width - 2 * inset
#     raw_from_lines = FROM_BLOCK if isinstance(FROM_BLOCK, (list, tuple)) else [FROM_BLOCK]
#     wrapped_from_lines = []
#     for raw in raw_from_lines:
#         if not raw:
#             continue
#         # simpleSplit returns wrapped lines for the available width
#         wrapped = simpleSplit(raw, from_font[0], from_font[1], maxw)
#         if wrapped:
#             wrapped_from_lines.extend(wrapped)
#         else:
#             wrapped_from_lines.append(raw)

#     from_height = len(wrapped_from_lines) * from_line_height

#     # Reserve bottom area for FROM block + inset + small gap
#     reserved_bottom = inset + from_height + gap_between_body_and_from

#     # Compute boundaries
#     slot_bottom_y = y_top - slot_height
#     min_allowed_y_for_body = slot_bottom_y + reserved_bottom

#     # Start drawing from top
#     y = y_top

#     # "To," heading
#     c.setFont(name_font[0], name_font[1])
#     c.drawString(x_left + inset, y, "To,")
#     y -= leading

#     # Recipient name
#     c.setFont(body_font[0], body_font[1])
#     name_line = (order.get("name") or "").strip()
#     y = draw_wrapped_text_slot(
#         c, name_line, x_left + inset, y,
#         maxw, min_allowed_y_for_body,
#         font_name=body_font[0], font_size=body_font[1], leading=leading
#     )

#     # Address fields (joined)
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

#     # city/state/pincode
#     city_state_pin = ", ".join([v for v in [order.get("city"), order.get("state")] if v])
#     if order.get("pincode"):
#         city_state_pin = f"{city_state_pin} - {order.get('pincode')}" if city_state_pin else order.get("pincode")

#     if city_state_pin:
#         y = draw_wrapped_text_slot(
#             c, city_state_pin, x_left + inset, y,
#             maxw, min_allowed_y_for_body,
#             font_name=body_font[0], font_size=body_font[1], leading=leading
#         )

#     # Now draw the FROM block inside the reserved bottom area.
#     # We'll draw from top-to-bottom inside that reserved area.
#     c.setFont(from_font[0], from_font[1])

#     # compute starting y for first FROM line (topmost of FROM block)
#     # topmost_from_y = slot_bottom_y + reserved_bottom - (inset) - (from_line_height - (from_line_height))
#     # simpler: position first wrapped_from_lines[0] at slot_bottom_y + reserved_bottom - (from_line_height)
#     topmost_from_y = slot_bottom_y + inset + from_height - from_line_height
#     # Draw each wrapped FROM line in order
#     for i, line in enumerate(wrapped_from_lines):
#         line_y = topmost_from_y - i * from_line_height
#         # safety clamp: do not draw below slot bottom + inset
#         if line_y < slot_bottom_y + inset - 1:
#             continue
#         c.drawString(x_left + inset, line_y, line)

def draw_label_block(c, order, x_left, y_top, slot_width, slot_height):
    """
    Draw a single label inside slot rectangle (x_left, y_top) with slot_width x slot_height.
    Ensures FROM block is wrapped to slot_width and body text doesn't overlap it.
    NOTE: y_top is the top edge of the slot (measured from page bottom).
    """
    # visual metrics
    leading = 17
    name_font = ("Helvetica", 16)
    body_font = ("Helvetica", 16)
    inset = 6 * mm              # horizontal & vertical inset inside slot
    gap_between_body_and_from = 1 * mm
    from_font = ("Helvetica", 10)
    from_line_height = 12  # vertical spacing for FROM lines

    # Prepare FROM block wrapped to slot width (respect inset)
    maxw = slot_width - 2 * inset
    raw_from_lines = FROM_BLOCK if isinstance(FROM_BLOCK, (list, tuple)) else [FROM_BLOCK]
    wrapped_from_lines = []
    for raw in raw_from_lines:
        if not raw:
            continue
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

    # Start drawing from top, but apply a vertical top inset so text doesn't draw above the slot
    y = y_top - inset

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

    
    qty = order.get("quantity") or 0
    if qty:
        y -= 2  # a small vertical gap (adjust if needed)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_left + inset, y, f"Qty: {int(qty)}")
        y -= leading
        c.setFont(body_font[0], body_font[1])  # restore body font for next lines

    # Now draw the FROM block inside the reserved bottom area.
    c.setFont(from_font[0], from_font[1])

    # compute starting y for first FROM line (topmost of FROM block) inside reserved area
    topmost_from_y = slot_bottom_y + inset + from_height - from_line_height
    for i, line in enumerate(wrapped_from_lines):
        line_y = topmost_from_y - i * from_line_height
        # safety clamp: do not draw below slot bottom + inset
        if line_y < slot_bottom_y + inset - 1:
            continue
        c.drawString(x_left + inset, line_y, line)


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
    try:
        res = supabase.table("orders").select("*").order("created_at", desc=True).execute()

        data, err = _unpack_supabase_response(res)
        if err:
            # Log detailed debug info for troubleshooting, but do not leak secret content back to client
            logger.error("Supabase returned error: %s; response type/dir=%s", err, getattr(res, "__class__", type(res)))
            # provide generic error to client
            raise HTTPException(status_code=500, detail=f"Supabase query failed: {err}")

        # data might be None if table empty — normalize to []
        return {"orders": data or []}

    except HTTPException:
        # re-raise HTTPExceptions thrown intentionally above
        raise
    except Exception as e:
        # Unexpected exception — capture type and partial repr of `res` if in scope to help debugging
        logger.exception("Unexpected exception while fetching orders: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch orders: {e}")

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

# def generate_bulk_labels_a4(order_ids):
#     """
#     Generates labels on A4 landscape sheets.
#     Layout: 3 columns × 2 rows = 6 labels per page.
#     Each label has a border rectangle.
#     """
#     ts = datetime.now().strftime("%Y%m%d_%H%M%S")
#     pdf_path = os.path.join(LABEL_FOLDER, f"labels_bulk_a4_{ts}.pdf")

#     # A4 in landscape orientation
#     page_width, page_height = landscape(A4)

#     # 3 cols × 2 rows grid
#     cols, rows = 3, 2
#     slot_width = page_width / cols
#     slot_height = page_height / rows

#     c = canvas.Canvas(pdf_path, pagesize=(page_width, page_height))

#     conn = get_conn()
#     cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

#     for i, oid in enumerate(order_ids):
#         # Fetch order
#         cur.execute("SELECT * FROM orders WHERE id=%s", (oid,))
#         row = cur.fetchone()
#         if not row:
#             continue
#         order = dict(row)

#         # Grid position
#         grid_index = i % (cols * rows)  # 0..5
#         col = grid_index % cols
#         row_num = grid_index // cols

#         # Top-left of this slot
#         x_left = col * slot_width
#         y_top = page_height - (row_num * slot_height)

#         # Draw border rectangle
#         c.rect(x_left, y_top - slot_height, slot_width, slot_height)

#         # Draw label content
#         draw_label_block(c, order, x_left, y_top, slot_width, slot_height)

#         # After 6 labels, start a new page
#         if grid_index == (cols * rows - 1):
#             c.showPage()

#     conn.close()
#     c.save()
#     return pdf_path

def generate_bulk_labels_a4(order_ids):
    """
    A4 landscape, 3 columns x 2 rows = 6 labels per page.
    Adds outer margins and border around each slot.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(LABEL_FOLDER, f"labels_bulk_a4_{ts}.pdf")

    # A4 landscape
    page_width, page_height = landscape(A4)

    # layout grid
    cols, rows = 3, 2

    # outer margin (adjust if you need larger margins)
    margin = 10 * mm

    # compute usable area inside margins
    usable_width = page_width - 2 * margin
    usable_height = page_height - 2 * margin

    # slot sizes
    slot_width = usable_width / cols
    slot_height = usable_height / rows

    # gutter between slots (optional)
    gutter = 4 * mm

    c = canvas.Canvas(pdf_path, pagesize=(page_width, page_height))

    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # iterate orders and place them in grid; create a new page every cols*rows items
    for i, oid in enumerate(order_ids):
        # fetch order
        cur.execute("SELECT * FROM orders WHERE id=%s", (oid,))
        row = cur.fetchone()
        if not row:
            continue
        order = dict(row)

        # index within page (0 .. cols*rows-1)
        index_in_page = i % (cols * rows)
        col = index_in_page % cols
        row_idx = index_in_page // cols  # 0 = top row, 1 = bottom row (we'll invert below)

        # compute top-left of slot (ReportLab origin is bottom-left)
        x_left = margin + col * slot_width
        # for y, row_idx 0 should be TOP row -> y_top = page_height - margin - (row_idx * slot_height)
        y_top = page_height - margin - (row_idx * slot_height)

        # Draw border rectangle for the slot
        c.setLineWidth(0.6)
        c.rect(x_left, y_top - slot_height, slot_width, slot_height)

        # (Optional) draw vertical separator dashed line between columns (visual aid)
        # you can uncomment if you also want dashed lines between slots
        # if col < cols - 1:
        #     sep_x = x_left + slot_width + (gutter / 2.0)
        #     c.setDash(3, 3)
        #     c.line(x_left + slot_width, y_top - slot_height, x_left + slot_width, y_top)
        #     c.setDash()

        # draw label content inside the slot. draw_label_block expects:
        #   (canvas, order, x_left, y_top, slot_width, slot_height)
        draw_label_block(c, order, x_left, y_top, slot_width, slot_height)

        # show page at end of full page or at the very end (we'll call showPage when page full)
        if index_in_page == (cols * rows - 1):
            c.showPage()

    # If the last page was partial (i.e., not exactly multiple of cols*rows) we must still finalize it.
    # If the last operation did NOT end with showPage (i.e., last index not the last of page), call showPage.
    if len(order_ids) % (cols * rows) != 0:
        c.showPage()

    conn.close()
    c.save()
    return pdf_path

@app.get("/orders/{order_id}/label")
def get_order_label(order_id: int):
    try:
        r = supabase.table("orders").select("*").eq("id", order_id).execute()
        if r.error:
            raise RuntimeError(r.error)
        if not r.data:
            raise HTTPException(status_code=404, detail="Order not found")
        order = r.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch order: {e}")

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
# @app.get("/admin", response_class=HTMLResponse)
# def admin_dashboard(request: Request):
#     if not request.session.get("admin"):
#         return RedirectResponse(url="/admin/login", status_code=302)
#     # return templates.TemplateResponse("admin_orders.html", {"request": request})
#     conn = get_conn()
#     cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

#     cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders WHERE status='pending'")
#     row = cursor.fetchone()
#     pending_count, pending_qty = row["count"], row["qty"]

#     cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders WHERE status='shipped'")
#     row = cursor.fetchone()
#     shipped_count, shipped_qty = row["count"], row["qty"]

#     cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders WHERE status='cancelled'")
#     row = cursor.fetchone()
#     cancelled_count, cancelled_qty = row["count"], row["qty"]

#     cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(quantity),0) as qty FROM orders")
#     row = cursor.fetchone()
#     total_count, total_qty = row["count"], row["qty"]

#     cursor.execute("SELECT * FROM orders WHERE status='pending'")
#     orders = cursor.fetchall()

#     conn.close()

#     counts = {
#         "pending": pending_count,
#         "shipped": shipped_count,
#         "cancelled": cancelled_count,
#     }

#     stats = {
#         "orders": {
#             "pending": pending_count,
#             "shipped": shipped_count,
#             "cancelled": cancelled_count,
#             "all": total_count,
#         },
#         "qty": {
#             "pending": pending_qty,
#             "shipped": shipped_qty,
#             "cancelled": cancelled_qty,
#             "all": total_qty,
#         }
#     }

#     return templates.TemplateResponse(
#         "admin_orders.html",
#         {
#             "request": request,
#             "stats": stats,
#             "orders": orders
#         }
#     )

# @app.get("/admin", response_class=HTMLResponse)
# def admin_dashboard(request: Request):
#     # auth
#     if not request.session.get("admin"):
#         return RedirectResponse(url="/admin/login", status_code=302)

#     try:
#         # --- pending counts/qty ---
#         # Try to get counts & sums via supabase. Some clients support .select("id", count="exact")
#         # but we handle the common shapes and fallback to separate queries.
#         def safe_count_and_sum(status_val=None):
#             """
#             Returns (count:int, qty:int) for given status (None => all)
#             """
#             try:
#                 query = supabase.table("orders")
#                 # Use explicit select to possibly get a count via returned rows
#                 if status_val:
#                     query = query.select("id, quantity").eq("status", status_val)
#                 else:
#                     query = query.select("id, quantity")
#                 res = query.execute()
#                 data, err = _unpack_supabase_response(res)
#                 if err:
#                     # fallback: try sql via rpc or return zeros
#                     logger.warning("Count query returned error for status=%s: %s", status_val, err)
#                     return 0, 0
#                 rows = data or []
#                 cnt = len(rows)
#                 qty = sum((int(r.get("quantity") or 0) for r in rows))
#                 return cnt, qty
#             except Exception as e:
#                 logger.exception("safe_count_and_sum failed for status=%s: %s", status_val, e)
#                 return 0, 0

#         pending_count, pending_qty = safe_count_and_sum("pending")
#         shipped_count, shipped_qty = safe_count_and_sum("shipped")
#         cancelled_count, cancelled_qty = safe_count_and_sum("cancelled")
#         total_count, total_qty = safe_count_and_sum(None)

#         # --- fetch pending orders (limited to a reasonable number, e.g. 500) ---
#         try:
#             res_orders = supabase.table("orders").select("*").eq("status", "pending").order("created_at", desc=True).limit(500).execute()
#             orders_data, orders_err = _unpack_supabase_response(res_orders)
#             if orders_err:
#                 logger.error("Failed to fetch pending orders: %s", orders_err)
#                 orders = []
#             else:
#                 orders = orders_data or []
#         except Exception as e:
#             logger.exception("Error fetching pending orders: %s", e)
#             orders = []

#         # ensure rows are simple dicts for the template
#         orders = [dict(o) for o in orders]

#         stats = {
#             "orders": {
#                 "pending": pending_count,
#                 "shipped": shipped_count,
#                 "cancelled": cancelled_count,
#                 "all": total_count,
#             },
#             "qty": {
#                 "pending": pending_qty,
#                 "shipped": shipped_qty,
#                 "cancelled": cancelled_qty,
#                 "all": total_qty,
#             }
#         }

#         return templates.TemplateResponse(
#             "admin_orders.html",
#             {
#                 "request": request,
#                 "stats": stats,
#                 "orders": orders
#             }
#         )

#     except Exception as e:
#         logger.exception("Unhandled error in admin_dashboard: %s", e)
#         # show a simple error page / redirect to login
#         raise HTTPException(status_code=500, detail=f"Failed to load admin dashboard: {e}")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    # auth
    if not request.session.get("admin"):
        return RedirectResponse(url="/admin/login", status_code=302)

    try:
        def safe_count_and_sum(status_val=None):
            try:
                query = supabase.table("orders")
                if status_val:
                    query = query.select("id, quantity").eq("status", status_val)
                else:
                    query = query.select("id, quantity")
                res = query.execute()
                data, err = _unpack_supabase_response(res)
                if err:
                    logger.warning("Count query returned error for status=%s: %s", status_val, err)
                    return 0, 0
                rows = data or []
                cnt = len(rows)
                qty = sum((int(r.get("quantity") or 0) for r in rows))
                return cnt, qty
            except Exception as e:
                logger.exception("safe_count_and_sum failed for status=%s: %s", status_val, e)
                return 0, 0

        pending_count, pending_qty = safe_count_and_sum("pending")
        shipped_count, shipped_qty = safe_count_and_sum("shipped")
        cancelled_count, cancelled_qty = safe_count_and_sum("cancelled")
        total_count, total_qty = safe_count_and_sum(None)

        # fetch pending orders
        try:
            res_orders = supabase.table("orders").select("*").eq("status", "pending").order("created_at", desc=True).limit(500).execute()
            orders_data, orders_err = _unpack_supabase_response(res_orders)
            if orders_err:
                logger.error("Failed to fetch pending orders: %s", orders_err)
                orders = []
            else:
                orders = orders_data or []
        except Exception as e:
            logger.exception("Error fetching pending orders: %s", e)
            orders = []

        # Normalize orders: convert created_at (and other ISO timestamps if present) to datetime
        normalized = []
        for o in orders:
            try:
                # ensure it's a dict
                od = dict(o)
                for key in ("created_at", "updated_at", "createdAt", "updatedAt"):
                    if key in od and od[key]:
                        od[key] = _parse_iso_datetime(od[key])
                normalized.append(od)
            except Exception as e:
                logger.warning("Failed to normalize order row: %s. Row repr: %s", e, repr(o)[:400])
                # still include raw row so UI can show something
                try:
                    normalized.append(dict(o))
                except Exception:
                    normalized.append(o)

        orders = normalized

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

    except Exception as e:
        logger.exception("Unhandled error in admin_dashboard: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load admin dashboard: {e}")

# ---- Data API for the dashboard table ----

@app.get("/admin/orders")
def admin_list_orders(request: Request, status: str = "pending", q: str = "", page: int = 1, page_size: int = 20):
    require_admin(request)

    offset = max(0, (page - 1) * page_size)
    start = offset
    end = offset + page_size - 1

    try:
        # Start with select(*) so .eq/.range/.order exist on the returned builder
        query = supabase.table("orders").select("*")

        # Add filters AFTER select()
        if status:
            query = query.eq("status", status)

        # (Optional) if you want server-side text filtering and your supabase client supports ilike:
        # if q:
        #     query = query.ilike("name", f"%{q}%")  # adjust field(s) as needed
        # If ilike isn't available, we'll filter in-Python after fetching the page.

        # Apply ordering & pagination
        res = query.order("id", desc=True).range(start, end).execute()

        # Unpack response safely
        rows, err = _unpack_supabase_response(res)
        if err:
            logger.error("Supabase query error (list): %s", err)
            raise HTTPException(status_code=500, detail=f"Query failed: {err}")

        rows = rows or []

        # If user supplied q and the client doesn't support ilike, do simple filter locally:
        if q:
            q_lower = q.lower()
            def matches(r):
                return (
                    (r.get("phone") and q_lower in str(r.get("phone")).lower()) or
                    (r.get("name") and q_lower in str(r.get("name")).lower())
                )
            rows = [r for r in rows if matches(r)]

        # Get total count (safe, simple approach)
        try:
            count_query = supabase.table("orders").select("id")
            if status:
                count_query = count_query.eq("status", status)
            count_res = count_query.execute()
            count_data, count_err = _unpack_supabase_response(count_res)
            if count_err:
                logger.warning("Count query returned unexpected shape/error, falling back to page length: %s", count_err)
                total = len(rows)
            else:
                total = len(count_data or [])
        except Exception as ce:
            logger.warning("Count query failed; using page length fallback: %s", ce)
            total = len(rows)

    except HTTPException:
        # bubble up authentication / client errors
        raise
    except Exception as e:
        logger.exception("Unhandled error in admin_list_orders: %s", e)
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return templates.TemplateResponse(
        "admin_orders_filtered.html",
        {
            "request": request,
            "orders": [dict(r) for r in rows],
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
    try:
        res = supabase.table("orders").update({"status": status}).eq("id", order_id).execute()
        if res.error:
            raise RuntimeError(res.error)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
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
        # pdf_path = generate_bulk_labels(order_ids)
        # return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))
        pdf_path = generate_bulk_labels_a4(order_ids)
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

@app.get("/_supabase_dbg")
def _supabase_dbg():
    res = supabase.table("orders").select("*").limit(1).execute()
    return {
        "type": str(type(res)),
        "repr": repr(res)[:200],
        "dir_sample": sorted([d for d in dir(res) if not d.startswith("_")])[:60]
    }


if __name__ == "__main__":
    # Config from env (sane defaults)
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()  # debug/info/warning/error
    # DEV_RELOAD can be "1", "true", "yes" to enable reload; default True for local dev
    DEV_RELOAD = os.getenv("DEV_RELOAD", "true").lower() in ("1", "true", "yes")

    # Note: reload=True is for development only (auto-restarts on code changes).
    # Do NOT enable reload on production hosts (Render, etc.) — they typically run uvicorn themselves.
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=DEV_RELOAD,
        log_level=LOG_LEVEL,
    )