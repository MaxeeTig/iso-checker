from iso_checker.tlv import build_lll_tagged_tlv, parse_lll_tagged_tlv


def test_tlv_roundtrip():
    tags = {"002": "774", "004": "1"}
    s = build_lll_tagged_tlv(tags)
    assert parse_lll_tagged_tlv(s) == tags


def test_parse_field48_sample():
    inner = "002003774"  # tag 002 len 3 val 774
    de48 = f"{str(len(inner)).zfill(3)}{inner}"
    assert parse_lll_tagged_tlv(de48)["002"] == "774"
