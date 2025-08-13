from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

app = FastAPI()

# CORS so frontend can call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your frontend URL in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB init
def init_db():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            contact TEXT,
            product TEXT,
            quantity INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

class Order(BaseModel):
    name: str
    address: str
    contact: str
    product: str
    quantity: int

@app.post("/orders")
def create_order(order: Order):
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders (name, address, contact, product, quantity)
        VALUES (?, ?, ?, ?, ?)
    """, (order.name, order.address, order.contact, order.product, order.quantity))
    conn.commit()
    conn.close()
    return {"message": "Order received successfully"}

@app.get("/orders")
def get_orders():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders")
    rows = cursor.fetchall()
    conn.close()
    return {"orders": rows}
