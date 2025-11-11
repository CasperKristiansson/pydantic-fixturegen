from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure Polyfactory integrations stay enabled on Python 3.14+ during development tests.
os.environ.setdefault("PFG_POLYFACTORY__ALLOW_PY314", "true")

# Polyfactory still calls `update_forward_refs`, which is deprecated on Pydantic v2.
warnings.filterwarnings(
    "ignore",
    message=r"The `update_forward_refs` method is deprecated; use `model_rebuild` instead\..*",
    category=Warning,
)

# Backfill Pydantic v1-only field symbols so Polyfactory can import under Python 3.14+.
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        import pydantic.fields as _pydantic_fields
        import pydantic.v1.fields as _pydantic_v1_fields
    except Exception:  # pragma: no cover - shim not available
        _pydantic_fields = None
        _pydantic_v1_fields = None

if _pydantic_fields is not None and _pydantic_v1_fields is not None:
    for _symbol in ("DeferredType", "ModelField", "Undefined"):
        if not hasattr(_pydantic_fields, _symbol) and hasattr(_pydantic_v1_fields, _symbol):
            setattr(_pydantic_fields, _symbol, getattr(_pydantic_v1_fields, _symbol))

# Reload discovery so the relaxed Polyfactory gate picks up the injected env var.
try:
    import importlib

    from pydantic_fixturegen.polyfactory_support import discovery as _polyfactory_discovery

    importlib.reload(_polyfactory_discovery)
except Exception:  # pragma: no cover - best-effort; tests will fail if reload is critical
    _polyfactory_discovery = None
else:
    try:
        from polyfactory.factories.pydantic_factory import ModelFactory as _RuntimeModelFactory
    except Exception:
        pass
    else:
        _polyfactory_discovery.POLYFACTORY_MODEL_FACTORY = _RuntimeModelFactory
        _polyfactory_discovery.POLYFACTORY_UNAVAILABLE_REASON = None
