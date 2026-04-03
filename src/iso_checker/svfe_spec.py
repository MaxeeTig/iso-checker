from __future__ import annotations

from copy import deepcopy

from iso8583.specs import default as iso_default


def get_svfe_iso_spec() -> dict:
    """ISO8583 decode/encode spec aligned with SVFE Host2Host (binary bitmap, common DE sizes)."""
    s = deepcopy(iso_default)
    # PAN LLVAR up to 24 (spec llvar n..24)
    s["2"]["max_len"] = 24
    # Local transaction date+time merged in DE12
    s["12"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 0,
        "max_len": 12,
        "desc": "Date & Time, Local Transaction YYMMDDhhmmss",
    }
    # Settlement date YYMMDD
    s["15"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 0,
        "max_len": 6,
        "desc": "Settlement Date",
    }
    # POS data ans12
    s["22"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 0,
        "max_len": 12,
        "desc": "Point of Service Data Code",
    }
    s["23"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 0,
        "max_len": 2,
        "desc": "Card Sequence Number",
    }
    s["36"]["max_len"] = 106
    s["39"]["max_len"] = 3
    s["43"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 3,
        "max_len": 136,
        "desc": "Card Acceptor Name/Location",
    }
    s["48"]["max_len"] = 999
    s["52"] = {
        "data_enc": "b",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": 16,
        "desc": "PIN Data LLVAR",
    }
    s["54"]["max_len"] = 999
    s["55"]["max_len"] = 255
    s["90"]["max_len"] = 33
    s["95"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 3,
        "max_len": 999,
        "desc": "Replacement Amounts TLV",
    }
    s["100"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": 11,
        "desc": "Receiving Institution ID",
    }
    s["102"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": 32,
        "desc": "Account Identification",
    }
    s["103"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": 32,
        "desc": "Account Identification 2",
    }
    s["112"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 3,
        "max_len": 999,
        "desc": "Payment Account Data",
    }
    s["123"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 4,
        "max_len": 9999,
        "desc": "Transaction-Specific Data LLLLVAR",
    }
    s["125"] = {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": 16,
        "desc": "New PIN Block",
    }
    return s
