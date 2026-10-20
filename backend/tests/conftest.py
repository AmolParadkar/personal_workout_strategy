import os

# Unit tests never talk to the real Supabase; these placeholder values let the
# app start without a backend/.env file. Real environment variables win.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
os.environ.setdefault("SUPABASE_SECRET_KEY", "sb_secret_test")
