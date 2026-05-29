"""Bundled FtM model snapshot and lookup helpers.

The model is loaded from ``model.json`` at import time and re-exported as a
plain dict. Use the helpers for the common membership / inheritance /
deprecation checks; navigate ``model`` directly for anything richer.
"""

from ._lookup import has_schema, is_a, is_deprecated, iter_properties, model

__all__ = ["has_schema", "is_a", "is_deprecated", "iter_properties", "model"]
