from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iso_checker.app_services import Company
from iso_checker.framing import pack_frame
from iso_checker.message_codec import decode_iso_message, encode_iso_message
from iso_checker.scenario_engine import (
    Scenario,
    ScenarioLedger,
    Step,
    load_scenario_file,
    scenario_supports_reference_client,
)


def _read_framed(sock: socket.socket) -> bytes:
    hdr = sock.recv(2)
    if len(hdr) != 2:
        raise EOFError("short read on length prefix")
    (n,) = struct.unpack("!H", hdr)
    body = bytearray()
    while len(body) < n:
        chunk = sock.recv(n - len(body))
        if not chunk:
            raise EOFError("connection closed while reading body")
        body.extend(chunk)
    return bytes(body)


def build_outbound_fields(
    step: Step,
    ledger: ScenarioLedger,
    *,
    company: Company | None,
    stan: str,
) -> dict[str, str]:
    ref = step.reference_request
    if ref is None:
        raise ValueError(f"Step {step.id!r} has no reference_request")
    if ref.inherit_request_from:
        prior = ledger.get_prior(ref.inherit_request_from)
        if prior is None:
            raise ValueError(
                f"No reference-client ledger data for inherit_request_from={ref.inherit_request_from!r} "
                f"(step {step.id!r})"
            )
        fields = {str(k): str(v) for k, v in prior["request"].items()}
        for k, v in ref.field_overrides.items():
            fields[str(k)] = str(v)
        resp = prior["response"]
        for dest, src in ref.copy_response_fields.items():
            fields[str(dest)] = str(resp.get(str(src), "")).strip()
    else:
        if not ref.flat_fields:
            raise ValueError(f"Step {step.id!r} reference_request has no flat_fields")
        fields = {str(k): str(v) for k, v in ref.flat_fields.items()}
    fields["11"] = stan
    if company is not None:
        if company.expected_de32:
            fields["32"] = company.expected_de32
        if company.expected_de41:
            fields["41"] = company.expected_de41
        if company.expected_de42:
            fields["42"] = company.expected_de42
    return fields


@dataclass
class ReferenceRunResult:
    ok: bool
    lines: list[str] = field(default_factory=list)
    error: str | None = None


def run_reference_scenario(
    host: str,
    port: int,
    scenario_path: Path,
    scenario_name: str,
    *,
    company: Company | None = None,
    stan_start: int = 100_001,
    timeout: float = 30.0,
) -> ReferenceRunResult:
    lines: list[str] = []
    try:
        scenario = load_scenario_file(scenario_path, scenario_name)
    except Exception as e:
        return ReferenceRunResult(ok=False, lines=[str(e)], error=str(e))
    if not scenario_supports_reference_client(scenario):
        msg = f"Scenario {scenario_name!r} is missing reference_request on one or more steps"
        return ReferenceRunResult(ok=False, lines=[msg], error=msg)

    ledger = ScenarioLedger()
    stan = stan_start
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            for step in scenario.steps:
                stan_str = f"{stan:06d}"
                stan += 1
                fields = build_outbound_fields(step, ledger, company=company, stan=stan_str)
                raw = encode_iso_message(fields)
                sock.sendall(pack_frame(raw))
                lines.append(f"→ {fields.get('t')} STAN={fields.get('11')} fields={_short_fields(fields)}")
                resp_b = _read_framed(sock)
                decoded, _ = decode_iso_message(resp_b)
                rsp = {str(k): str(v) for k, v in decoded.items()}
                lines.append(
                    f"← {rsp.get('t')} DE39={rsp.get('39')} DE37={rsp.get('37')}",
                )
                ledger.record(step.id, fields, rsp)
    except Exception as e:
        lines.append(f"Error: {e}")
        return ReferenceRunResult(ok=False, lines=lines, error=str(e))
    lines.append("Done.")
    return ReferenceRunResult(ok=True, lines=lines)


def _short_fields(fields: dict[str, str]) -> str:
    keys = sorted(fields.keys(), key=lambda x: (len(x) > 1, x))
    parts = [f"{k}={fields[k][:16]}{'…' if len(fields[k]) > 16 else ''}" for k in keys if k != "2"]
    pan = fields.get("2")
    if pan:
        parts.insert(0, "2=<pan>")
    return ", ".join(parts[:12]) + (" …" if len(parts) > 12 else "")


def list_runnable_reference_scenario_names(scenario_path: Path) -> list[str]:
    names: list[str] = []
    try:
        from iso_checker.scenario_engine import list_scenarios

        for item in list_scenarios(scenario_path):
            name = str(item.get("name") or "")
            if not name:
                continue
            try:
                sc = load_scenario_file(scenario_path, name)
                if scenario_supports_reference_client(sc):
                    names.append(name)
            except Exception:
                continue
    except Exception:
        return []
    return sorted(names)


def scenario_reference_payloads_for_display(scenario_path: Path, scenario_name: str) -> list[dict[str, Any]]:
    """Static preview of reference_request templates (STAN/company not applied)."""
    scenario = load_scenario_file(scenario_path, scenario_name)
    out: list[dict[str, Any]] = []
    for step in scenario.steps:
        ref = step.reference_request
        if ref is None:
            out.append({"step_id": step.id, "mode": "none"})
        elif ref.flat_fields:
            out.append({"step_id": step.id, "mode": "flat", "fields": dict(ref.flat_fields)})
        else:
            out.append(
                {
                    "step_id": step.id,
                    "mode": "inherit",
                    "inherit_request_from": ref.inherit_request_from,
                    "field_overrides": dict(ref.field_overrides),
                    "copy_response_fields": dict(ref.copy_response_fields),
                },
            )
    return out
