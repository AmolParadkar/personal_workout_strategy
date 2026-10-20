"""Write the API description (OpenAPI JSON) to a file, for generating frontend types.

Usage (inside backend/): uv run python -m api.export_openapi openapi.json
"""

import json
import sys
from pathlib import Path

from api.main import app

if __name__ == "__main__":
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    output.write_text(json.dumps(app.openapi(), indent=2) + "\n")
