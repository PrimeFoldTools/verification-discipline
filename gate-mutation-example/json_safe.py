"""A JSON encoder that will not quietly turn a fake-boolean into a truthy string.

The bug this exists to prevent (a real one, caught by a pre-commit guard on
2026-08-18): `json.dumps(payload, default=str)` turns numpy.bool_(False) into the
STRING "False", which is truthy. A gate that serializes its own "pass: False"
verdict through default=str reads back as a pass. So default=str is banned here;
non-native scalars are converted to their NATIVE Python type, not stringified.
"""
from __future__ import annotations

import json


def _to_native(obj):
    # numpy scalars (and anything numpy-like) expose .item() -> native python.
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001 - fall through to the hard error below
            pass
    raise TypeError(f"unencodable, and refusing to stringify: {type(obj).__name__}")


def dumps(obj) -> str:
    """json.dumps with a native-preserving fallback. Never default=str."""
    return json.dumps(obj, default=_to_native)
