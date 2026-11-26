#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Break one line of product code on purpose, run the tests, and put it back.

This is the proof behind every cut: the test you keep must pass on the real
code and fail on the broken code, and the test you cut is shown to add
nothing. It works with any runner that can write JUnit XML, which covers
browser suites (Playwright) where coverage and mutation tools cannot reach.

  uv run mutation_check.py --file src/cart.ts \\
      --find 'if (qty > 0)' --replace 'if (qty >= 0)' \\
      --junit results.xml \\
      --expect-fail 'rejects an empty cart' \\
      --expect-pass 'cart total is a number' \\
      -- npx playwright test tests/cart.spec.ts --reporter=junit

The command must write its JUnit report to the --junit path (Playwright:
PLAYWRIGHT_JUNIT_OUTPUT_NAME=results.xml; Vitest: --reporter=junit
--outputFile=results.xml; pytest: --junitxml=results.xml).

Each expectation is reported as one of:

  KILLED        expected to fail, and failed on its own assertion
  SURVIVED      expected to fail, and passed: it does not catch this break
  STAYED GREEN  expected to pass, and passed (a cut test that adds nothing)
  FAILED        expected to pass, and failed: it catches this break too
  INCONCLUSIVE  failed on a timeout or setup error, was skipped, or did not
                run. Neither a kill nor a survival.

The file is restored from the bytes read at the start, in a finally block,
and the script checks the restored file's SHA-256 matches. Exit codes: 0 every
expectation met, 1 one or more not met, 2 inconclusive or a usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# A failure whose headline matches one of these is the harness, not the test's
# own assertion: the page never loaded, a server was down, a hook timed out.
# Counting it as a kill turns a broken environment into a clean bill of health.
#
# Only the headline is checked (JUnit's `message`, else the first line). The
# body is a traceback and call log, and a polled assertion that ran out of time
# (Playwright's expect.poll) logs "Timeout 60000ms exceeded" under a headline
# of `expect(received).not.toBe(expected)`: that is the assertion failing.
ASSERTION_HEADLINE = re.compile(r"^\s*(?:Error:\s*)?(?:expect\(|AssertionError|assert\b|expected\b)", re.IGNORECASE)
HARNESS_PATTERNS = [
    r"\bTimeout\b.*\bexceeded\b",
    r"\bTimeoutError\b",
    r"\btimed out\b",
    r"ECONNREFUSED",
    r"net::ERR_",
    r"\bbeforeAll\b|\bbeforeEach\b|\bglobalSetup\b",
    r"Target page, context or browser has been closed",
    r"\bfixture\b.*\berror\b",
    r"ModuleNotFoundError|Cannot find module",
    r"SyntaxError",
]


@dataclass
class Case:
    name: str
    status: str  # passed, failed, skipped
    message: str  # headline plus body, whitespace collapsed, for display
    headline: str = ""  # what the failure is, without the traceback


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_junit(path: Path) -> list[Case]:
    # The stdlib parser is enough here: the report is written by the user's own
    # test command on their own machine, and expat (2.4.1+) caps entity
    # expansion. Keeping it stdlib keeps the script free of dependencies.
    cases = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        name = " ".join(filter(None, [tc.get("classname"), tc.get("name")]))
        problem = tc.find("failure")
        if problem is None:
            problem = tc.find("error")
        if problem is not None:
            body = problem.text or ""
            first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
            raw = (problem.get("message") or first).strip()
            headline = raw.splitlines()[0] if raw else ""
            text = " ".join(filter(None, [problem.get("message"), body]))
            cases.append(Case(name, "failed", " ".join(text.split()), headline))
        elif tc.find("skipped") is not None:
            cases.append(Case(name, "skipped", ""))
        else:
            cases.append(Case(name, "passed", ""))
    return cases


def run_tests(command: list[str], junit: Path, timeout: int) -> tuple[int, list[Case] | None, str]:
    """Run the command once. Returns (exit code, cases or None, tail of output)."""
    junit.unlink(missing_ok=True)  # never read a report left over from an earlier run
    try:
        proc = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        code, out = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return 124, None, f"command timed out after {timeout} s"
    if not junit.is_file():
        return code, None, out[-2000:]
    try:
        return code, read_junit(junit), out[-2000:]
    except ET.ParseError as err:
        return code, None, f"could not parse {junit}: {err}"


def matching(cases: list[Case], needle: str) -> list[Case]:
    return [c for c in cases if needle in c.name]


def is_harness(case: Case, extra: list[str]) -> bool:
    if ASSERTION_HEADLINE.search(case.headline):
        return False
    return any(re.search(p, case.headline, re.IGNORECASE) for p in HARNESS_PATTERNS + extra)


def judge(cases: list[Case] | None, needle: str, expect_fail: bool, extra: list[str]) -> tuple[str, str]:
    if cases is None:
        return "INCONCLUSIVE", "no JUnit report"
    found = matching(cases, needle)
    if not found:
        return "INCONCLUSIVE", "no test name contains this text"
    if any(c.status == "skipped" for c in found) and not any(c.status == "failed" for c in found):
        return "INCONCLUSIVE", "skipped"
    failed = [c for c in found if c.status == "failed"]
    if expect_fail:
        if not failed:
            return "SURVIVED", f"{len(found)} matching test(s) passed"
        own = [c for c in failed if not is_harness(c, extra)]
        if own:
            return "KILLED", own[0].headline[:160]
        return "INCONCLUSIVE", "failed on the harness: " + failed[0].headline[:140]
    if failed:
        return "FAILED", failed[0].headline[:160]
    return "STAYED GREEN", f"{len(found)} matching test(s) passed"


def mutate(path: Path, find: str, replace: str) -> bytes:
    """Return the mutated bytes. Refuses unless `find` occurs exactly once."""
    original = path.read_bytes()
    text = original.decode("utf-8")
    count = text.count(find)
    if count != 1:
        raise SystemExit(f"--find occurs {count} times in {path}; it must occur exactly once")
    if find == replace:
        raise SystemExit("--find and --replace are the same; that is not a mutation")
    return text.replace(find, replace, 1).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, type=Path, help="product file to break")
    ap.add_argument("--find", required=True, help="exact text to replace; must occur once")
    ap.add_argument("--replace", required=True, help="the broken version")
    ap.add_argument("--junit", required=True, type=Path, help="where the command writes JUnit XML")
    ap.add_argument(
        "--expect-fail",
        action="append",
        default=[],
        metavar="TEXT",
        help="a kept test that must catch the break (substring of its name); repeatable",
    )
    ap.add_argument(
        "--expect-pass",
        action="append",
        default=[],
        metavar="TEXT",
        help="a test being cut, expected to stay green; repeatable",
    )
    ap.add_argument(
        "--harness-pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="extra regex marking a failure as harness, not assertion",
    )
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per run (default 1800)")
    ap.add_argument(
        "--no-control", action="store_true", help="skip the run on unbroken code that shows the kept tests pass first"
    )
    ap.add_argument("command", nargs=argparse.REMAINDER, help="test command, after --")
    args = ap.parse_args(argv)

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("give the test command after --")
    if not args.expect_fail and not args.expect_pass:
        ap.error("give at least one --expect-fail or --expect-pass")

    path = args.file
    original = path.read_bytes()
    before = sha256(original)
    mutated = mutate(path, args.find, args.replace)
    verdict_ok, inconclusive = True, False

    if not args.no_control:
        # The kill criterion has two sides: a keeper that already fails on the
        # real code proves nothing when it fails on the broken code.
        _, cases, tail = run_tests(command, args.junit, args.timeout)
        print("control run (unbroken code):")
        for needle in args.expect_fail + args.expect_pass:
            v, why = judge(cases, needle, expect_fail=False, extra=args.harness_pattern)
            ok = v == "STAYED GREEN"
            print(f"  {'ok  ' if ok else 'BAD '} {needle}: {'passes' if ok else v + ' - ' + why}")
            if not ok:
                print("Control failed: fix the baseline before trusting any mutation.", file=sys.stderr)
                if cases is None:
                    print(tail, file=sys.stderr)
                return 2

    # Caches that trust a file's mtime and size (Python bytecode, for one) would
    # run the old code if a same-size mutation lands in the same second as the
    # control run. So the mutant gets an mtime 2 s later, and the restore puts
    # the original mtime back, which a mutant-era cache entry cannot match.
    stat = path.stat()
    try:
        path.write_bytes(mutated)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
        code, cases, tail = run_tests(command, args.junit, args.timeout)
    finally:
        path.write_bytes(original)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    after = sha256(path.read_bytes())
    if after != before:
        print(f"RESTORE FAILED: {path} sha256 {after} != {before}", file=sys.stderr)
        return 2

    print(f"mutated run: {path}  ({args.find!r} -> {args.replace!r}), exit {code}")
    for needle, want_fail in [(n, True) for n in args.expect_fail] + [(n, False) for n in args.expect_pass]:
        v, why = judge(cases, needle, want_fail, args.harness_pattern)
        print(f"  {v:<13} {needle}  [{why}]")
        if v == "INCONCLUSIVE":
            inconclusive = True
        elif v not in ("KILLED", "STAYED GREEN"):
            verdict_ok = False

    if cases:
        failed = [c for c in cases if c.status == "failed"]
        if len(cases) >= 3 and len(failed) == len(cases) and len({c.headline[:80] for c in failed}) == 1:
            print(
                "warning: every test failed with the same message. Suspect the environment, "
                "not the mutation, and read one failure in full.",
                file=sys.stderr,
            )
    elif cases is None:
        print(tail, file=sys.stderr)
    print(f"restored {path} (sha256 {after[:12]}, unchanged)")

    if inconclusive:
        return 2
    return 0 if verdict_ok else 1


if __name__ == "__main__":
    sys.exit(main())
