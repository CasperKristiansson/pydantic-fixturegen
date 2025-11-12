from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Polyfactory still calls `update_forward_refs`, which is deprecated on Pydantic v2.
warnings.filterwarnings(
    "ignore",
    message=r"The `update_forward_refs` method is deprecated; use `model_rebuild` instead\..*",
    category=Warning,
)
