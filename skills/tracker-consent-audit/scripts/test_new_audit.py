import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from new_audit import scaffold  # noqa: E402


def test_scaffold_fills_placeholders(tmp_path):
    dest = scaffold("https://www.example-blog.com", tmp_path / "audit", "Mediavine", "Example Blog")
    cfg = (dest / "scripts" / "site_config.py").read_text()
    assert 'SITE = "https://www.example-blog.com"' in cfg
    assert 'SITE_HOST = "example-blog.com"' in cfg
    assert 'AD_NETWORK = "Mediavine"' in cfg
    assert re.search(r'CANARY = "audit-canary-[0-9a-f]{4}@example\.com"', cfg)
    worker = re.search(r'name: "(wm-[0-9a-f]{6})"', (dest / "deploy" / "cloudflare.config.ts").read_text()).group(1)
    assert f'"name": "{worker}"' in (dest / "deploy" / "package.json").read_text()
    assert "__ACCESS_AUD__" in (dest / "deploy" / "cloudflare.config.ts").read_text()  # filled later, by hand
    assert (dest / "tracker-audit-probe.php").is_file()
    assert (dest / ".git").is_dir()
    for f in ("scripts/site_config.py", "README.md"):
        assert not re.search(r"__(SITE|SITE_HOST|AD_NETWORK|CANARY|WORKER_NAME|SITE_NAME|DATE)__", (dest / f).read_text()), f


def test_template_tests_pass_in_a_scaffold(tmp_path):
    dest = scaffold("https://www.example-blog.com", tmp_path / "audit", "Raptive", "Example Blog")
    r = subprocess.run(["uv", "run", "--with", "pytest", "pytest", "-q", "tests"], cwd=dest, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("site", ["http://example.com", "example.com", "https://",
                                  "https://example.com/blog", 'https://example.com"+x'])
def test_rejects_bad_site(tmp_path, site):
    with pytest.raises(SystemExit):
        scaffold(site, tmp_path / "audit", "Mediavine", "X")


@pytest.mark.parametrize("name", ["<script>alert(1)</script>", 'Quote "here"', "x" * 61])
def test_rejects_bad_name(tmp_path, name):
    with pytest.raises(SystemExit):
        scaffold("https://www.example.com", tmp_path / "audit", "Mediavine", name)


def test_refuses_non_empty_dest(tmp_path):
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit" / "keep.txt").write_text("x")
    with pytest.raises(SystemExit):
        scaffold("https://www.example.com", tmp_path / "audit", "Mediavine", "X")


def test_no_caches_or_build_output_copied(tmp_path):
    dest = scaffold("https://www.example.com", tmp_path / "audit", "Mediavine", "X")
    junk = {".pytest_cache", "__pycache__", "node_modules", ".cloudflare", "dist", ".wrangler", ".ruff_cache", ".DS_Store"}
    found = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if junk & set(p.relative_to(dest).parts))
    assert found == []


def test_probe_mtime_is_now(tmp_path):
    # The probe expires 48 hours after its file time, so an old template time would make it expired on upload.
    os.utime(Path(__file__).resolve().parent / "template" / "tracker-audit-probe.php", (0, 0))
    try:
        dest = scaffold("https://www.example.com", tmp_path / "audit", "Mediavine", "X")
        assert abs(time.time() - (dest / "tracker-audit-probe.php").stat().st_mtime) < 60
    finally:
        os.utime(Path(__file__).resolve().parent / "template" / "tracker-audit-probe.php")
