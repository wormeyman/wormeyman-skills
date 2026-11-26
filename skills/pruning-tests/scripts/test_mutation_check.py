"""Tests for mutation_check.py, run against a tiny pytest project it breaks on purpose.

uv run --with pytest pytest skills/pruning-tests/scripts/test_mutation_check.py
"""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutation_check import main

PRODUCT = """\
def total(qty):
    if qty > 0:
        return qty * 2
    return 0
"""

TESTS = """\
import os
import time
from product import total

def test_keeper_pins_zero():
    assert total(0) == 0
    assert total(3) == 6

def test_cut_only_checks_type():
    assert isinstance(total(3), int)

def test_harness_style_failure():
    if total(0) != 0:
        raise TimeoutError("Timeout 5000ms exceeded while waiting for the page")

def test_polled_assertion_times_out():
    # Timeout 5000ms exceeded while waiting on the predicate
    assert total(0) == 0

def test_sleeps():
    if total(0) != 0 and os.environ.get("MUTATION_CHECK_SLEEP"):
        time.sleep(30)
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "product.py").write_text(PRODUCT)
    (tmp_path / "test_product.py").write_text(TESTS)
    return tmp_path


def run(project, find, replace, *expect, timeout=120, control=True, monkeypatch=None):
    junit = project / "junit.xml"
    args = [
        "--file",
        str(project / "product.py"),
        "--find",
        find,
        "--replace",
        replace,
        "--junit",
        str(junit),
        "--timeout",
        str(timeout),
    ]
    for kind, text in expect:
        args += [f"--expect-{kind}", text]
    if not control:
        args.append("--no-control")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--junitxml={junit}",
        "--rootdir",
        str(project),
        str(project / "test_product.py"),
    ]
    return main(args + ["--", *cmd])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_keeper_killed_and_cut_test_stays_green(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    before = digest(project / "product.py")
    mtime = (project / "product.py").stat().st_mtime_ns
    # The control run imports product.py first, so a same-size mutant written
    # in the same second would reuse its cached bytecode without the mtime bump.
    code = run(
        project, "return 0", "return 1", ("fail", "test_keeper_pins_zero"), ("pass", "test_cut_only_checks_type")
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert "KILLED" in out and "STAYED GREEN" in out
    assert digest(project / "product.py") == before
    assert (project / "product.py").stat().st_mtime_ns == mtime


def test_the_mutant_never_shares_a_whole_second_mtime_with_the_original(project, monkeypatch):
    # Python's bytecode cache (and others) trust mtime-to-the-second plus size.
    # A same-size mutant in the same second as a cached original would run the
    # original code, and every keeper would "survive". Record what the test
    # command sees, since a natural collision cannot be forced from here.
    monkeypatch.chdir(project)
    product = project / "product.py"
    original = product.stat().st_mtime_ns
    seen = project / "seen"
    probe = f"import os; open({str(seen)!r}, 'w').write(str(os.stat({str(product)!r}).st_mtime_ns))"
    main(
        [
            "--file", str(product), "--find", "return 0", "--replace", "return 1",
            "--junit", str(project / "junit.xml"), "--expect-fail", "x", "--no-control",
            "--", sys.executable, "-c", probe,
        ]
    )  # fmt: skip
    assert int(seen.read_text()) // 10**9 != original // 10**9
    assert product.stat().st_mtime_ns == original


def test_a_keeper_that_misses_the_break_survives(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    code = run(project, "return qty * 2", "return qty * 3", ("fail", "test_cut_only_checks_type"))
    assert code == 1
    assert "SURVIVED" in capsys.readouterr().out


def test_a_harness_failure_is_not_a_kill(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    code = run(project, "return 0", "return 1", ("fail", "test_harness_style_failure"))
    assert code == 2
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_a_timeout_in_the_traceback_of_a_real_assertion_is_still_a_kill(project, monkeypatch, capsys):
    # Playwright's expect.poll fails with an assertion headline and a call log
    # that says "Timeout 60000ms exceeded". Judging the whole text called that
    # harness noise on a real suite; only the headline decides.
    monkeypatch.chdir(project)
    code = run(project, "return 0", "return 1", ("fail", "test_polled_assertion_times_out"))
    assert code == 0, capsys.readouterr().out


def test_a_name_that_matches_nothing_is_inconclusive(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    code = run(project, "return 0", "return 1", ("fail", "no_such_test"), control=False)
    assert code == 2


def test_find_must_occur_exactly_once(project, monkeypatch):
    monkeypatch.chdir(project)
    before = digest(project / "product.py")
    with pytest.raises(SystemExit, match=r"occurs \d+ times"):
        run(project, "qty", "n", ("fail", "test_keeper_pins_zero"))
    assert digest(project / "product.py") == before


def test_file_is_restored_when_the_command_times_out(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setenv("MUTATION_CHECK_SLEEP", "1")
    before = digest(project / "product.py")
    code = run(project, "return 0", "return 1", ("fail", "test_sleeps"), timeout=5, control=False)
    assert code == 2
    assert digest(project / "product.py") == before


def test_a_keeper_already_failing_on_real_code_stops_the_run(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    (project / "product.py").write_text(PRODUCT.replace("qty * 2", "qty * 5"))
    before = digest(project / "product.py")
    code = run(project, "return 0", "return 1", ("fail", "test_keeper_pins_zero"))
    assert code == 2
    assert "Control failed" in capsys.readouterr().err
    assert digest(project / "product.py") == before
