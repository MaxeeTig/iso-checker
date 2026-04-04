#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import struct
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from iso_checker.framing import pack_frame  # noqa: E402
from iso_checker.message_codec import decode_iso_message, encode_iso_message  # noqa: E402


def _de48(tag002: str) -> str:
    inner = f"002{len(tag002):03d}{tag002}"
    return f"{len(inner):03d}{inner}"


def _auth_1100() -> dict[str, str]:
    return {
        "t": "1100",
        "2": "4111111111111111",
        "3": "000000",
        "4": "000000001000",
        "11": "100001",
        "12": "250403120000",
        "14": "2512",
        "15": "250403",
        "18": "5999",
        "22": "510101510301",
        "32": "123456",
        "37": "RRN100000001",
        "41": "TERM0001",
        "42": "MERCHANT00001",
        "43": "ShopX                   CITY    PL",
        "48": _de48("774"),
        "49": "978",
    }


def _network_1804(code: str, stan: str) -> dict[str, str]:
    return {
        "t": "1804",
        "11": stan,
        "12": "250403120000",
        "24": code,
    }


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


def _exchange(sock: socket.socket, fields: dict[str, str]) -> dict[str, str]:
    raw = encode_iso_message(fields)
    sock.sendall(pack_frame(raw))
    resp = _read_framed(sock)
    decoded, _ = decode_iso_message(resp)
    print(f"{fields['t']} -> {decoded.get('t')} DE39={decoded.get('39')} DE37={decoded.get('37')}")
    return {str(k): str(v) for k, v in decoded.items()}


def run_scenario(host: str, port: int, scenario: str) -> int:
    with socket.create_connection((host, port), timeout=30) as sock:
        if scenario == "auth_reversal":
            auth = _auth_1100()
            resp = _exchange(sock, auth)
            reversal = {k: v for k, v in auth.items() if k != "t"}
            reversal["t"] = "1420"
            reversal["37"] = str(resp.get("37", "")).strip()
            reversal["39"] = "000"
            _exchange(sock, reversal)
            return 0
        if scenario == "network_echo":
            _exchange(sock, _network_1804("831", "000001"))
            return 0
        if scenario == "sign_on_sign_off":
            _exchange(sock, _network_1804("801", "000001"))
            _exchange(sock, _network_1804("802", "000002"))
            return 0
        raise ValueError(f"Unsupported scenario {scenario!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a predefined ISO checker scenario as a client.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8583)
    parser.add_argument("--scenario", required=True, choices=["auth_reversal", "network_echo", "sign_on_sign_off"])
    args = parser.parse_args()
    return run_scenario(args.host, args.port, args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())
