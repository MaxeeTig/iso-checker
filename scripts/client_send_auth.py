#!/usr/bin/env python3
"""
Send a sample authorization request (MTI 1100) to the ISO checker / SVFE simulator.

Uses the same 2-byte big-endian length framing as Host2Host. Run from the
repository root with the virtualenv activated and dependencies installed.

  python scripts/client_send_auth.py --host 127.0.0.1 --port 8583

Optional: send a second message (e.g. run a full scenario interactively by
adding --reversal after a successful auth (same RRN as in response)).
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
from pathlib import Path

# Allow running without pip install (repo checkout)
_ROOT = Path(__file__).resolve().parents[1]
_src = _ROOT / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from iso_checker.framing import pack_frame  # noqa: E402
from iso_checker.message_codec import decode_iso_message, encode_iso_message  # noqa: E402


def _build_1100(
    *,
    pan: str,
    amount_minor_units: str,
    stan: str,
    local_datetime_12: str,
    retrieval_ref_12: str,
    terminal_id: str,
    merchant_id: str,
    acquirer_id: str,
    currency_numeric: str,
    processing_code: str,
    field48_tag002_svfe: str,
) -> dict[str, str]:
    """Build a minimal valid 1100 for the default scenario (tag 002 must match DE3 mapping)."""
    de48_inner = f"002{len(field48_tag002_svfe):03d}{field48_tag002_svfe}"
    de48 = f"{len(de48_inner):03d}{de48_inner}"
    return {
        "t": "1100",
        "2": pan,
        "3": processing_code.zfill(6)[:6],
        "4": amount_minor_units.zfill(12)[-12:],
        "11": stan.zfill(6)[-6:],
        "12": local_datetime_12,
        "14": "2512",
        "15": local_datetime_12[:6],
        "18": "5999",
        "22": "510101510301",
        "32": acquirer_id,
        "37": retrieval_ref_12.ljust(12)[:12],
        "41": terminal_id.ljust(8)[:8],
        "42": merchant_id.ljust(15)[:15],
        "43": "Test merchant           CITY    US".ljust(40)[:40],
        "48": de48,
        "49": currency_numeric.zfill(3)[-3:],
    }


def _read_framed(sock: socket.socket) -> bytes:
    hdr = sock.recv(2)
    if len(hdr) != 2:
        raise EOFError("short read on length prefix")
    (n,) = struct.unpack("!H", hdr)
    if n == 0:
        return b""
    body = bytearray()
    while len(body) < n:
        chunk = sock.recv(n - len(body))
        if not chunk:
            raise EOFError("connection closed while reading body")
        body.extend(chunk)
    return bytes(body)


def _send_framed(sock: socket.socket, body: bytes) -> None:
    sock.sendall(pack_frame(body))


def main() -> int:
    p = argparse.ArgumentParser(description="Send MTI 1100 auth request to SVFE simulator (port 8583).")
    p.add_argument("--host", default="127.0.0.1", help="Simulator host")
    p.add_argument("--port", type=int, default=8583, help="Simulator TCP port")
    p.add_argument("--pan", default="4111111111111111")
    p.add_argument("--amount", default="000000010000", help="12-digit transaction amount (minor units)")
    p.add_argument("--stan", default="900001", help="6-digit STAN")
    p.add_argument("--when", default="250403143000", help="12-digit local YYMMDDhhmmss for DE12")
    p.add_argument("--rrn", default="CLI000000001", help="12-char RRN for DE37")
    p.add_argument("--tag002", default="774", help="Field 48 tag 002 SVFE txn type (774 for purchase + DE3 000000)")
    p.add_argument("--reversal", action="store_true", help="After 1110, send 1420 reversal using RRN from response")
    args = p.parse_args()

    req = _build_1100(
        pan=args.pan,
        amount_minor_units=args.amount,
        stan=args.stan,
        local_datetime_12=args.when,
        retrieval_ref_12=args.rrn,
        terminal_id="TERM0001",
        merchant_id="MERCHANT00001",
        acquirer_id="123456",
        currency_numeric="978",
        processing_code="000000",
        field48_tag002_svfe=args.tag002,
    )

    raw = encode_iso_message(req)
    print(f"Connecting to {args.host}:{args.port} …")
    with socket.create_connection((args.host, args.port), timeout=30) as sock:
        _send_framed(sock, raw)
        print(f"Sent 1100 ({len(raw)} bytes ISO payload + 2-byte length prefix).")
        resp_body = _read_framed(sock)
        dec, _ = decode_iso_message(resp_body)
        mti = dec.get("t", "?")
        print(f"Response MTI {mti} DE39={dec.get('39')} DE37={dec.get('37')} DE38={dec.get('38')}")

        if args.reversal and mti == "1110" and dec.get("39") == "000":
            rrn_resp = str(dec.get("37", "")).strip()
            rev = {k: v for k, v in req.items() if k != "t"}
            rev["t"] = "1420"
            rev["37"] = rrn_resp
            rev["39"] = "000"
            raw_r = encode_iso_message(rev)
            _send_framed(sock, raw_r)
            print("Sent 1420 reversal …")
            resp2 = _read_framed(sock)
            d2, _ = decode_iso_message(resp2)
            print(f"Response MTI {d2.get('t')} DE39={d2.get('39')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
