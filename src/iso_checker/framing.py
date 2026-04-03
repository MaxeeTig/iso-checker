from __future__ import annotations

import struct
from typing import Final

MAX_FRAME_LEN: Final[int] = 65535


def read_frame_header(prefix: bytes) -> int:
    if len(prefix) < 2:
        raise ValueError("need 2 bytes")
    (n,) = struct.unpack("!H", prefix[:2])
    return int(n)


def pack_frame(body: bytes) -> bytes:
    if len(body) > MAX_FRAME_LEN:
        raise ValueError(f"body length {len(body)} exceeds {MAX_FRAME_LEN}")
    return struct.pack("!H", len(body)) + body


async def read_exact(reader, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            raise EOFError("connection closed")
        buf.extend(chunk)
    return bytes(buf)


async def read_framed_message(reader) -> bytes:
    header = await read_exact(reader, 2)
    n = read_frame_header(header)
    if n > MAX_FRAME_LEN:
        raise ValueError(f"FRAME_TOO_LARGE: declared length {n}")
    if n == 0:
        return b""
    return await read_exact(reader, n)


def write_framed_message(writer, body: bytes) -> None:
    writer.write(pack_frame(body))
