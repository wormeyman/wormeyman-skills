import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from gpp import decode, decode_usp  # noqa: E402

# Captured from a Mediavine site on 2026-10-07: plain visit, then the same page with GPC on.
PLAIN = "DBABL~BVQqAAAAAgA.QA"
WITH_GPC = "DBABL~BVQVAAAAAgA.YA"


def test_plain_visit_did_not_opt_out():
    d = decode(PLAIN)
    assert d["section_ids"] == [7]
    assert d["usnat"]["sale_opt_out"] == "did not opt out"
    assert d["usnat"]["sharing_opt_out"] == "did not opt out"
    assert d["usnat"]["targeted_advertising_opt_out"] == "did not opt out"
    assert d["usnat"]["gpc"] is False


def test_gpc_visit_opted_out():
    d = decode(WITH_GPC)
    assert d["usnat"]["sale_opt_out"] == "opted out"
    assert d["usnat"]["sharing_opt_out"] == "opted out"
    assert d["usnat"]["targeted_advertising_opt_out"] == "opted out"
    assert d["usnat"]["gpc"] is True


@pytest.mark.parametrize("bad", ["", "[GPP]", "${GPP}", "DBABL~", "not base64!"])
def test_malformed_raises(bad):
    with pytest.raises(ValueError):
        decode(bad)


def test_usp():
    assert decode_usp("1YN-") == {
        "version": 1, "notice_given": "yes", "opted_out_of_sale": "no", "lspa_covered": "not applicable",
    }
    assert decode_usp("1YYY")["opted_out_of_sale"] == "yes"
    with pytest.raises(ValueError):
        decode_usp("[US_PRIVACY]")
