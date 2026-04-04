from __future__ import annotations

from iso_checker.errors import CheckFailure, ErrorCode
from iso_checker.tlv import parse_lll_tagged_tlv

# Processing code (DE3) first two digits (transaction code) + common SVFE types from spec (subset).
# Full table is in docs; expand as needed.
_PCODE_TO_SVFE: dict[str, str] = {
    "000000": "774",
    "180000": "736",
    "290000": "785",
    "500000": "781",
    "900000": "737",
}


def _de3_key(de3: str) -> str:
    de3 = (de3 or "").zfill(6)[:6]
    return de3


def expected_svfe_type_from_de3(de3: str) -> str | None:
    """Return expected Field 48 tag 002 value, or None if unknown (skip strict check)."""
    k = _de3_key(de3)
    if k in _PCODE_TO_SVFE:
        return _PCODE_TO_SVFE[k]
    # Default: transaction code 00 with goods → 774 common case
    if k.startswith("00"):
        return "774"
    return None


def check_field48_tag002(de3: str, de48: str | None) -> CheckFailure | None:
    if not de48:
        return CheckFailure(
            ErrorCode.FIELD48_TAG002_MISSING,
            "Field 48 is missing; tag 002 cannot be verified.",
            field="48",
            spec_hint="Appendix A Field 48 tag 002",
        )
    tags = parse_lll_tagged_tlv(de48)
    tag2 = tags.get("002")
    if tag2 is None:
        return CheckFailure(
            ErrorCode.FIELD48_TAG002_MISSING,
            "Field 48 must contain tag 002 (SVFE transaction type).",
            field="48",
            spec_hint="Appendix A tag 002",
        )
    exp = expected_svfe_type_from_de3(de3)
    if exp is None:
        return None
    if tag2 != exp:
        return CheckFailure(
            ErrorCode.FIELD48_TAG002_MISMATCH_DE3,
            "Field 48 tag 002 does not match Processing Code for known mappings.",
            field="48",
            expected=exp,
            actual=tag2,
            spec_hint="Field 3 processing code vs Field 48 tag 002",
        )
    return None
