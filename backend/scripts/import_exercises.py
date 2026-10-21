"""Import (or update) the exercise library from free-exercise-db.

    cd backend && uv run python -m scripts.import_exercises

free-exercise-db (https://github.com/yuhonas/free-exercise-db) is public domain
(Unlicense): ~870 exercises with start and end images. A fixed version (commit)
is used so imports are repeatable; images are served by the jsDelivr CDN from
that version, so nothing needs storing. Running it again updates the source
fields only: guide text and videos written by the worker are kept.

Uses SUPABASE_SECRET_KEY (backend/.env), because the library is read-only for
everyone else.
"""

import json
import sys
import urllib.request
from typing import Any

from dotenv import dotenv_values

# Pin a version: change this (and re-run) to pick up the database's updates.
COMMIT = "f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5"
DATA_URL = (
    f"https://raw.githubusercontent.com/yuhonas/free-exercise-db/{COMMIT}/dist/exercises.json"
)
IMAGE_BASE = f"https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@{COMMIT}/exercises/"
BATCH = 200


def to_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item["name"].strip(),
        "source": "free-exercise-db",
        "category": item.get("category"),
        "level": item.get("level"),
        "force": item.get("force"),
        "mechanic": item.get("mechanic"),
        "equipment": item.get("equipment"),
        "primary_muscles": item.get("primaryMuscles") or [],
        "secondary_muscles": item.get("secondaryMuscles") or [],
        "instructions": [step.strip() for step in item.get("instructions") or [] if step.strip()],
        "images": [IMAGE_BASE + path for path in item.get("images") or []],
    }


def main() -> None:
    env = dotenv_values(".env")
    url, key = (env.get("SUPABASE_URL") or "").rstrip("/"), env.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_SECRET_KEY must be set in backend/.env")

    with urllib.request.urlopen(DATA_URL, timeout=60) as response:
        rows = [to_row(item) for item in json.load(response)]
    print(f"Downloaded {len(rows)} exercises (free-exercise-db @ {COMMIT[:7]})")

    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        request = urllib.request.Request(
            f"{url}/rest/v1/exercises?on_conflict=id",
            method="POST",
            data=json.dumps(batch).encode(),
            headers={
                "apikey": key,
                "Content-Type": "application/json",
                # Update existing rows' source fields; leave guide and video columns alone.
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        urllib.request.urlopen(request, timeout=60).close()
        print(f"  saved {start + len(batch)}/{len(rows)}")
    print("Done.")


if __name__ == "__main__":
    main()
