from supabase import create_client, Client
import os

# Set your Supabase credentials
SUPABASE_URL = "https://zjgzqudobxmqgulyhgft.supabase.co"   # Replace with your project URL
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpqZ3pxdWRvYnhtcWd1bHloZ2Z0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTM1NzY5NSwiZXhwIjoyMDcwOTMzNjk1fQ.CLfTneOENRa0ccIxz3Na1VqLbREdmj5X7ieaWj3OFWw"          # Replace with your API key

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Define bucket and file details
bucket_name = "childrenshealings2025"   # Replace with your bucket name
local_file_path = "example.txt"  # File you want to upload
storage_file_path = "uploads/example.txt"  # Path inside bucket

# Upload file
with open(local_file_path, "rb") as f:
    res = supabase.storage.from_(bucket_name).upload(storage_file_path, f)

# Check response
print(res)
