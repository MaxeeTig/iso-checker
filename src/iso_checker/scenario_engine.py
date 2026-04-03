from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from iso_checker.errors import CheckFailure, ErrorCode
from iso_checker.field48 import check_field48_tag002
from iso_checker.message_codec import fields_present, mti_from_decoded
from iso_checker.validators import validate_formats, validate_mandatory_request


@dataclass
class RespondConfig:
    mti: str
    field_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class ValidateConfig:
    required_fields: list[str] = field(default_factory=list)
    field48_check_de3: bool = False
    matches_step: str | None = None


@dataclass
class CaptureConfig:
    response: dict[str, str] = field(default_factory=dict)
    request: dict[str, str] = field(default_factory=dict)


@dataclass
class Step:
    id: str
    expect_mti: str
    validate: ValidateConfig
    respond: RespondConfig
    capture: CaptureConfig


@dataclass
class Scenario:
    name: str
    description: str = ""
    steps: list[Step] = field(default_factory=list)


@dataclass
class ScenarioLedger:
    """step id -> request/response decode dicts (digit field keys + t)."""

    step_data: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def record(self, step_id: str, request_decoded: dict[str, Any], response_decoded: dict[str, Any]) -> None:
        def filt(d: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in d.items() if (k.isdigit() or k == "t")}

        self.step_data[step_id] = {"request": filt(request_decoded), "response": filt(response_decoded)}

    def get_prior(self, step_id: str) -> dict[str, dict[str, Any]] | None:
        return self.step_data.get(step_id)


def _parse_validate(d: dict[str, Any]) -> ValidateConfig:
    return ValidateConfig(
        required_fields=list(d.get("required_fields") or []),
        field48_check_de3=bool(d.get("field48_check_de3", False)),
        matches_step=d.get("matches_step"),
    )


def _parse_capture(d: dict[str, Any]) -> CaptureConfig:
    return CaptureConfig(
        response=dict(d.get("response") or {}),
        request=dict(d.get("request") or {}),
    )


def _parse_step(d: dict[str, Any]) -> Step:
    rc = d.get("respond") or {}
    return Step(
        id=str(d["id"]),
        expect_mti=str(d["expect_mti"]),
        validate=_parse_validate(d.get("validate") or {}),
        respond=RespondConfig(mti=str(rc["mti"]), field_overrides=dict(rc.get("field_overrides") or {})),
        capture=_parse_capture(d.get("capture") or {}),
    )


def load_scenario_file(path: Path, scenario_name: str | None = None) -> Scenario:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "scenarios" in raw:
        scenarios_list = list(raw["scenarios"])
    elif isinstance(raw, dict) and "steps" in raw:
        scenarios_list = [raw]
    else:
        raise ValueError("YAML must contain 'scenarios: [...]' or top-level 'steps:'")
    if not scenarios_list:
        raise ValueError("No scenarios defined")
    picked: dict[str, Any] | None = None
    if scenario_name:
        for s in scenarios_list:
            if str(s.get("name")) == scenario_name:
                picked = s
                break
        if picked is None:
            raise ValueError(f"Scenario named {scenario_name!r} not found")
    else:
        picked = scenarios_list[0]
    steps = [_parse_step(x) for x in picked.get("steps") or []]
    if not steps:
        raise ValueError("Scenario has no steps")
    return Scenario(
        name=str(picked.get("name") or "unnamed"),
        description=str(picked.get("description") or ""),
        steps=steps,
    )


def validate_step_capture(
    prior_step_id: str,
    ledger: ScenarioLedger,
    decoded: dict[str, Any],
) -> list[CheckFailure]:
    prior = ledger.get_prior(prior_step_id)
    if prior is None:
        return [
            CheckFailure(
                ErrorCode.LEDGER_NO_PRIOR_STEP,
                f"No data for prior step {prior_step_id!r}; run scenario steps in order.",
                spec_hint="Scenario ledger",
            )
        ]
    failures: list[CheckFailure] = []
    req = prior["request"]
    resp = prior["response"]
    pan = str(decoded.get("2") or "").strip()
    exp_pan = str(req.get("2") or "").strip()
    if exp_pan and pan != exp_pan:
        failures.append(
            CheckFailure(
                ErrorCode.MATCH_PAN,
                "PAN must match the original transaction for this step.",
                field="2",
                expected=exp_pan,
                actual=pan,
                spec_hint="MESSAGE MATCHING — reversals",
            )
        )
    rrn = str(decoded.get("37") or "").strip()
    exp_rrn = str(resp.get("37") or "").strip()
    if exp_rrn and rrn != exp_rrn:
        failures.append(
            CheckFailure(
                ErrorCode.MATCH_RRN,
                "Field 37 (RRN) must match the authorization response of the original transaction.",
                field="37",
                expected=exp_rrn,
                actual=rrn,
                spec_hint="MESSAGE MATCHING — reversals",
            )
        )
    return failures


def run_validations(decoded: dict[str, Any], step: Step, ledger: ScenarioLedger) -> list[CheckFailure]:
    fail: list[CheckFailure] = []
    mti = mti_from_decoded(decoded)
    if mti != step.expect_mti:
        fail.append(
            CheckFailure(
                ErrorCode.SCENARIO_UNEXPECTED_MTI,
                f"Expected MTI {step.expect_mti} for step {step.id!r}, got {mti}.",
                expected=step.expect_mti,
                actual=mti,
            )
        )
        return fail
    present = fields_present(decoded)
    fail.extend(validate_mandatory_request(mti, present))
    fail.extend(validate_formats(decoded))
    for extra in step.validate.required_fields:
        if extra not in present:
            fail.append(
                CheckFailure(
                    ErrorCode.MCO_MISSING,
                    f"Scenario requires field {extra} for step {step.id}.",
                    field=extra,
                    spec_hint="scenario validate.required_fields",
                )
            )
    if step.validate.field48_check_de3 and "48" in present:
        e = check_field48_tag002(str(decoded.get("3", "")), str(decoded.get("48", "")))
        if e:
            fail.append(e)
    if step.validate.matches_step:
        fail.extend(validate_step_capture(step.validate.matches_step, ledger, decoded))
    return fail
