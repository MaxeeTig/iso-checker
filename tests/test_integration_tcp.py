import asyncio
from pathlib import Path

import pytest

from iso_checker.framing import pack_frame, read_framed_message
from iso_checker.logging_report import RunReport
from iso_checker.message_codec import decode_iso_message, encode_iso_message
from iso_checker.server import handle_connection


def _sample_1100():
    de48_inner = "002003774"
    de48 = f"{str(len(de48_inner)).zfill(3)}{de48_inner}"
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
        "42": "MERCHANTID00001",
        "43": "ShopX                   CITY    PL",
        "48": de48,
        "49": "978",
    }


@pytest.mark.asyncio
async def test_tcp_auth_reversal_roundtrip() -> None:
    scen = Path(__file__).resolve().parent.parent / "scenarios" / "default.yaml"

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await handle_connection(reader, writer, scen, "auth_reversal", RunReport("test-session", None))

    srv = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]

    async def serve() -> None:
        async with srv:
            await srv.serve_forever()

    bg = asyncio.create_task(serve())
    await asyncio.sleep(0.05)
    try:
        r, w = await asyncio.open_connection("127.0.0.1", port)
        a = encode_iso_message(_sample_1100())
        w.write(pack_frame(a))
        await w.drain()
        raw = await asyncio.wait_for(read_framed_message(r), timeout=2.0)
        d1, _ = decode_iso_message(raw)
        assert d1["t"] == "1110"
        assert d1["39"] == "000"
        rev = _sample_1100()
        rev["t"] = "1420"
        rev["37"] = d1["37"]
        rev["39"] = "000"
        w.write(pack_frame(encode_iso_message(rev)))
        await w.drain()
        raw2 = await asyncio.wait_for(read_framed_message(r), timeout=2.0)
        d2, _ = decode_iso_message(raw2)
        assert d2["t"] == "1430"
        w.close()
        await w.wait_closed()
    finally:
        bg.cancel()
        try:
            await bg
        except asyncio.CancelledError:
            pass
