from __future__ import annotations

from typing import Any

import iso8583
from iso8583.specs import default as iso_default

from iso_checker.svfe_spec import get_svfe_iso_spec

_SPEC = get_svfe_iso_spec()


def decode_iso_message(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (decoded fields as str keys, internal encoded meta)."""
    return iso8583.decode(raw, spec=_SPEC)


def encode_iso_message(fields: dict[str, Any]) -> bytes:
    raw, _enc = iso8583.encode(fields, spec=_SPEC)
    return bytes(raw)


def mti_from_decoded(decoded: dict[str, Any]) -> str:
    t = decoded.get("t", "")
    return str(t)


def fields_present(decoded: dict[str, Any]) -> set[str]:
    """DE field numbers present (string keys), excluding t, p, s, h."""
    skip = frozenset({"t", "p", "h", "s"})
    return {k for k in decoded if k not in skip and k.isdigit()}


# For tests / debugging only
def decode_with_default_spec(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    return iso8583.decode(raw, spec=iso_default)
