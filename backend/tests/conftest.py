import os
from pathlib import Path

from dotenv import dotenv_values

# The app reads its settings from environment variables, which take priority
# over backend/.env. Use the real values from backend/.env when present (the
# integration tests need them) and placeholders otherwise, so unit tests run
# without a .env file. Unit tests replace Supabase with a fake either way.
_env_file = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
_placeholders = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
    "SUPABASE_SECRET_KEY": "sb_secret_test",
}
for name, placeholder in _placeholders.items():
    os.environ.setdefault(name, _env_file.get(name) or placeholder)
