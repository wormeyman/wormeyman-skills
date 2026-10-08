import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_config  # noqa: E402


def test_required_names_exist():
    for name in ("SITE", "SITE_HOST", "AD_NETWORK", "PAGES", "FORM_PAGES", "SIGNUP_EMAIL",
                 "FORM_TEST_FIELDS", "RECORDER_UPLOADS", "CANARY", "SITE_VENDORS"):
        assert hasattr(site_config, name), name


def test_filled_in_after_scaffold():
    # In the template these are placeholders; in a scaffolded audit they must not be.
    values = [site_config.SITE, site_config.SITE_HOST, site_config.AD_NETWORK, site_config.CANARY]
    template = all(v.startswith("__") for v in values)
    filled = not any(v.startswith("__") for v in values)
    assert template or filled, "half-filled site_config.py"
    if filled:
        assert site_config.SITE.startswith("https://")
        assert re.fullmatch(r"[a-z0-9-]+@example\.com", site_config.CANARY)
