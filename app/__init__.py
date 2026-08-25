"""StockJarvis app layer on the Vanna kernel."""

from __future__ import annotations

import sys
from pathlib import Path

# Vendored engine lives in vanna/src/vanna. PYTHONPATH=. would otherwise
# bind the name "vanna" to the repo folder (no Agent).
_VANNA_SRC = Path(__file__).resolve().parent.parent / "vanna" / "src"
if _VANNA_SRC.is_dir():
    _src = str(_VANNA_SRC)
    if _src not in sys.path:
        sys.path.insert(0, _src)
