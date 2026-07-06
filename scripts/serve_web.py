"""Launch the digest web page:  python scripts/serve_web.py  ->  http://localhost:8000/"""
import os
import sys
from pathlib import Path

# src-layout shim (same as scripts/run_digest.py): put src/ on the import path so we
# can `import digest`. PYTHONPATH is also set so uvicorn's reload subprocess (which
# re-imports the app string in a fresh process) can find the package too.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
os.environ["PYTHONPATH"] = str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", "")

import uvicorn  # noqa: E402 (after path setup)

if __name__ == "__main__":
    uvicorn.run("digest.web.app:app", host="127.0.0.1", port=8000, reload=True)
