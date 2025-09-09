import psycopg2
import psycopg2.extras
import os
import socket
import urllib.parse
from app.config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

# def get_conn():
#     return psycopg2.connect(
#         user=DB_USER,
#         password=DB_PASS,
#         host=DB_HOST,
#         port=DB_PORT,
#         dbname=DB_NAME
#     )

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

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
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
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP
        )
    """)
    conn.commit()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    conn.commit()
    conn.close()
