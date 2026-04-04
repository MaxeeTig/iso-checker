from __future__ import annotations

import re
from typing import Any

from iso_checker.errors import CheckFailure, ErrorCode

# Mandatory field sets from SVFE Message Formats (partner -> simulator requests)
MANDATORY_REQUEST: dict[str, frozenset[str]] = {
    "1100": frozenset(
        {
            "2",
            "3",
            "4",
            "11",
            "12",
            "15",
            "18",
            "22",
            "32",
            "37",
            "41",
            "42",
            "43",
            "48",
            "49",
        }
    ),
    "1200": frozenset(
        {
            "2",
            "3",
            "4",
            "11",
            "12",
            "15",
            "18",
            "22",
            "32",
            "37",
            "41",
            "42",
            "43",
            "48",
            "49",
        }
    ),
    "1220": frozenset(
        {
            "2",
            "3",
            "4",
            "11",
            "12",
            "15",
            "18",
            "22",
            "32",
            "37",
            "41",
            "42",
            "43",
            "48",
            "49",
        }
    ),
    "1221": frozenset(
        {
            "2",
            "3",
            "4",
            "11",
            "12",
            "15",
            "18",
            "22",
            "32",
            "37",
            "41",
            "42",
            "43",
            "48",
            "49",
        }
    ),
    "1420": frozenset(
        {
            "2",
            "3",
            "4",
            "11",
            "12",
            "15",
            "18",
            "22",
            "32",
            "37",
            "39",
            "41",
            "43",
            "48",
            "49",
        }
    ),
    "1421": frozenset(
        {
            "2",
            "3",
            "4",
            "11",
            "12",
            "15",
            "18",
            "22",
            "32",
            "37",
            "39",
            "41",
            "43",
            "48",
            "49",
        }
    ),
    "1804": frozenset({"11", "12", "24"}),
}

# Simulator responses we generate (for optional self-check)
MANDATORY_RESPONSE: dict[str, frozenset[str]] = {
    "1110": frozenset({"2", "3", "4", "11", "12", "15", "32", "37", "39", "41", "48", "49"}),
    "1210": frozenset({"2", "3", "4", "11", "12", "15", "32", "37", "39", "41", "48", "49"}),
    "1230": frozenset({"2", "3", "4", "11", "12", "15", "32", "37", "39", "41", "48", "49"}),
    "1430": frozenset({"2", "3", "4", "11", "12", "15", "32", "37", "39", "41", "48", "49"}),
    "1814": frozenset({"11", "24", "39"}),
}


def validate_mandatory_request(mti: str, present: set[str]) -> list[CheckFailure]:
    m = MANDATORY_REQUEST.get(mti)
    if not m:
        return []
    missing = sorted(m - present)
    if not missing:
        return []
    return [
        CheckFailure(
            ErrorCode.MCO_MISSING,
            f"Mandatory data elements missing for MTI {mti}: {', '.join(missing)}",
            spec_hint="Message Formats — request table",
            expected=f"DE {', '.join(missing)}",
            actual="absent",
        )
    ]


def validate_mandatory_response(mti: str, present: set[str]) -> list[CheckFailure]:
    m = MANDATORY_RESPONSE.get(mti)
    if not m:
        return []
    missing = sorted(m - present)
    if not missing:
        return []
    return [
        CheckFailure(
            ErrorCode.MCO_MISSING,
            f"Mandatory data elements missing for MTI {mti}: {', '.join(missing)}",
            spec_hint="Message Formats — response table",
            expected=f"DE {', '.join(missing)}",
            actual="absent",
        )
    ]


_FORMAT_RULES: list[tuple[str, int, re.Pattern[str]]] = [
    ("3", 6, re.compile(r"^\d{6}$")),
    ("4", 12, re.compile(r"^\d{12}$")),
    ("11", 6, re.compile(r"^\d{6}$")),
    ("12", 12, re.compile(r"^\d{12}$")),
    ("15", 6, re.compile(r"^\d{6}$")),
    ("37", 12, re.compile(r"^[A-Za-z0-9 ]{12}$")),
    ("39", 3, re.compile(r"^.{3}$")),
]


def validate_formats(decoded: dict[str, Any]) -> list[CheckFailure]:
    failures: list[CheckFailure] = []
    for field, _length, pat in _FORMAT_RULES:
        v = decoded.get(field)
        if v is None:
            continue
        s = str(v)
        if not pat.match(s):
            failures.append(
                CheckFailure(
                    ErrorCode.FORMAT_FIELD,
                    f"Field {field} has invalid format for SVFE profile.",
                    field=field,
                    expected=pat.pattern,
                    actual=s[:20] + ("…" if len(s) > 20 else ""),
                    spec_hint="Data Field Description",
                )
            )
    return failures
