import hashlib
import sys
from supabase import create_client, Client
from math import floor
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
import socket
import os
import uvicorn
import logging
from urllib.parse import quote_plus, urlparse, urlunparse
from app.routes.debug import router as debug_router
from fastapi import Query

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
from reportlab.lib.pagesizes import A6, A4
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
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import tempfile
from openpyxl import Workbook
from openpyxl.styles import Border, Side, Alignment, Font

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

# -------------------------
# Helper: fetch orders by ids preserving input order
# -------------------------
def _fetch_orders_by_ids(order_ids):
    """
    Return list of order dicts in the same order as order_ids.
    Uses a single supabase query to fetch all rows then reorders to match the input ids.
    """
    if not order_ids:
        return []

    try:
        # supabase-py supports .in_("id", order_ids)
        res = supabase.table("orders_ch2025").select("*").in_("id", order_ids).execute()
        data, err = _unpack_supabase_response(res)
        if err:
            logger.error("Failed to fetch orders by ids: %s", err)
            return []
        rows = data or []
        # Map by id for ordering
        by_id = {int(r.get("id")): dict(r) for r in rows}
        ordered = []
        for oid in order_ids:
            try:
                ordered.append(by_id[int(oid)])
            except Exception:
                # if a particular id missing, skip
                logger.debug("Order id %s not found in fetched rows", oid)
        return ordered
    except Exception as e:
        logger.exception("Exception in _fetch_orders_by_ids: %s", e)
        return []

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

# ---------- Helper: iterate orders in chunks to avoid Supabase "1000 row" limit ----------
def _iter_orders_chunks(select_cols="id,quantity,status", chunk_size=1000, order_desc=False, status_filter=None):
    """
    Generator that yields lists of rows (chunks) from the orders table.
    Uses .range(start, end) to page through results. Falls back to a single .execute() if .range isn't available.
    """
    start = 0
    while True:
        # build base query
        q = supabase.table("orders_ch2025").select(select_cols)
        if status_filter:
            try:
                q = q.eq("status", status_filter)
            except Exception:
                # client might not support eq in chained fashion; ignore
                pass
        q = q.order("id", desc=order_desc)
        try:
            q = q.range(start, start + chunk_size - 1)
            res = q.execute()
        except Exception:
            # fallback to no-range (may be limited by server/client)
            res = q.execute()

        data, err = _unpack_supabase_response(res)
        if err:
            raise RuntimeError(f"Supabase chunk fetch failed: {err}")

        rows = data or []
        if not rows:
            break

        yield rows

        # if returned less than chunk_size, we've reached the end
        if len(rows) < chunk_size:
            break
        start += chunk_size

def _count_rows(status=None, chunk_size=1000):
    """Return total row count, optionally filtered by status, by iterating chunks."""
    total = 0
    for chunk in _iter_orders_chunks(select_cols="id,status", chunk_size=chunk_size, status_filter=status):
        total += len(chunk)
    return total

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
        res_phone = supabase.table("orders_ch2025").select("id").eq("phone", phone).eq("status", "pending").limit(1).execute()
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
        ins = supabase.table("orders_ch2025").insert(payload).execute()
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
                upd = supabase.table("orders_ch2025").update({"paymentproof": payment_proof_url}).eq("id", order_id).execute()
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
    "Kaillash RRohida,",
    "Indore,",
    "Mobile: +91-9893270011",
]

def fit_and_wrap_lines(text, font_name, font_size, max_width, max_lines, leading, min_font_size=8):
    """
    Try wrapping `text` at font_size into lines that fit max_width using simpleSplit.
    If the wrapped lines exceed max_lines, reduce font_size stepwise until it fits or until min_font_size.
    If it still doesn't fit at min_font_size, truncate last visible line and append '...'.
    Returns: (used_font_size, lines)
    """
    if not text:
        return font_size, []

    used_size = font_size
    # attempt reduce font size until it fits
    while used_size >= min_font_size:
        lines = simpleSplit(text, font_name, used_size, max_width)
        if max_lines is None or len(lines) <= max_lines:
            return used_size, lines
        # not fit -> reduce font size a bit and retry
        used_size -= 1

    # at this point we are at min_font_size and still too many lines: truncate to max_lines
    lines = simpleSplit(text, font_name, min_font_size, max_width)
    if max_lines is None or max_lines <= 0:
        return min_font_size, lines[:max_lines] if max_lines else lines

    if len(lines) > max_lines:
        allowed = lines[:max_lines]
        last = allowed[-1]
        # trim last so ellipsis fits — naive: remove last 3 characters and append '...'
        # better approach: shrink last until width fits
        ell = "..."
        # shorten last until width fits
        while pdfmetrics.stringWidth(allowed[-1] + ell, font_name, min_font_size) > max_width and len(allowed[-1]) > 0:
            allowed[-1] = allowed[-1][:-1]
        allowed[-1] = allowed[-1].rstrip() + ell
        return min_font_size, allowed

    return min_font_size, lines


# def draw_wrapped_text(c, text, x, y, max_width, font_name="Helvetica", font_size=11, leading=14):
#     """
#     Draws text with word wrapping starting at (x,y); y decreases downward.
#     """
#     c.setFont(font_name, font_size)
#     lines = simpleSplit(text, font_name, font_size, max_width)
#     for i, line in enumerate(lines):
#         c.drawString(x, y - i * leading, line)
#     return y - (len(lines) * leading)

def draw_wrapped_text(c, text, x, y, max_width, font_name="Helvetica", font_size=11, leading=14, min_font_size=8):
    """
    Draws text with word wrapping starting at (x,y); y decreases downward.
    Attempts to fit text by reducing font size if needed. Returns final y after drawing.
    """
    if not text:
        return y
    # estimate how many lines can fit if no lower bound: use a large number or compute using page space (caller might know)
    # Here we assume caller wants all lines (no explicit min_y), so we won't clamp vertically but we do attempt to reduce font size
    # to avoid overflowing horizontally and reduce visual overflow.
    used_size, lines = fit_and_wrap_lines(text, font_name, font_size, max_width, None, leading, min_font_size=min_font_size)
    c.setFont(font_name, used_size)
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
#     Draw a single label inside slot rectangle (x_left, y_top) with slot_width x slot_height.
#     Ensures FROM block is wrapped to slot_width and body text doesn't overlap it.
#     NOTE: y_top is the top edge of the slot (measured from page bottom).
#     """
#     # visual metrics
#     leading = 17
#     name_font = ("Helvetica", 16)
#     body_font = ("Helvetica", 16)
#     inset = 6 * mm              # horizontal & vertical inset inside slot
#     gap_between_body_and_from = 1 * mm
#     from_font = ("Helvetica", 10)
#     from_line_height = 12  # vertical spacing for FROM lines

#     # Prepare FROM block wrapped to slot width (respect inset)
#     maxw = slot_width - 2 * inset
#     raw_from_lines = FROM_BLOCK if isinstance(FROM_BLOCK, (list, tuple)) else [FROM_BLOCK]
#     wrapped_from_lines = []
#     for raw in raw_from_lines:
#         if not raw:
#             continue
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

#     # Start drawing from top, but apply a vertical top inset so text doesn't draw above the slot
#     y = y_top - inset

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

    
#     qty = order.get("quantity") or 0
#     if qty:
#         y -= 2  # a small vertical gap (adjust if needed)
#         c.setFont("Helvetica-Bold", 10)
#         c.drawString(x_left + inset, y, f"Qty: {int(qty)}")
#         y -= leading
#         c.setFont(body_font[0], body_font[1])  # restore body font for next lines

#     # Now draw the FROM block inside the reserved bottom area.
#     c.setFont(from_font[0], from_font[1])

#     # compute starting y for first FROM line (topmost of FROM block) inside reserved area
#     topmost_from_y = slot_bottom_y + inset + from_height - from_line_height
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
    Adds Mobile No. line in the "To" block under the name.
    """
    # visual metrics
    leading = 16
    name_font = ("Helvetica-Bold", 14)
    body_font = ("Helvetica", 12)
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

    # Start drawing from top, apply a vertical top inset so text doesn't draw above the slot
    y = y_top - inset

    # "To," heading
    c.setFont(name_font[0], name_font[1])
    c.drawString(x_left + inset, y, "To,")
    y -= leading

    # Recipient name (fit & wrap)
    name_line = (order.get("name") or "").strip()
    if name_line:
        used_size, lines = fit_and_wrap_lines(name_line, body_font[0], body_font[1], maxw, None, leading, min_font_size=8)
        c.setFont(body_font[0], used_size)
        for i, ln in enumerate(lines):
            c.drawString(x_left + inset, y - i * leading, ln)
        y = y - (len(lines) * leading)

    # Address fields (joined)
    addr_parts = [
        (order.get("addressline1") or "").strip(),
        (order.get("addressline2") or "").strip(),
        (order.get("landmark") or "").strip(),
    ]
    addr_text = ", ".join([p for p in addr_parts if p])
    # compute max lines allowed for address given remaining vertical space
    y_available_for_address = y - min_allowed_y_for_body
    if y_available_for_address < 0:
        max_addr_lines = 0
    else:
        max_addr_lines = max(0, floor(y_available_for_address / leading))

    if addr_text and max_addr_lines > 0:
        used_size, lines = fit_and_wrap_lines(addr_text, body_font[0], body_font[1], maxw, max_addr_lines, leading, min_font_size=8)
        c.setFont(body_font[0], used_size)
        for i, ln in enumerate(lines):
            c.drawString(x_left + inset, y - i * leading, ln)
        y = y - (len(lines) * leading)

    # city/state/pincode (try to fit to remaining small area)
    city_state_pin = ", ".join([v for v in [order.get("city"), order.get("state")] if v])
    if order.get("pincode"):
        city_state_pin = f"{city_state_pin} - {order.get('pincode')}" if city_state_pin else order.get("pincode")

    if city_state_pin:
        # small allowance of 1 or 2 lines
        used_size, lines = fit_and_wrap_lines(city_state_pin, body_font[0], body_font[1], maxw, 2, leading, min_font_size=8)
        c.setFont(body_font[0], used_size)
        for i, ln in enumerate(lines):
            c.drawString(x_left + inset, y - i * leading, ln)
        y = y - (len(lines) * leading)

    # Mobile line: Mobile No. : <phone>
    phone = (order.get("phone") or "").strip()
    if phone:
        mobile_text = f"Mobile No. : {phone}"
        # draw mobile in slightly smaller size but ensure it fits in one or two lines
        used_size, lines = fit_and_wrap_lines(mobile_text, body_font[0], 11, maxw, 2, leading, min_font_size=8)
        c.setFont(body_font[0], used_size)
        for i, ln in enumerate(lines):
            c.drawString(x_left + inset, y - i * leading, ln)
        y = y - (len(lines) * leading)

    # Quantity (if present)
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


# def draw_wrapped_text_slot(c, text, x, y, max_width, min_y, font_name="Helvetica", font_size=11, leading=14):
#     """
#     Draw wrapped text starting at y and NOT going below min_y.
#     If text lines exceed available space, truncate and append '...'.
#     Returns new y after drawing.
#     """
#     if not text:
#         return y
#     c.setFont(font_name, font_size)
#     lines = simpleSplit(text, font_name, font_size, max_width)

#     available_height = y - min_y
#     if available_height <= 0:
#         return min_y

#     max_lines = max(0, floor(available_height / leading))

#     if len(lines) == 0:
#         return y

#     if len(lines) > max_lines and max_lines > 0:
#         # keep lines up to max_lines, add ellipsis to last line
#         allowed = lines[:max_lines]
#         last = allowed[-1]
#         ell = "..."
#         # Try to trim last so ellipsis fits. We'll simply append ellipses; ReportLab will clip visually if still too long.
#         allowed[-1] = (last.rstrip() + ell)
#         lines_to_draw = allowed
#     else:
#         lines_to_draw = lines[:max_lines] if max_lines > 0 else []

#     for i, line in enumerate(lines_to_draw):
#         c.drawString(x, y - i * leading, line)

#     return y - (len(lines_to_draw) * leading)

def draw_wrapped_text_slot(c, text, x, y, max_width, min_y, font_name="Helvetica", font_size=11, leading=14, min_font_size=8):
    """
    Draw wrapped text starting at y and NOT going below min_y.
    If text lines exceed available space, reduce font size until it fits or truncate and append '...'.
    Returns new y after drawing.
    """
    if not text:
        return y

    # compute available vertical space (y down to min_y)
    available_height = y - min_y
    if available_height <= 0:
        return min_y

    # compute max lines that can fit (floor)
    max_lines = max(0, floor(available_height / leading))

    if max_lines == 0:
        return min_y

    used_size, lines = fit_and_wrap_lines(text, font_name, font_size, max_width, max_lines, leading, min_font_size=min_font_size)

    c.setFont(font_name, used_size)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * leading, line)

    return y - (len(lines) * leading)

@app.get("/orders")
def get_orders():
    try:
        res = supabase.table("orders_ch2025").select("*").order("created_at", desc=True).execute()

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


# -------------------------
# generate_bulk_labels (A6 two-per-page) using supabase
# -------------------------
def generate_bulk_labels(order_ids):
    """
    Generates a PDF with two half-width labels per A6 page (left and right).
    Fetches order rows from Supabase in one call.
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

    # Fetch rows from Supabase once and preserve order
    orders = _fetch_orders_by_ids(order_ids)

    # Iterate in steps of 2 to place two per page, but using ordered list
    i = 0
    n = len(orders)
    while i < n:
        left_row = orders[i]
        if left_row:
            x_left = margin
            y_top = height - margin
            draw_label_block(c, left_row, x_left, y_top, slot_width, slot_height)

        if i + 1 < n:
            right_row = orders[i + 1]
            if right_row:
                x_right = margin + slot_width + gutter
                y_top = height - margin
                draw_label_block(c, right_row, x_right, y_top, slot_width, slot_height)

        # divider between slots
        divider_x = margin + slot_width + (gutter / 2.0)
        c.setDash(3, 3)
        c.line(divider_x, margin, divider_x, height - margin)
        c.setDash()

        c.showPage()
        i += 2

    c.save()
    return pdf_path

# -------------------------
# generate_bulk_labels_a4 (A4 landscape 6-per-page) using supabase
# -------------------------
def generate_bulk_labels_a4(order_ids, sort_by_name=False):
    """
    A4 landscape, 3 columns x 2 rows = 6 labels per page.
    Uses Supabase to fetch orders and preserves input ordering,
    unless sort_by_name is set, in which case labels are ordered A–Z by recipient name.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_az" if sort_by_name else ""
    pdf_path = os.path.join(LABEL_FOLDER, f"labels_bulk_a4{suffix}_{ts}.pdf")

    # A4 landscape
    page_width, page_height = landscape(A4)

    # layout grid
    cols, rows = 3, 2

    # outer margin
    margin = 10 * mm

    usable_width = page_width - 2 * margin
    usable_height = page_height - 2 * margin

    slot_width = usable_width / cols
    slot_height = usable_height / rows

    c = canvas.Canvas(pdf_path, pagesize=(page_width, page_height))

    orders = _fetch_orders_by_ids(order_ids)
    if sort_by_name:
        orders.sort(key=lambda o: ((o.get("name") or "").strip().casefold(), int(o.get("id") or 0)))

    for idx, order in enumerate(orders):
        index_in_page = idx % (cols * rows)
        col = index_in_page % cols
        row_idx = index_in_page // cols  # 0 = top row
        x_left = margin + col * slot_width
        y_top = page_height - margin - (row_idx * slot_height)

        # border
        c.setLineWidth(0.6)
        c.rect(x_left, y_top - slot_height, slot_width, slot_height)

        draw_label_block(c, order, x_left, y_top, slot_width, slot_height)

        if index_in_page == (cols * rows - 1):
            c.showPage()

    if len(order_ids) % (cols * rows) != 0:
        c.showPage()

    c.save()
    return pdf_path

@app.get("/orders/{order_id}/label")
def get_order_label(order_id: int):
    try:
        r = supabase.table("orders_ch2025").select("*").eq("id", order_id).execute()
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

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    # auth
    if not request.session.get("admin"):
        return RedirectResponse(url="/admin/login", status_code=302)

    try:
        # def safe_count_and_sum(status_val=None):
        #     try:
        #         query = supabase.table("orders_ch2025")
        #         if status_val:
        #             query = query.select("id, quantity").eq("status", status_val)
        #         else:
        #             query = query.select("id, quantity")
        #         res = query.execute()
        #         data, err = _unpack_supabase_response(res)
        #         if err:
        #             logger.warning("Count query returned error for status=%s: %s", status_val, err)
        #             return 0, 0
        #         rows = data or []
        #         cnt = len(rows)
        #         qty = sum((int(r.get("quantity") or 0) for r in rows))
        #         return cnt, qty
        #     except Exception as e:
        #         logger.exception("safe_count_and_sum failed for status=%s: %s", status_val, e)
        #         return 0, 0

        def safe_count_and_sum(status_val=None):
            """
            Count rows and sum quantities robustly by iterating in chunks.
            """
            try:
                cnt = 0
                qty = 0
                for chunk in _iter_orders_chunks(select_cols="id,quantity,status", chunk_size=1000, status_filter=status_val):
                    for r in chunk:
                        cnt += 1
                        try:
                            qty += int(r.get("quantity") or 0)
                        except Exception:
                            pass
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
            res_orders = supabase.table("orders_ch2025").select("*").eq("status", "pending").order("created_at", desc=True).limit(5000).execute()
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
# def admin_list_orders(request: Request, status: str = "pending", q: str = "", page: int = 1, page_size: int = 20):
#     require_admin(request)

#     offset = max(0, (page - 1) * page_size)
#     start = offset
#     end = offset + page_size - 1

#     try:
#         # Build query
#         query = supabase.table("orders_ch2025").select("*")
#         if status:
#             query = query.eq("status", status)

#         # Apply ordering & pagination (range uses start/end inclusive)
#         # res = query.order("id", desc=True).range(start, end).execute()
#         res = query.order("id", desc=True).execute()

#         rows, err = _unpack_supabase_response(res)
#         if err:
#             logger.error("Supabase query error (list): %s", err)
#             raise HTTPException(status_code=500, detail=f"Query failed: {err}")

#         rows = rows or []

#         # If q provided and client doesn't support ilike, do basic client-side filter
#         if q:
#             q_lower = q.lower()
#             def matches(r):
#                 return (
#                     (r.get("phone") and q_lower in str(r.get("phone")).lower()) or
#                     (r.get("name") and q_lower in str(r.get("name")).lower())
#                 )
#             rows = [r for r in rows if matches(r)]

#         # Count total matching rows (simple approach)
#         try:
#             count_query = supabase.table("orders_ch2025").select("id")
#             if status:
#                 count_query = count_query.eq("status", status)
#             count_res = count_query.execute()
#             count_data, count_err = _unpack_supabase_response(count_res)
#             if count_err:
#                 logger.warning("Count query returned unexpected shape/error, falling back to page length: %s", count_err)
#                 total = len(rows)
#             else:
#                 total = len(count_data or [])
#         except Exception as ce:
#             logger.warning("Count query failed; using page length fallback: %s", ce)
#             total = len(rows)

#         # Normalize rows and convert created_at to datetime when possible
#         normalized = []
#         for r in rows:
#             try:
#                 od = dict(r)
#                 if "created_at" in od and od["created_at"]:
#                     od["created_at"] = _parse_iso_datetime(od["created_at"])
#                 normalized.append(od)
#             except Exception as e:
#                 logger.warning("Row normalization failed: %s. Row repr: %s", e, repr(r)[:300])
#                 try:
#                     normalized.append(dict(r))
#                 except Exception:
#                     normalized.append(r)

#         return templates.TemplateResponse(
#             "admin_orders_filtered.html",
#             {
#                 "request": request,
#                 "orders": [dict(r) for r in normalized],
#                 "total": total,
#                 "page": page,
#                 "page_size": page_size,
#                 "status": status,
#                 "q": q
#             }
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception("Unhandled error in admin_list_orders: %s", e)
#         raise HTTPException(status_code=500, detail=f"Query failed: {e}")
def admin_list_orders(request: Request, status: str = "pending", q: str = "", page: int = 1, page_size: int = 20):
    require_admin(request)

    offset = max(0, (page - 1) * page_size)
    start = offset
    end = offset + page_size - 1

    try:
        # Build base query
        base_query = supabase.table("orders_ch2025").select("*")
        if status:
            base_query = base_query.eq("status", status)

        # If the client supplied a search q, we preserve your previous behaviour:
        # fetch all rows (chunked), filter client-side, then paginate.
        if q:
            q_lower = q.lower()
            all_rows = []
            for chunk in _iter_orders_chunks(select_cols="*", chunk_size=1000, order_desc=True, status_filter=status):
                all_rows.extend(chunk)

            def matches(r):
                return (
                    (r.get("phone") and q_lower in str(r.get("phone")).lower()) or
                    (r.get("name") and q_lower in str(r.get("name")).lower())
                )

            filtered = [r for r in all_rows if matches(r)]
            total = len(filtered)
            page_rows = filtered[offset: offset + page_size]

            rows = page_rows
        else:
            # Normal server-side pagination (use .range to fetch exactly the page)
            try:
                res = base_query.order("id", desc=True).range(start, end).execute()
                rows, err = _unpack_supabase_response(res)
                if err:
                    logger.error("Supabase query error (list): %s", err)
                    raise HTTPException(status_code=500, detail=f"Query failed: {err}")
                rows = rows or []
            except Exception as e:
                logger.exception("Failed fetching page via range: %s", e)
                # fallback: fetch everything chunked then slice (less efficient)
                all_rows = []
                for chunk in _iter_orders_chunks(select_cols="*", chunk_size=1000, order_desc=True, status_filter=status):
                    all_rows.extend(chunk)
                rows = all_rows[offset: offset + page_size]

            # compute total via chunked counting (robust)
            total = _count_rows(status=status if status else None)

        # Normalize rows and convert created_at to datetime when possible
        normalized = []
        for r in rows:
            try:
                od = dict(r)
                if "created_at" in od and od["created_at"]:
                    od["created_at"] = _parse_iso_datetime(od["created_at"])
                normalized.append(od)
            except Exception as e:
                logger.warning("Row normalization failed: %s. Row repr: %s", e, repr(r)[:300])
                try:
                    normalized.append(dict(r))
                except Exception:
                    normalized.append(r)

        return templates.TemplateResponse(
            "admin_orders_filtered.html",
            {
                "request": request,
                "orders": [dict(r) for r in normalized],
                "total": total,
                "page": page,
                "page_size": page_size,
                "status": status,
                "q": q
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in admin_list_orders: %s", e)
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


# -------------------------
# get_status_counts via Supabase
# -------------------------
# def get_status_counts():
#     """
#     Returns dict with counts per status and overall.
#     Uses Supabase select + client-side counting (robust across client versions).
#     """
#     try:
#         # fetch all orders' id and quantity (could be heavy if many rows; consider aggregate/sql if table grows)
#         res_all = supabase.table("orders_ch2025").select("id, quantity, status").execute()
#         data_all, err_all = _unpack_supabase_response(res_all)
#         if err_all:
#             logger.warning("get_status_counts: supabase select returned error: %s", err_all)
#             # fallback zeros
#             return {"pending": 0, "shipped": 0, "cancelled": 0, "all": 0}

#         rows = data_all or []
#         counts = {"pending": 0, "shipped": 0, "cancelled": 0}
#         total = 0
#         for r in rows:
#             total += 1
#             st = (r.get("status") or "").lower()
#             if st in counts:
#                 counts[st] += 1

#         counts["all"] = total
#         return counts
#     except Exception as e:
#         logger.exception("get_status_counts failed: %s", e)
#         return {"pending": 0, "shipped": 0, "cancelled": 0, "all": 0}

def get_status_counts():
    """
    Returns dict with counts per status and overall.
    Iterates over the table in chunks so it isn't limited by 1k-row responses.
    """
    try:
        counts = {"pending": 0, "shipped": 0, "cancelled": 0}
        total = 0
        for chunk in _iter_orders_chunks(select_cols="id,quantity,status", chunk_size=1000):
            for r in chunk:
                total += 1
                st = (r.get("status") or "").lower()
                if st in counts:
                    counts[st] += 1
        counts["all"] = total
        return counts
    except Exception as e:
        logger.exception("get_status_counts failed: %s", e)
        return {"pending": 0, "shipped": 0, "cancelled": 0, "all": 0}

# ---- Update status ----

# -------------------------
# admin_update_status -> supabase
# -------------------------
@app.post("/admin/orders/{order_id}/status")
def admin_update_status(order_id: int, request: Request, status: str = Form(...)):
    require_admin(request)
    if status not in ("pending", "shipped", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    try:
        res = supabase.table("orders_ch2025").update({"status": status}).eq("id", order_id).execute()
        data, err = _unpack_supabase_response(res)
        if err:
            logger.error("admin_update_status supabase error: %s", err)
            raise HTTPException(status_code=500, detail=f"Update failed: {err}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_update_status exception: %s", e)
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    return {"ok": True}


# Optional: quick health ping
@app.get("/admin/ping")
def admin_ping():
    return {"ok": True}

# -------------------------
# admin_bulk_action -> supabase
# -------------------------
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

    # operate using Supabase
    try:
        if action == "mark_shipped":
            res = supabase.table("orders_ch2025").update({"status": "shipped"}).in_("id", order_ids).execute()
            data, err = _unpack_supabase_response(res)
            if err:
                logger.error("bulk mark_shipped error: %s", err)
            return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

        elif action == "cancel":
            res = supabase.table("orders_ch2025").update({"status": "cancelled"}).in_("id", order_ids).execute()
            data, err = _unpack_supabase_response(res)
            if err:
                logger.error("bulk cancel error: %s", err)
            return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

        elif action in ("generate_labels", "generate_labels_alpha"):
            pdf_path = generate_bulk_labels_a4(
                order_ids,
                sort_by_name=(action == "generate_labels_alpha"),
            )
            return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))

    except Exception as e:
        logger.exception("admin_bulk_action failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Bulk action failed: {e}")

    return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

# -------------------------
# admin_cancel_single -> supabase
# -------------------------
@app.post("/admin/orders/{order_id}/cancel")
def admin_cancel_single(request: Request, order_id: int):
    if not is_logged_in(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    try:
        res = supabase.table("orders_ch2025").update({"status": "cancelled"}).eq("id", order_id).execute()
        data, err = _unpack_supabase_response(res)
        if err:
            logger.error("admin_cancel_single error: %s", err)
            raise HTTPException(status_code=500, detail=f"Cancel failed: {err}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_cancel_single exception: %s", e)
        raise HTTPException(status_code=500, detail=f"Cancel failed: {e}")
    return RedirectResponse(url="/admin/orders?status=pending", status_code=303)

@app.get("/admin/orders/{order_id}/label")
def admin_single_label(request: Request, order_id: int):
    if not is_logged_in(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return get_order_label(order_id)

def _pick_latest_file(files):
    """
    From a list of file entries from Supabase storage list(), return the file name
    with the latest timestamp. Uses created_at/updated_at if present, else sorts by
    name (uploaded filenames use YYYYMMDDHHMMSS_* so lexicographic sort = newest last).
    """
    if not files:
        return None
    # Normalize: ensure we have a list of dict-like items with at least "name"
    items = []
    for f in files:
        if isinstance(f, dict):
            name = f.get("name")
        else:
            name = getattr(f, "name", None)
        if not name:
            continue
        created = None
        if isinstance(f, dict):
            created = f.get("created_at") or f.get("updated_at") or f.get("createdAt") or f.get("updatedAt")
        else:
            created = getattr(f, "created_at", None) or getattr(f, "updated_at", None)
        items.append({"name": name, "created": created})
    if not items:
        return None
    # Prefer sorting by created_at/updated_at if available
    with_ts = [x for x in items if x["created"] is not None]
    if with_ts:
        def parse_ts(t):
            if t is None:
                return None
            if isinstance(t, (int, float)):
                return t
            s = str(t)
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None
        with_ts.sort(key=lambda x: parse_ts(x["created"]) or 0, reverse=True)
        return with_ts[0]["name"]
    # Fallback: sort by name; uploads use YYYYMMDDHHMMSS_originalname so latest has largest name
    items.sort(key=lambda x: x["name"], reverse=True)
    return items[0]["name"]


@app.get("/admin/orders/{order_id}/screenshot")
async def get_order_screenshot(order_id: str):
    try:
        # list files in /uploads/{order_id}
        files = supabase.storage.from_(BUCKET).list(f"uploads/{order_id}")
        if not files:
            raise HTTPException(status_code=404, detail="Payment screenshot not found")

        # Unwrap if Supabase returns {"name": "...", "id": "...", "metadata": {"..."}} or list of such
        if isinstance(files, dict) and "id" not in files:
            file_list = files if isinstance(files, list) else list(files.values()) if isinstance(files, dict) else []
        else:
            file_list = files if isinstance(files, list) else [files]

        file_name = _pick_latest_file(file_list)
        if not file_name:
            raise HTTPException(status_code=404, detail="Payment screenshot not found")

        file_path = f"uploads/{order_id}/{file_name}"

        # generate signed URL valid for 1 hour
        signed_url = supabase.storage.from_(BUCKET).create_signed_url(file_path, 3600)

        return {"url": signed_url["signedURL"]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/_supabase_dbg")
def _supabase_dbg():
    res = supabase.table("orders_ch2025").select("*").limit(1).execute()
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

# ---------- New helper: fetch export rows ----------
def _fetch_export_rows(start_id=None, end_id=None):
    """
    Return list of dict rows where status in ('pending','shipped') and id between start_id and end_id (inclusive)
    if provided. Each row: {'id': ..., 'name': ..., 'city': ..., 'quantity': ...}
    """
    try:
        q = supabase.table("orders_ch2025").select("id, name, city, status, quantity")

        # Only pending or shipped (try server-side .in_ if available)
        try:
            q = q.in_("status", ["pending", "shipped"])
        except Exception:
            # client may not support in_ - we'll filter later
            pass

        # Apply start_id / end_id filters server-side if supported
        if start_id not in (None, "",):
            try:
                q = q.gte("id", int(start_id))
            except Exception:
                pass

        if end_id not in (None, "",):
            try:
                q = q.lte("id", int(end_id))
            except Exception:
                pass

        # ordering by id ascending
        res = q.order("id", desc=False).execute()
        data, err = _unpack_supabase_response(res)
        if err:
            logger.error("Export fetch error: %s", err)
            raise RuntimeError(err)
        rows = data or []

        # final safety filtering for client versions without in_/gte/lte
        filtered = []
        for r in rows:
            try:
                st = (r.get("status") or "").lower()
                oid = int(r.get("id"))
            except Exception:
                continue
            if st not in ("pending", "shipped"):
                continue
            if start_id not in (None, ""):
                try:
                    if oid < int(start_id):
                        continue
                except Exception:
                    pass
            if end_id not in (None, ""):
                try:
                    if oid > int(end_id):
                        continue
                except Exception:
                    pass
            # ensure quantity present (int fallback 0)
            try:
                qty = int(r.get("quantity") or 0)
            except Exception:
                qty = 0
            filtered.append({"id": oid, "name": r.get("name") or "", "city": r.get("city") or "", "quantity": qty})
        return filtered
    except Exception as e:
        logger.exception("Failed to fetch export rows: %s", e)
        raise

# ---------- New endpoint: export orders ----------
@app.post("/admin/export-orders")
@app.post("/admin/export-orders")
def admin_export_orders(request: Request, start_id: str = Form(None), end_id: str = Form(None), fmt: str = Form("pdf"), sort: str = Form("id")):
    """
    Admin-only endpoint that creates a PDF or XLSX of orders with columns:
      S.No (order.id), Name, City, Quantity, Dispatched (blank), Received (blank)

    Form params:
      start_id (optional): if set, only orders with id >= start_id are exported
      end_id (optional): if set, only orders with id <= end_id are exported
      fmt: 'pdf' or 'xlsx'
      sort: 'id' (default, by S.No) or 'name' (A–Z by recipient name)
    """
    require_admin(request)

    fmt = (fmt or "pdf").lower()
    if fmt not in ("pdf", "xlsx"):
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'pdf' or 'xlsx'.")

    sort_key = (sort or "id").lower()
    if sort_key not in ("id", "name"):
        sort_key = "id"

    # Normalize empty strings to None
    if start_id in ("", None):
        start_val = None
    else:
        start_val = start_id

    if end_id in ("", None):
        end_val = None
    else:
        end_val = end_id

    try:
        rows = _fetch_export_rows(start_id=start_val, end_id=end_val)
        if sort_key == "name":
            rows.sort(key=lambda r: ((r.get("name") or "").strip().casefold(), int(r.get("id") or 0)))

        # Build table data: headers + rows (added Quantity column)
        table_data = []
        headers = ["S.No", "Name", "City", "Quantity", "Dispatched", "Received"]
        table_data.append(headers)
        for r in rows:
            table_data.append([r["id"], r["name"], r["city"], r.get("quantity", 0), "", ""])

        # Temporary file path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "pdf":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_orders_{ts}.pdf")
            tmp.close()
            pdf_path = tmp.name

            # Create PDF with ReportLab Table and bordered style
            doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
            story = []
            styles = getSampleStyleSheet()
            range_desc = ""
            if start_val and end_val:
                range_desc = f" — id between {start_val} and {end_val}"
            elif start_val:
                range_desc = f" — starting id >= {start_val}"
            elif end_val:
                range_desc = f" — up to id <= {end_val}"
            if sort_key == "name":
                range_desc += " — sorted by name (A–Z)"
            title = Paragraph(f"Orders Export (status: pending/shipped){range_desc}", styles["Heading2"])
            story.append(title)
            story.append(Spacer(1, 6))

            # Column width heuristics: S.No narrow, Name wider, City medium, Quantity narrow, Dispatched/Received narrow
            page_w, _ = A4
            usable_w = page_w - (18 * mm + 18 * mm)
            col_widths = [22 * mm, usable_w * 0.40, usable_w * 0.22, 18 * mm, usable_w * 0.10, usable_w * 0.10]

            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            t_style = TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),  # S.No center
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ])
            t.setStyle(t_style)

            story.append(t)
            doc.build(story)
            suffix = "_az" if sort_key == "name" else ""
            filename = f"orders{suffix}_{ts}.pdf"
            return FileResponse(pdf_path, media_type="application/pdf", filename=filename)

        else:  # fmt == xlsx
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_orders_{ts}.xlsx")
            tmp.close()
            xlsx_path = tmp.name

            wb = Workbook()
            ws = wb.active
            ws.title = "Orders"

            # write header
            header_font = Font(bold=True)
            thin = Side(border_style="thin", color="000000")
            border = Border(left=thin, right=thin, top=thin, bottom=thin)
            align = Alignment(vertical="center", wrap_text=True)

            for col_idx, h in enumerate(headers, start=1):
                cell = ws.cell(row=1, column=col_idx, value=h)
                cell.font = header_font
                cell.border = border
                cell.alignment = align

            # write rows
            for row_idx, r in enumerate(rows, start=2):
                ws.cell(row=row_idx, column=1, value=r["id"]).border = border
                ws.cell(row=row_idx, column=2, value=r["name"]).border = border
                ws.cell(row=row_idx, column=3, value=r["city"]).border = border
                ws.cell(row=row_idx, column=4, value=r.get("quantity", 0)).border = border
                ws.cell(row=row_idx, column=5, value="").border = border
                ws.cell(row=row_idx, column=6, value="").border = border

            # column widths (approx)
            ws.column_dimensions["A"].width = 8   # S.No
            ws.column_dimensions["B"].width = 35  # Name
            ws.column_dimensions["C"].width = 20  # City
            ws.column_dimensions["D"].width = 10  # Quantity
            ws.column_dimensions["E"].width = 12  # Dispatched
            ws.column_dimensions["F"].width = 12  # Received

            wb.save(xlsx_path)
            suffix = "_az" if sort_key == "name" else ""
            filename = f"orders{suffix}_{ts}.xlsx"
            return FileResponse(xlsx_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Export failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

@app.get("/admin/export", response_class=HTMLResponse)
def admin_export_page(request: Request):
    require_admin(request)
    return templates.TemplateResponse("admin_export.html", {"request": request})

# @app.get("/admin/summary", response_class=HTMLResponse)
# def admin_summary(request: Request):
#     """
#     Show summary: for each quantity value, how many orders exist with that quantity.
#     Equivalent SQL: SELECT quantity, count(id) FROM orders GROUP BY quantity ORDER BY quantity ASC
#     Implemented by fetching minimal columns and aggregating in Python for compatibility.
#     """
#     require_admin(request)
#     try:
#         # Fetch only quantity and id (lightweight)
#         res = supabase.table("orders_ch2025").select("quantity, id").execute()
#         rows, err = _unpack_supabase_response(res)
#         if err:
#             logger.error("Failed to fetch orders for summary: %s", err)
#             raise HTTPException(status_code=500, detail=f"Failed to fetch data: {err}")

#         rows = rows or []

#         # Aggregate counts by quantity (safe parsing to int)
#         counts = {}
#         for r in rows:
#             try:
#                 qty = int(r.get("quantity") or 0)
#             except Exception:
#                 # skip malformed quantity
#                 continue
#             counts[qty] = counts.get(qty, 0) + 1

#         # Convert to sorted list of dicts for template
#         summary = [{"quantity": q, "count": counts[q]} for q in sorted(counts.keys())]

#         # Also compute totals (optional)
#         total_orders = sum(item["count"] for item in summary)
#         total_items = sum(item["quantity"] * item["count"] for item in summary)

#         return templates.TemplateResponse("admin_summary.html", {
#             "request": request,
#             "summary": summary,
#             "total_orders": total_orders,
#             "total_items": total_items
#         })

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception("Unhandled error in admin_summary: %s", e)
#         raise HTTPException(status_code=500, detail=f"Failed to load summary: {e}")

@app.get("/admin/summary", response_class=HTMLResponse)
# def admin_summary(request: Request):
#     """
#     Show summary: for each quantity value, how many orders exist with that quantity,
#     separated into pending, shipped, and total tables. Also include comma-separated
#     order ids for groups where quantity > 1 AND count > 1.
#     """
#     require_admin(request)
#     try:
#         # Fetch quantity, id and status (lightweight)
#         res = supabase.table("orders_ch2025").select("quantity, id, status").execute()
#         rows, err = _unpack_supabase_response(res)
#         if err:
#             logger.error("Failed to fetch orders for summary: %s", err)
#             raise HTTPException(status_code=500, detail=f"Failed to fetch data: {err}")

#         rows = rows or []

#         def new_counter():
#             return {"count": 0, "ids": []}

#         counts_pending = {}
#         counts_shipped = {}
#         counts_total = {}

#         for r in rows:
#             # parse quantity safely to int; if malformed, skip
#             try:
#                 qty = int(r.get("quantity") or 0)
#             except Exception:
#                 continue

#             oid = r.get("id")
#             oid_str = str(oid) if oid is not None else None
#             status = (r.get("status") or "").lower().strip()

#             def add_to(counts_dict):
#                 if qty not in counts_dict:
#                     counts_dict[qty] = new_counter()
#                 counts_dict[qty]["count"] += 1
#                 if oid_str:
#                     counts_dict[qty]["ids"].append(oid_str)

#             add_to(counts_total)

#             if status == "pending":
#                 add_to(counts_pending)
#             elif status == "shipped":
#                 add_to(counts_shipped)

#         # 🔑 UPDATED FUNCTION
#         def make_summary_list(counts_dict):
#             out = []
#             for q in sorted(counts_dict.keys()):
#                 entry = counts_dict[q]
#                 ids_str = ""
#                 # Only include ids if BOTH quantity > 1 and count > 1
#                 if q > 1  and entry["ids"]:
#                     seen = set()
#                     unique_ids = []
#                     for i in entry["ids"]:
#                         if i not in seen:
#                             seen.add(i)
#                             unique_ids.append(i)
#                     ids_str = ",".join(unique_ids)
#                 out.append({"quantity": q, "count": entry["count"], "ids": ids_str})
#             return out

#         pending_summary = make_summary_list(counts_pending)
#         shipped_summary = make_summary_list(counts_shipped)
#         total_summary = make_summary_list(counts_total)

#         def compute_totals(summary_list):
#             total_orders = sum(item["count"] for item in summary_list)
#             total_items = sum(item["quantity"] * item["count"] for item in summary_list)
#             return total_orders, total_items

#         pending_total_orders, pending_total_items = compute_totals(pending_summary)
#         shipped_total_orders, shipped_total_items = compute_totals(shipped_summary)
#         total_total_orders, total_total_items = compute_totals(total_summary)

#         return templates.TemplateResponse("admin_summary.html", {
#             "request": request,
#             "pending_summary": pending_summary,
#             "pending_total_orders": pending_total_orders,
#             "pending_total_items": pending_total_items,
#             "shipped_summary": shipped_summary,
#             "shipped_total_orders": shipped_total_orders,
#             "shipped_total_items": shipped_total_items,
#             "total_summary": total_summary,
#             "total_total_orders": total_total_orders,
#             "total_total_items": total_total_items,
#         })

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception("Unhandled error in admin_summary: %s", e)
#         raise HTTPException(status_code=500, detail=f"Failed to load summary: {e}")

def admin_summary(request: Request):
    """
    Show summary: for each quantity value, how many orders exist with that quantity,
    separated into pending, shipped, and total tables. Also include comma-separated
    order ids for groups where quantity > 1 AND count > 1.
    This implementation iterates in chunks to avoid Supabase/PostgREST 1000-row limits.
    """
    require_admin(request)
    try:
        # iterate chunks and aggregate counts (robust for large tables)
        def new_counter():
            return {"count": 0, "ids": []}

        counts_pending = {}
        counts_shipped = {}
        counts_total = {}

        for chunk in _iter_orders_chunks(select_cols="quantity,id,status", chunk_size=1000, order_desc=False):
            for r in chunk:
                # parse quantity safely to int; if malformed, skip
                try:
                    qty = int(r.get("quantity") or 0)
                except Exception:
                    continue

                oid = r.get("id")
                oid_str = str(oid) if oid is not None else None
                status = (r.get("status") or "").lower().strip()

                def add_to(counts_dict):
                    if qty not in counts_dict:
                        counts_dict[qty] = new_counter()
                    counts_dict[qty]["count"] += 1
                    if oid_str:
                        counts_dict[qty]["ids"].append(oid_str)

                add_to(counts_total)
                if status == "pending":
                    add_to(counts_pending)
                elif status == "shipped":
                    add_to(counts_shipped)

        def make_summary_list(counts_dict):
            out = []
            for q in sorted(counts_dict.keys()):
                entry = counts_dict[q]
                ids_str = ""
                # Only include ids if BOTH quantity > 1 and count > 1
                if q > 1 and entry["ids"]:
                    seen = set()
                    unique_ids = []
                    for i in entry["ids"]:
                        if i not in seen:
                            seen.add(i)
                            unique_ids.append(i)
                    ids_str = ",".join(unique_ids)
                out.append({"quantity": q, "count": entry["count"], "ids": ids_str})
            return out

        pending_summary = make_summary_list(counts_pending)
        shipped_summary = make_summary_list(counts_shipped)
        total_summary = make_summary_list(counts_total)

        def compute_totals(summary_list):
            total_orders = sum(item["count"] for item in summary_list)
            total_items = sum(item["quantity"] * item["count"] for item in summary_list)
            return total_orders, total_items

        pending_total_orders, pending_total_items = compute_totals(pending_summary)
        shipped_total_orders, shipped_total_items = compute_totals(shipped_summary)
        total_total_orders, total_total_items = compute_totals(total_summary)

        return templates.TemplateResponse("admin_summary.html", {
            "request": request,
            "pending_summary": pending_summary,
            "pending_total_orders": pending_total_orders,
            "pending_total_items": pending_total_items,
            "shipped_summary": shipped_summary,
            "shipped_total_orders": shipped_total_orders,
            "shipped_total_items": shipped_total_items,
            "total_summary": total_summary,
            "total_total_orders": total_total_orders,
            "total_total_items": total_total_items,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in admin_summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load summary: {e}")


@app.get("/admin/duplicates", response_class=HTMLResponse)
def admin_duplicates(request: Request, limit: int = Query(None, description="Optional limit of rows to display")):
    """
    Show duplicate orders using the database view `orders_duplicates`.
    The view should return all order rows whose addressline1 appears more than once.
    Groups are returned keyed by normalized addressline1, with `display_address` and list of rows.
    """
    require_admin(request)
    try:
        # Query the view which returns only duplicate rows (server-side)
        res = supabase.table("orders_duplicates").select("*").order("addressline1").execute()
        rows, err = _unpack_supabase_response(res)
        if err:
            logger.error("Failed to fetch duplicate rows from view orders_duplicates: %s", err)
            raise HTTPException(status_code=500, detail=f"Failed to fetch data: {err}")

        rows = rows or []

        # Group rows by normalized addressline1 (normalize by trim + lower)
        groups = {}
        for r in rows:
            addr = (r.get("addressline1") or "").strip()
            if not addr:
                # place empty addresses under a special key if you want; skip for now
                key = "__EMPTY__"
            else:
                key = addr.lower()
            # Use the first-seen original address for display
            if key not in groups:
                groups[key] = {"display_address": addr or "(blank)", "rows": []}
            groups[key]["rows"].append(r)

        total_rows = sum(len(g["rows"]) for g in groups.values())

        # Apply optional limit: trim rows across groups (simple per-group trim until limit exhausted)
        if limit is not None and limit > 0:
            remaining = limit
            for key in list(groups.keys()):
                if remaining <= 0:
                    groups[key]["rows"] = []
                else:
                    if len(groups[key]["rows"]) > remaining:
                        groups[key]["rows"] = groups[key]["rows"][:remaining]
                    remaining -= len(groups[key]["rows"])

        return templates.TemplateResponse("duplicates.html", {
            "request": request,
            "groups": groups,
            "total_dup_addresses": len([k for k in groups.keys() if groups[k]["rows"]]),  # count groups with at least 1 row
            "total_rows": total_rows,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in admin_duplicates: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load duplicates: {e}")

@app.get("/admin/group", response_class=HTMLResponse)
def admin_group_page(request: Request, start_id: str = None, end_id: str = None, group_by: str = "quantity"):
    """
    Defensive grouping endpoint. Uses 'rows' key (not 'items') to avoid colliding with dict.items method.
    """
    require_admin(request)

    group_by = (group_by or "quantity").lower()
    if group_by not in ("quantity", "city"):
        group_by = "quantity"

    debug_note = None

    try:
        # find helper
        helper = globals().get("_fetch_export_rows")
        if helper is None:
            logger.error("_fetch_export_rows not found in globals()")
            debug_note = "_fetch_export_rows not found"
            rows = []
        elif not callable(helper):
            logger.error("_fetch_export_rows exists but is not callable. type=%s repr=%s", type(helper), repr(helper)[:400])
            debug_note = f"_fetch_export_rows exists but is not callable (type={type(helper).__name__})"
            try:
                rows = list(helper)
            except Exception:
                rows = []
        else:
            try:
                rows = helper(start_id=start_id if start_id not in ("", None) else None,
                              end_id=end_id if end_id not in ("", None) else None)
            except TypeError:
                # fallback to positional if signature differs
                try:
                    rows = helper(start_id, end_id)
                except Exception as e:
                    logger.exception("Calling _fetch_export_rows failed: %s", e)
                    rows = []
            except Exception as e:
                logger.exception("Calling _fetch_export_rows failed: %s", e)
                rows = []

        # defensive normalization
        if callable(rows):
            try:
                rows = rows()
            except Exception:
                debug_note = "Returned callable could not be invoked; coerced to empty list."
                rows = []

        if rows is None:
            rows = []

        if isinstance(rows, dict):
            rows = [rows]

        if not isinstance(rows, (list, tuple)):
            try:
                rows = list(rows)
            except Exception:
                logger.warning("Unable to coerce rows to list; type=%s repr=%s", type(rows), repr(rows)[:400])
                debug_note = f"Unexpected rows type: {type(rows).__name__}; coerced to empty list."
                rows = []

        # Build groups using "rows" key (avoid name collision with dict.items)
        groups = {}
        for r in rows:
            try:
                get = r.get if isinstance(r, dict) else lambda k, d=None: getattr(r, k, d)
                raw_id = get("id", None)
                try:
                    oid = int(raw_id) if raw_id is not None else None
                except Exception:
                    oid = raw_id

                if group_by == "city":
                    key_raw = get("city", "(blank)") or "(blank)"
                    key = key_raw.strip() if isinstance(key_raw, str) else str(key_raw)
                else:
                    qv = get("quantity", 0)
                    try:
                        key = int(qv)
                    except Exception:
                        try:
                            key = int(str(qv).strip())
                        except Exception:
                            key = 0

                key_display = str(key)
                if key_display not in groups:
                    groups[key_display] = {"key": key_display, "rows": []}

                groups[key_display]["rows"].append({
                    "id": oid if oid is not None else raw_id,
                    "name": get("name", "") or "",
                    "quantity": get("quantity", 0) or 0
                })
            except Exception as e:
                logger.exception("Failed processing row for grouping: %s; row_repr=%s", e, repr(r)[:300])
                # skip bad row

        # sort groups
        if group_by == "quantity":
            sorted_keys = sorted(groups.keys(), key=lambda x: int(x) if str(x).lstrip("-").isdigit() else 0)
        else:
            sorted_keys = sorted(groups.keys(), key=lambda x: (x or "").lower())

        sorted_groups = [groups[k] for k in sorted_keys]
        total_rows = len(rows)

        return templates.TemplateResponse("admin_group.html", {
            "request": request,
            "groups": sorted_groups,
            "start_id": start_id or "",
            "end_id": end_id or "",
            "group_by": group_by,
            "total_rows": total_rows,
            "debug_note": debug_note,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin_group_page failed (unexpected): %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to group orders: {e}")
