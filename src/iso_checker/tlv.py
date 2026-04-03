from __future__ import annotations


def parse_lll_tagged_tlv(de48: str) -> dict[str, str]:
    """Parse SVFE Field 48 / 54 / 61 style body: 3-digit LLL then [3 tag][3 len][data]... returns tag->data str."""
    if not de48 or len(de48) < 3:
        return {}
    try:
        total = int(de48[:3])
    except ValueError:
        return {}
    inner = de48[3 : 3 + total]
    if len(inner) != total:
        return {}
    out: dict[str, str] = {}
    pos = 0
    while pos + 6 <= len(inner):
        tag = inner[pos : pos + 3]
        ln = int(inner[pos + 3 : pos + 6])
        pos += 6
        if pos + ln > len(inner):
            break
        out[tag] = inner[pos : pos + ln]
        pos += ln
    return out


def build_lll_tagged_tlv(tags: dict[str, str]) -> str:
    parts: list[str] = []
    for tag in sorted(tags.keys()):
        data = tags[tag]
        t = tag.zfill(3)[-3:]
        ln = len(data)
        parts.append(f"{t}{str(ln).zfill(3)}{data}")
    inner = "".join(parts)
    return f"{str(len(inner)).zfill(3)}{inner}"
