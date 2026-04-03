from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    FRAME_TOO_LARGE = "FRAME_TOO_LARGE"
    FRAME_SHORT_READ = "FRAME_SHORT_READ"
    PARSE_ERROR = "PARSE_ERROR"
    PARSE_BITMAP = "PARSE_BITMAP"
    MCO_MISSING = "MCO_MISSING"
    FORMAT_FIELD = "FORMAT_FIELD"
    FIELD48_TAG002_MISSING = "FIELD48_TAG002_MISSING"
    FIELD48_TAG002_MISMATCH_DE3 = "FIELD48_TAG002_MISMATCH_DE3"
    LEDGER_NO_PRIOR_STEP = "LEDGER_NO_PRIOR_STEP"
    MATCH_RRN = "MATCH_RRN"
    MATCH_PAN = "MATCH_PAN"
    MATCH_STAN = "MATCH_STAN"
    MATCH_LOCAL_TIME = "MATCH_LOCAL_TIME"
    SCENARIO_UNEXPECTED_MTI = "SCENARIO_UNEXPECTED_MTI"
    TIMEOUT = "TIMEOUT"
    VALIDATION_RULE = "VALIDATION_RULE"


REMEDIATION: dict[ErrorCode, str] = {
    ErrorCode.FRAME_TOO_LARGE: "Reduce message size; check framing (2-byte length must match body).",
    ErrorCode.FRAME_SHORT_READ: "Ensure the partner sends the full ISO message after the length prefix.",
    ErrorCode.PARSE_ERROR: "Verify binary bitmap (8 bytes), MTI (4 ASCII digits), and field formats per SVFE spec.",
    ErrorCode.PARSE_BITMAP: "Primary bitmap must be 8 bytes binary; secondary bitmap follows DE1 if bit 1 set.",
    ErrorCode.MCO_MISSING: "Include all mandatory data elements for this MTI per Message Formats in the spec.",
    ErrorCode.FORMAT_FIELD: "Check field length and encoding (e.g. DE12 is 12 digits YYMMDDhhmmss).",
    ErrorCode.FIELD48_TAG002_MISSING: "Field 48 must contain tag 002 (SVFE transaction type) in requests/responses when DE48 is present.",
    ErrorCode.FIELD48_TAG002_MISMATCH_DE3: "Align Field 48 tag 002 with the SVFE transaction type implied by Processing Code (Field 3).",
    ErrorCode.LEDGER_NO_PRIOR_STEP: "Run scenario steps in order; this step references a previous step that did not complete.",
    ErrorCode.MATCH_RRN: "For reversals, Field 37 should match the RRN from the original authorization response (MESSAGE MATCHING).",
    ErrorCode.MATCH_PAN: "PAN (Field 2) must match the original transaction.",
    ErrorCode.MATCH_STAN: "STAN (Field 11) must match the matching rules for this message class.",
    ErrorCode.MATCH_LOCAL_TIME: "Local date/time Field 12 must match the original for correlation.",
    ErrorCode.SCENARIO_UNEXPECTED_MTI: "Send the MTI expected by the current scenario step.",
    ErrorCode.VALIDATION_RULE: "Compare your message to the scenario validate rules and the SVFE Message Formats table.",
}


@dataclass
class CheckFailure:
    code: ErrorCode
    message: str
    field: str | None = None
    expected: str | None = None
    actual: str | None = None
    spec_hint: str | None = None

    def remediation(self) -> str:
        return REMEDIATION.get(self.code, "See docs/SVFE_Host2Host_AI_INDEX.md and Message Formats in the specification.")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "error_code": self.code.value,
            "message": self.message,
            "remediation": self.remediation(),
        }
        if self.field is not None:
            d["field"] = self.field
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        if self.spec_hint is not None:
            d["spec_hint"] = self.spec_hint
        return d
