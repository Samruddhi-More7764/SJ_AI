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

# #region agent log
try:
    import json
    import time

    _spec_origin = None
    _spec_locs = None
    try:
        from importlib.util import find_spec

        _sp = find_spec("vanna")
        if _sp is not None:
            _spec_origin = getattr(_sp, "origin", None)
            _spec_locs = list(_sp.submodule_search_locations or [])
    except Exception:
        pass
    with Path("/Users/samruddhimore/Desktop/t-to-sql/.cursor/debug-be79e4.log").open("a") as _f:
        _f.write(
            json.dumps(
                {
                    "sessionId": "be79e4",
                    "runId": "post-fix",
                    "hypothesisId": "A",
                    "location": "app/__init__.py",
                    "message": "sys.path after vanna/src prepend",
                    "data": {
                        "vanna_src": _src if _VANNA_SRC.is_dir() else None,
                        "path0": sys.path[0] if sys.path else None,
                        "spec_origin": _spec_origin,
                        "spec_sublocs": _spec_locs,
                    },
                    "timestamp": int(time.time() * 1000),
                }
            )
            + "\n"
        )
except Exception:
    pass
# #endregion
