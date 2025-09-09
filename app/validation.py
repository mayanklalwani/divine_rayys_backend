import re
from fastapi import HTTPException, UploadFile

def validate_order_data(email, phone, name, addressLine1, pincode, city, state, quantity, paymentProof: UploadFile):
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    if not re.match(r"^\d{10}$", phone):
        raise HTTPException(status_code=400, detail="Phone must be exactly 10 digits")
    if not re.match(r"^[A-Za-z\s]{2,50}$", name):
        raise HTTPException(status_code=400, detail="Name should be 2-50 letters only")
    if len(addressLine1.strip()) < 5:
        raise HTTPException(status_code=400, detail="Address must be at least 5 characters")
    if not re.match(r"^[1-9][0-9]{5}$", pincode):
        raise HTTPException(status_code=400, detail="Invalid pincode format")
    if not city.strip() or not state.strip():
        raise HTTPException(status_code=400, detail="City/State cannot be blank")
    if not (1 <= quantity <= 999):
        raise HTTPException(status_code=400, detail="Quantity must be between 1 and 999")
    if not paymentProof:
        raise HTTPException(status_code=400, detail="Payment proof is required")
    if paymentProof.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Payment proof must be under 5MB")
