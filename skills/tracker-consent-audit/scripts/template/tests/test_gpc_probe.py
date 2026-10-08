import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from gpc_probe import privacy_strings  # noqa: E402


def test_extracts_and_drops_placeholders():
    reqs = [
        {"url": "https://a.example/bid?gpp=DBABL~BVQqAAAAAgA.QA&gpp_sid=7"},
        {"url": "https://b.example/x?gpp=DBABL%7EBVQqAAAAAgA.QA"},
        {"url": "https://c.example/x?gpp=[GPP]&us_privacy=[US_PRIVACY]"},
        {"url": "https://d.example/x?us_privacy=1YN-"},
        {"url": "https://e.example/x?us_privacy=%5BUS_PRIVACY%5D&gpp=${GPP}"},
    ]
    got = privacy_strings(reqs)
    assert got["gpp"] == {"DBABL~BVQqAAAAAgA.QA"}
    assert got["us_privacy"] == {"1YN-"}
