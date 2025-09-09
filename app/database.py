import psycopg2
import psycopg2.extras
from app.config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

def get_conn():
    return psycopg2.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME
    )

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
