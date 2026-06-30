"""Make `import digest.*` work in tests by putting src/ on the path."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
