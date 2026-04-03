from pathlib import Path

import pytest

from iso_checker.errors import ErrorCode
from iso_checker.message_codec import decode_iso_message, encode_iso_message
from iso_checker.scenario_engine import ScenarioLedger, load_scenario_file, run_validations


def _auth_msg():
    de48_inner = "002003774"
    de48 = f"{str(len(de48_inner)).zfill(3)}{de48_inner}"
    return {
        "t": "1100",
        "2": "4111111111111111",
        "3": "000000",
        "4": "000000001000",
        "11": "123456",
        "12": "250403120000",
        "14": "2512",
        "15": "250403",
        "18": "5999",
        "22": "510101510301",
        "32": "123456",
        "37": "ABC123567890",
        "41": "TERM0001",
        "42": "MERCHANTID00001",
        "43": "ShopX                   CITY    PL",
        "48": de48,
        "49": "978",
    }


def test_load_yaml(tmp_path: Path):
    p = tmp_path / "s.yaml"
    p.write_text(
        """
scenarios:
  - name: t
    steps:
      - id: a
        expect_mti: "1100"
        validate: {}
        respond:
          mti: "1110"
""",
        encoding="utf-8",
    )
    s = load_scenario_file(p, "t")
    assert s.name == "t"
    assert s.steps[0].id == "a"


def test_expect_field_values_sign_on():
    scenario_path = Path(__file__).resolve().parent.parent / "scenarios" / "sign_on_off.yaml"
    sc = load_scenario_file(scenario_path, "sign_on_sign_off")
    ledger = ScenarioLedger()
    req_on = {"t": "1804", "11": "000001", "12": "250403120000", "24": "801"}
    dec_on, _ = decode_iso_message(encode_iso_message(req_on))
    assert not run_validations(dec_on, sc.steps[0], ledger)
    rsp_on = {"t": "1814", "11": req_on["11"], "24": "801", "39": "000"}
    ledger.record(sc.steps[0].id, dec_on, rsp_on)
    req_off = {"t": "1804", "11": "000002", "12": "250403120001", "24": "802"}
    dec_off, _ = decode_iso_message(encode_iso_message(req_off))
    assert not run_validations(dec_off, sc.steps[1], ledger)


def test_expect_field_values_wrong_de24_fails(tmp_path: Path):
    p = tmp_path / "s.yaml"
    p.write_text(
        """
scenarios:
  - name: s
    steps:
      - id: sign_on
        expect_mti: "1804"
        validate:
          expect_field_values:
            "24": "801"
        respond:
          mti: "1814"
""",
        encoding="utf-8",
    )
    sc = load_scenario_file(p, "s")
    req = {"t": "1804", "11": "000001", "12": "250403001200", "24": "831"}
    dec, _ = decode_iso_message(encode_iso_message(req))
    fails = run_validations(dec, sc.steps[0], ScenarioLedger())
    assert fails
    assert fails[0].code == ErrorCode.VALIDATION_RULE


def test_auth_then_reversal_match():
    scenario_path = Path(__file__).resolve().parent.parent / "scenarios" / "default.yaml"
    sc = load_scenario_file(scenario_path, "auth_reversal")
    ledger = ScenarioLedger()
    req = _auth_msg()
    dec, _ = decode_iso_message(encode_iso_message(req))
    step0 = sc.steps[0]
    assert not run_validations(dec, step0, ledger)
    rsp = {
        "t": "1110",
        **{k: req[k] for k in ("2", "3", "4", "11", "12", "15", "32", "37", "41", "48", "49")},
        "39": "000",
        "38": "AUTHOK",
    }
    ledger.record(step0.id, dec, rsp)
    step1 = sc.steps[1]
    rev = {k: v for k, v in req.items() if k != "t"}
    rev["t"] = "1420"
    rev["37"] = rsp["37"]
    rev["39"] = "000"
    rdec, _ = decode_iso_message(encode_iso_message(rev))
    assert not run_validations(rdec, step1, ledger)
