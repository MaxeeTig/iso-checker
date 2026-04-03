import asyncio

import pytest

from iso_checker.framing import pack_frame, read_framed_message, read_frame_header


@pytest.mark.asyncio
async def test_read_framed_message():
    body = b"hello"
    payload = pack_frame(body)

    class R:
        def __init__(self, data: bytes) -> None:
            self._d = data

        async def read(self, n: int) -> bytes:
            out = self._d[:n]
            self._d = self._d[n:]
            return out

    got = await read_framed_message(R(payload))
    assert got == body


def test_header():
    assert read_frame_header(b"\x00\x05") == 5
