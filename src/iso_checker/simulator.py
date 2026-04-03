from __future__ import annotations

from typing import Any

from iso_checker.message_codec import fields_present
from iso_checker.scenario_engine import RespondConfig, Step


def echo_fields_for_response(mti: str, req: dict[str, Any]) -> dict[str, Any]:
    """Populate common echo DEs from partner request."""
    out: dict[str, Any] = {"t": mti}
    numeric = fields_present(req)

    def copy_if_present(bit: str) -> None:
        if bit in req:
            out[bit] = req[bit]

    if mti in ("1110", "1210", "1130", "1230"):
        for b in ("2", "3", "4", "6", "11", "12", "15", "32", "37", "41", "42", "43", "48", "49", "51"):
            copy_if_present(b)
        copy_if_present("22")
        copy_if_present("23")
    elif mti == "1430":
        for b in ("2", "3", "4", "11", "12", "15", "23", "32", "37", "39", "41", "48", "49"):
            copy_if_present(b)
    elif mti == "1814":
        for b in ("11", "24"):
            copy_if_present(b)
    if len(out) <= 2 and numeric:
        for b in sorted(numeric):
            out[b] = req[b]
    return out


def build_response_for_step(step: Step, request_decoded: dict[str, Any]) -> dict[str, Any]:
    rc: RespondConfig = step.respond
    rsp = echo_fields_for_response(rc.mti, request_decoded)
    rsp["t"] = rc.mti
    for k, v in rc.field_overrides.items():
        rsp[str(k)] = str(v)
    if rc.mti in ("1110", "1210", "1130", "1230") and "39" not in rsp:
        rsp["39"] = "000"
    if rc.mti in ("1430",) and "39" not in rsp:
        rsp["39"] = "000"
    if rc.mti == "1814" and "39" not in rsp:
        rsp["39"] = "000"
    if rc.mti in ("1110", "1210", "1130") and rsp.get("39") == "000" and "38" not in rsp:
        rsp["38"] = "AUTHOK"
    return rsp
