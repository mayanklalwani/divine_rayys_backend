import os
from supabase import create_client, Client

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zjgzqudobxmqgulyhgft.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your-key-here")
BUCKET = "divinerayysdiwali2025"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Database
DB_USER = os.getenv("user", "postgres")
DB_PASS = os.getenv("password", "DivineRayys@2025")
DB_HOST = os.getenv("host", "db.zjgzqudobxmqgulyhgft.supabase.co")
DB_PORT = os.getenv("port", "5432")
DB_NAME = os.getenv("dbname", "postgres")

# Sessions / Admin
SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "dev-secret-change-me")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
SESSION_COOKIE = "admin_session"
