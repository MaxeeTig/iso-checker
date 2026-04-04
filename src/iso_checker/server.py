from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import iso8583
import structlog

from iso_checker.app_services import AppServices, Company
from iso_checker.errors import ErrorCode
from iso_checker.framing import pack_frame, read_framed_message
from iso_checker.logging_report import RunReport, mask_pan
from iso_checker.message_codec import decode_iso_message, encode_iso_message, mti_from_decoded
from iso_checker.scenario_engine import Scenario, ScenarioLedger, load_scenario_file, run_validations
from iso_checker.simulator import build_response_for_step, echo_fields_for_response

log = structlog.get_logger(__name__)


@dataclass
class SessionState:
    scenario: Scenario | None = None
    company: Company | None = None
    run_id: int | None = None
    step_index: int = 0
    ledger: ScenarioLedger = field(default_factory=ScenarioLedger)
    msg_seq: int = 0


def _decline_payload(req: dict[str, Any], response_mti: str, code: str = "057") -> dict[str, Any]:
    """Minimal decline with fixed response code."""
    r = echo_fields_for_response(response_mti, req)
    r["t"] = response_mti
    r["39"] = code
    return r


async def handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    scenario_path: Path,
    scenario_name: str | None,
    report: RunReport | None,
    services: AppServices | None = None,
) -> None:
    peer = writer.get_extra_info("peername")
    cfg_log = structlog.get_logger(peer=str(peer))
    state = SessionState()
    if not services:
        try:
            state.scenario = load_scenario_file(scenario_path, scenario_name)
        except Exception as e:
            cfg_log.error("scenario_load_failed", err=str(e))
            writer.close()
            await writer.wait_closed()
            return
        if report:
            report.emit("connected", scenario=state.scenario.name)
        cfg_log.info("session_start", scenario=state.scenario.name)
    else:
        cfg_log.info("session_start", scenario="deferred_partner_resolution")

    try:
        while True:
            try:
                raw = await read_framed_message(reader)
            except EOFError:
                cfg_log.info("peer_closed")
                break
            except ValueError as e:
                cfg_log.error("frame_error", error=str(e))
                if report:
                    report.emit("validation_fail", error_code=ErrorCode.FRAME_TOO_LARGE.value, message=str(e))
                break
            except OSError as e:
                cfg_log.error("read_error", error=str(e))
                break

            state.msg_seq += 1
            if report:
                report.emit("rx_frame", seq=state.msg_seq, bytes=len(raw))

            try:
                decoded, _enc = decode_iso_message(raw)
            except iso8583.DecodeError as e:
                cfg_log.error("parse_error", error=str(e))
                if report:
                    report.emit("validation_fail", error_code=ErrorCode.PARSE_ERROR.value, message=str(e))
                break

            mti = mti_from_decoded(decoded)
            cfg_log.info(
                "rx_message",
                seq=state.msg_seq,
                mti=mti,
                pan_masked=mask_pan(str(decoded.get("2", ""))),
            )

            if state.scenario is None:
                if services is None:
                    cfg_log.error("scenario_not_loaded")
                    break
                company = services.resolve_company(decoded)
                if company is None:
                    cfg_log.warning("company_resolution_failed", mti=mti)
                    if report:
                        report.emit(
                            "validation_fail",
                            error_code=ErrorCode.VALIDATION_RULE.value,
                            message="Unable to resolve partner/company for inbound message.",
                        )
                    break
                selected_scenario = scenario_name or company.scenario_name
                try:
                    state.scenario = load_scenario_file(scenario_path, selected_scenario)
                except Exception as e:
                    cfg_log.error("scenario_load_failed", err=str(e), company=company.slug)
                    break
                state.company = company
                state.run_id = services.create_run(
                    company=company,
                    scenario_name=state.scenario.name,
                    session_id=report.session_id if report else str(uuid.uuid4()),
                    client_addr=str(peer),
                )
                services.audit(
                    "tcp_session_started",
                    company_id=company.id,
                    details={"peer": str(peer), "scenario": state.scenario.name},
                )
                if report:
                    report.emit("connected", scenario=state.scenario.name, company=company.name)
                cfg_log = cfg_log.bind(company=company.slug, scenario=state.scenario.name)
                cfg_log.info("company_resolved", company=company.slug, scenario=state.scenario.name)

            if state.step_index >= len(state.scenario.steps):
                cfg_log.warning("scenario_already_complete")
                if report:
                    report.emit("scenario_fail", message="No more steps; reconnect to restart scenario.")
                if services and state.run_id is not None:
                    services.finish_run(state.run_id, status="failed", summary="No more steps; reconnect to restart scenario.")
                break

            step = state.scenario.steps[state.step_index]
            failures = run_validations(decoded, step, state.ledger)

            if failures:
                f = failures[0]
                cfg_log.warning(
                    "validation_failed",
                    step=step.id,
                    error_code=f.code.value,
                    message=f.message,
                )
                if report:
                    report.emit(
                        "validation_fail",
                        step=step.id,
                        seq=state.msg_seq,
                        **f.to_dict(),
                    )
                # Human-readable line
                if report:
                    report.human(
                        f"FAIL step {state.step_index + 1} ({step.id}): [{f.code.value}] {f.message}\n"
                        f"  {f.remediation()}"
                    )
                if services and state.run_id is not None:
                    services.record_message(
                        run_id=state.run_id,
                        seq=state.msg_seq,
                        direction="inbound",
                        payload=raw,
                        decoded=decoded,
                        validation_status="failed",
                        error_code=f.code.value,
                        error_message=f.message,
                    )
                    services.finish_run(state.run_id, status="failed", summary=f.message)
                decline_mti = step.respond.mti
                out = _decline_payload(decoded, decline_mti, code="057")
                try:
                    out_b = encode_iso_message(out)
                    writer.write(pack_frame(out_b))
                    await writer.drain()
                    if services and state.run_id is not None:
                        services.record_message(
                            run_id=state.run_id,
                            seq=state.msg_seq,
                            direction="outbound",
                            payload=out_b,
                            decoded=out,
                            validation_status="failed",
                            error_code=f.code.value,
                            error_message="Auto-decline sent after validation failure.",
                        )
                except Exception as enc_e:
                    cfg_log.error("encode_decline_failed", error=str(enc_e))
                break

            if services and state.run_id is not None:
                services.record_message(
                    run_id=state.run_id,
                    seq=state.msg_seq,
                    direction="inbound",
                    payload=raw,
                    decoded=decoded,
                    validation_status="ok",
                )

            rsp = build_response_for_step(step, decoded)
            try:
                out_b = encode_iso_message(rsp)
            except Exception as e:
                cfg_log.error("encode_response_failed", error=str(e))
                if report:
                    report.emit("validation_fail", message=str(e))
                break

            if report:
                report.emit("tx_frame", seq=state.msg_seq, bytes=len(out_b), mti=rsp.get("t"))
            cfg_log.info("tx_message", mti=rsp.get("t"), seq=state.msg_seq)

            state.ledger.record(step.id, decoded, rsp)
            state.step_index += 1

            writer.write(pack_frame(out_b))
            await writer.drain()
            if services and state.run_id is not None:
                services.record_message(
                    run_id=state.run_id,
                    seq=state.msg_seq,
                    direction="outbound",
                    payload=out_b,
                    decoded=rsp,
                    validation_status="ok",
                )

            if state.step_index >= len(state.scenario.steps):
                if report:
                    report.emit("scenario_pass", scenario=state.scenario.name, messages=state.msg_seq)
                    report.human(f"PASS scenario {state.scenario.name!r} completed in {state.msg_seq} messages.")
                if services and state.run_id is not None:
                    services.finish_run(
                        state.run_id,
                        status="passed",
                        summary=f"Scenario {state.scenario.name} completed in {state.msg_seq} messages.",
                    )
                cfg_log.info("scenario_complete", scenario=state.scenario.name)
                break

    finally:
        writer.close()
        await writer.wait_closed()
        if services and state.run_id is not None:
            if state.scenario is not None and state.step_index < len(state.scenario.steps):
                services.finish_run(state.run_id, status="failed", summary="Session closed before scenario completion.")
        if report:
            report.close()


async def serve(
    host: str,
    port: int,
    scenario_path: Path,
    scenario_name: str | None,
    report_path: Path | None,
    services: AppServices | None = None,
) -> None:
    srv: asyncio.Server | None = None

    async def _client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        rep = RunReport(str(uuid.uuid4()), report_path)
        await handle_connection(reader, writer, scenario_path, scenario_name, rep, services)

    srv = await asyncio.start_server(_client, host, port)
    log.info("listening", host=host, port=port, scenario=str(scenario_path))
    async with srv:
        await srv.serve_forever()
