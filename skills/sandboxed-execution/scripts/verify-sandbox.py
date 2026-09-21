#!/usr/bin/env python3
"""Probe a sandbox's controls and report which ones are actually enforced.

Every check has a control that could fail. A probe on its own proves nothing:
"connection refused" looks identical whether the network is blocked or nothing
was listening, and both of those happened during the session this came from.
So each control is reported as HELD, BROKEN, or INCONCLUSIVE, and INCONCLUSIVE
is a real answer - it means the probe could not distinguish the two cases.

  python3 verify-sandbox.py --mode docker --image alpine
  python3 verify-sandbox.py --mode orb --machine my-sandbox
"""
import argparse
import shlex
import subprocess
import sys

TIMEOUT = 60


def run(cmd, timeout=TIMEOUT):
    """Return (exit_code, combined_output). A timeout is exit code 124, as in timeout(1)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "(timed out)"
    except FileNotFoundError as e:
        return 127, str(e)


class Report:
    def __init__(self):
        self.rows = []

    @staticmethod
    def _flat(text):
        return " ".join(str(text).split()) or "(no output)"

    def add(self, control, verdict, probe, ctrl):
        self.rows.append((control, verdict, self._flat(probe), self._flat(ctrl)))

    def judge(self, control, probe_denied, control_allowed, probe_detail, control_detail):
        """probe_denied: the unsafe thing was refused. control_allowed: the safe thing worked."""
        if probe_denied and control_allowed:
            verdict = "HELD"
        elif not probe_denied:
            verdict = "BROKEN"
        else:
            verdict = "INCONCLUSIVE"
        self.add(control, verdict, probe_detail, control_detail)

    def print(self):
        width = max(len(r[0]) for r in self.rows)
        print()
        for control, verdict, probe, ctrl in self.rows:
            mark = {"HELD": "ok  ", "BROKEN": "FAIL", "INCONCLUSIVE": "??  "}[verdict]
            print(f"  [{mark}] {control.ljust(width)}  {verdict}")
            print(f"           probe:   {probe}")
            print(f"           control: {ctrl}")
        broken = [r[0] for r in self.rows if r[1] == "BROKEN"]
        unclear = [r[0] for r in self.rows if r[1] == "INCONCLUSIVE"]
        print()
        if broken:
            print(f"  NOT SAFE TO RUN UNTRUSTED CODE. Broken: {', '.join(broken)}")
        if unclear:
            print(f"  Could not prove: {', '.join(unclear)}. Treat as not enforced.")
        if not broken and not unclear:
            print("  Every control probed held, each against a control that could have failed.")
        return 1 if (broken or unclear) else 0


def check_docker(image, report):
    base = ["docker", "run", "--rm", "--network", "none", "--read-only",
            "--env-file", "/dev/null", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "256m", "--memory-swap", "256m", "--pids-limit", "32",
            "--tmpfs", "/scratch:rw,size=32m,nosuid,nodev", "-w", "/scratch"]

    # Network: an outbound connection must fail while loopback still works.
    rc_out, out = run(base + [image, "sh", "-c",
                              "getent hosts example.com >/dev/null 2>&1 && echo RESOLVED || echo NO_DNS"])
    rc_lo, lo = run(base + [image, "sh", "-c",
                            "(nc -l -p 9999 -e /bin/true &) 2>/dev/null; sleep 1; "
                            "nc -z 127.0.0.1 9999 >/dev/null 2>&1 && echo LO_OK || echo LO_DOWN; "
                            "ip link show lo >/dev/null 2>&1 && echo HAS_LO || echo NO_LO"])
    report.judge("no external network",
                 probe_denied="NO_DNS" in out,
                 control_allowed="HAS_LO" in lo or "LO_OK" in lo,
                 probe_detail=f"resolve example.com -> {out or '(no output)'}",
                 control_detail=f"loopback present -> {lo or '(no output)'}")

    # Filesystem: root read-only, scratch writable.
    rc, fs = run(base + [image, "sh", "-c",
                         "touch /nope 2>/dev/null && echo ROOT_WRITABLE || echo ROOT_RO; "
                         "touch /scratch/ok 2>/dev/null && echo SCRATCH_OK || echo SCRATCH_RO"])
    report.judge("read-only root, writable scratch",
                 probe_denied="ROOT_RO" in fs,
                 control_allowed="SCRATCH_OK" in fs,
                 probe_detail=f"touch / -> {'refused' if 'ROOT_RO' in fs else 'SUCCEEDED'}",
                 control_detail=f"touch /scratch -> {'ok' if 'SCRATCH_OK' in fs else 'refused'}")

    # Memory: a large allocation dies, a small one does not. `tail -c <n>` has to
    # buffer n bytes, so this really allocates. An earlier version of this probe
    # piped into `tail -c 1`, which streams and holds a single byte: it allocated
    # nothing, every run exited 0, and it reported a working limit as BROKEN.
    rc_big, _ = run(base + [image, "sh", "-c",
                            "head -c 536870912 /dev/zero | tail -c 536870912 >/dev/null"])
    rc_small, _ = run(base + [image, "sh", "-c",
                              "head -c 8388608 /dev/zero | tail -c 8388608 >/dev/null"])
    report.judge("memory limit",
                 probe_denied=rc_big != 0,
                 control_allowed=rc_small == 0,
                 probe_detail=f"buffer 512 MiB against a 256m cap -> exit {rc_big}",
                 control_detail=f"buffer 8 MiB -> exit {rc_small}")

    # Environment: nothing inherited from the host.
    rc, env = run(base + [image, "sh", "-c", "env | wc -l; env | grep -c '^HOME=' || true"])
    report.add("empty environment", "HELD" if rc == 0 else "INCONCLUSIVE",
               f"env var count inside: {env.splitlines()[0] if env else '?'}",
               "--env-file /dev/null passes nothing from the host; image ENV still applies")


def check_orb(machine, report):
    def guest(script, timeout=TIMEOUT):
        return run(["orb", "-m", machine, "sh", "-c", script], timeout=timeout)

    rc, mnt = guest("test -e /mnt/mac && echo MNT_MAC || echo NO_MNT_MAC; "
                    "timeout 8 mac uname >/dev/null 2>&1 && echo MAC_WORKS || echo MAC_DEAD")
    report.judge("host filesystem and host command",
                 probe_denied="NO_MNT_MAC" in mnt and "MAC_DEAD" in mnt,
                 control_allowed=rc == 0,
                 probe_detail=f"/mnt/mac and `mac` -> {mnt or '(no output)'}",
                 control_detail=f"the guest answered at all -> exit {rc}")

    # Egress must be gone while loopback still answers. Bind a listener so the
    # loopback control can actually succeed - without one it reports "closed"
    # and proves nothing, which is a mistake this script exists to prevent.
    rc, net = guest(
        "(python3 -m http.server 39997 --bind 127.0.0.1 >/dev/null 2>&1 &) ; sleep 2; "
        "timeout 5 bash -c '</dev/tcp/127.0.0.1/39997' 2>/dev/null && echo LO_OK || echo LO_DOWN; "
        "timeout 8 getent hosts example.com >/dev/null 2>&1 && echo DNS_UP || echo DNS_DOWN; "
        "pkill -f 'http.server 39997' 2>/dev/null; true")
    report.judge("no external network",
                 probe_denied="DNS_DOWN" in net,
                 control_allowed="LO_OK" in net,
                 probe_detail=f"resolve example.com -> {'blocked' if 'DNS_DOWN' in net else 'RESOLVED'}",
                 control_detail=f"loopback listener -> {'answered' if 'LO_OK' in net else 'no answer'}")

    rc, host = guest("timeout 6 ping -c1 -W3 host.orb.internal >/dev/null 2>&1 && echo PINGS || echo no_ping; "
                     "for p in 22 80 443; do timeout 3 bash -c \"</dev/tcp/host.orb.internal/$p\" "
                     "2>/dev/null && echo OPEN_$p; done; echo SWEPT")
    report.judge("macOS host unreachable",
                 probe_denied="PINGS" not in host and "OPEN_" not in host,
                 control_allowed="SWEPT" in host,
                 probe_detail=f"ping and ports 22/80/443 -> {host.replace(chr(10), ' ') or '(none)'}",
                 control_detail="the sweep ran to completion")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("docker", "orb"), required=True)
    ap.add_argument("--image", help="container image, for --mode docker")
    ap.add_argument("--machine", help="machine name, for --mode orb")
    args = ap.parse_args()

    report = Report()
    if args.mode == "docker":
        if not args.image:
            ap.error("--mode docker needs --image")
        print(f"Probing a container from {args.image} ...")
        check_docker(args.image, report)
    else:
        if not args.machine:
            ap.error("--mode orb needs --machine")
        print(f"Probing OrbStack machine {shlex.quote(args.machine)} ...")
        check_orb(args.machine, report)
    sys.exit(report.print())


if __name__ == "__main__":
    main()
