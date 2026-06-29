"""Entry point: run `python scripts/hello.py` to see the hello agent work.

Scripts in this folder are things you *run*; the reusable code lives in
``src/digest/``. Because our package sits under ``src/`` (the src layout), we
add that folder to Python's import path before importing ``digest``.

(Later, when we package the project properly with an editable install,
``pip install -e .``, this path shim goes away. For Phase 0 this keeps the
tooling minimal — exactly one new concept at a time.)
"""

import sys
from pathlib import Path

# Project root is the parent of this scripts/ folder; src/ lives next to it.
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from digest.hello_agent import say_hello  # noqa: E402  (import after path setup)


def main() -> None:
    # Windows consoles default to a legacy encoding (cp1252) that can't print
    # emoji or many Unicode characters. Force UTF-8 so Claude's replies always
    # render. (No-op on systems that are already UTF-8.)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("Asking Claude to say hello...\n")
    print(say_hello())


if __name__ == "__main__":
    main()
