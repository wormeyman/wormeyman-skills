import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from analyze import inventory_owners, label  # noqa: E402

INVENTORY = {
    "hooks": {
        "wp_enqueue_scripts": [
            {"name": "x", "owner": "plugin:ad-plugin", "enqueued": {"ads": "https://scripts.adnetwork.example/tag.js"}},
            {"name": "rel", "owner": "plugin:local", "enqueued": {"local": "/wp-content/plugins/local/x.js"}},
        ],
        "wp_head": [
            {"name": "gtag", "owner": "theme:genesis", "prints": {"domains": ["www.googletagmanager.com"]}},
            {"name": "wp_print_head_scripts", "owner": "core", "prints": {"domains": ["scripts.adnetwork.example"]}},
            {"name": "proto", "owner": "plugin:recorder", "prints": {"domains": ["www.clarity.ms"]}},
        ],
        "wp_footer": [
            {"name": "gtag2", "owner": "plugin:google-analytics-for-wordpress", "prints": {"domains": ["www.googletagmanager.com"]}},
        ],
    },
    "options": {"genesis-settings": {"ga4": ["G-ABCDEF12"]}},
}


def test_owners(tmp_path):
    (tmp_path / "inventory.json").write_text(json.dumps(INVENTORY))
    owners = inventory_owners(tmp_path)
    assert owners["googletagmanager.com"] == "theme:genesis (wp_head); plugin:google-analytics-for-wordpress (wp_footer)"
    assert owners["adnetwork.example"] == "plugin:ad-plugin (wp_enqueue_scripts)"  # core printing is ignored
    assert owners["clarity.ms"] == "plugin:recorder (wp_head)"
    assert all(not k.startswith("/") for k in owners)  # relative script paths have no host


def test_no_inventory(tmp_path):
    assert inventory_owners(tmp_path) == {}


def test_label_prefers_inventory():
    name, source = label("clarity.ms", {"clarity.ms": "plugin:recorder (wp_head)"})
    assert source == "plugin:recorder (wp_head)"
    assert "Clarity" in name
