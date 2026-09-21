---
name: sandboxed-execution
description: |
  Choose an OS-enforced sandbox for running code you do not trust, then prove the
  sandbox actually holds before running anything in it. Use whenever you are about
  to execute, build, install, or test something whose contents you have not
  verified: a contributor's branch or fork PR, a dependency you are auditing, a
  downloaded binary or archive, a devcontainer or Dockerfile from a repo, a
  proof-of-concept, or fixture input during a security review. Also use when a
  workflow tells you it needs "no external network", "read-only target",
  "scratch-only writes" or resource limits and you have to build that. Covers
  picking between a plain container and a full isolated VM, the fetch-then-cut
  pattern for code that must download before it runs, proving each control with a
  probe that could fail, and getting evidence back out safely. On this Mac the VM
  mechanism is OrbStack.
---

# Sandboxed execution

Running untrusted code needs a boundary the kernel enforces, not a promise. This
skill covers picking the weakest boundary that is still sufficient, proving it,
and getting results back out.

The single most common failure is not a weak sandbox. It is a sandbox nobody
checked, or a probe that reported success because it was broken. Budget as much
effort for proving the boundary as for building it.

## Pick the weakest sufficient boundary

**Default: a plain container with no network.**

```bash
timeout 600 docker run --rm \
  --network none \
  --read-only \
  --env-file /dev/null \
  --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
  --cpus 2 --memory 2g --memory-swap 2g --pids-limit 256 --ulimit fsize=104857600 \
  -v /abs/path/to/target:/target:ro \
  --tmpfs /scratch:rw,size=512m,nosuid,nodev \
  -w /scratch <image> <command>
```

`--network none` gives a fresh network namespace with only `lo`, which is the
strongest and cheapest control here. This covers almost everything: running a
test suite, parsing a hostile fixture, building a library, inspecting a
dependency.

**Escalate to an isolated VM only when the thing under test needs a container
runtime of its own** - building a devcontainer, running docker-in-docker,
testing a Dockerfile, or anything that needs its own kernel-level state. You
cannot nest that inside `--network none` cleanly, so you need a machine.

On this Mac that is OrbStack:

```bash
orb create --isolated --isolate-network --cpus 4 --memory 6G --disk 40G ubuntu:noble <name>
```

`--isolated` drops `/mnt/mac` and host integration. Measured: `mac` and `macctl`
remain on `PATH` but fail with `dial: no such file or directory`, and
`host.orb.internal` resolves while answering on nothing.

Escalating costs real time and adds the failure modes below, so do not reach for
it when a container would do.

## `--isolate-network` is not "no network"

This is the trap that matters most, because the flag name invites the wrong
reading. It blocks other machines and host IPs **while keeping internet access**.
Measured on this Mac: an `--isolate-network` machine could still ping a Tailscale
peer on the user's tailnet.

If your workflow requires no external network, add a firewall inside the guest
and verify it:

```bash
nft delete table inet audit 2>/dev/null
nft add table inet audit
nft add chain inet audit output '{ type filter hook output priority 0; policy drop; }'
nft add rule inet audit output oif lo accept
nft add rule inet audit output ip daddr 172.16.0.0/12 accept   # docker bridge only
```

**Never run `nft flush ruleset`.** It deletes Docker's own NAT chains along with
yours, container DNS dies, and flushing again does not bring it back. Manage only
your own table, or recover with `systemctl restart docker`. This cost a full
measurement run.

## Fetch-then-cut, when the target must download first

Some things cannot run offline at all: a devcontainer build, a dependency
install, a toolchain that fetches a runtime on first use. Running them with the
network up violates the usual rule, and refusing outright means measuring
nothing.

Split it in time instead, and say so in your write-up:

1. **Fetch phase.** Network up. Pull images by digest, install dependencies, let
   package managers populate caches. No conclusions are drawn here.
2. **Freeze.** Capture what was fetched so it survives without the network.
   A named volume keeps a directory; `docker commit` keeps everything, which is
   what you need when the runtime lives inside the image's own prefix.
3. **Cut.** Apply the firewall, then prove it is gone (below).
4. **Measure.** Everything you will actually report happens here, offline.

Get explicit approval before the fetch phase if the governing workflow forbids
network during execution, and record the deviation with its reason.

## Prove every control, with a probe that could fail

A probe that cannot fail proves nothing. Every control needs a positive case and
a negative case, and you should be able to say which result would have told you
the sandbox was broken.

`scripts/verify-sandbox.py` runs the standard set. Read it before trusting it;
it is short on purpose.

```bash
python3 scripts/verify-sandbox.py --mode docker --image <image>
python3 scripts/verify-sandbox.py --mode orb --machine <name>
```

The checks that matter, and the control for each:

| Control | Probe | Control that could fail |
| --- | --- | --- |
| No external network | resolve and connect to a public host | a loopback listener still answers |
| Host unreachable | connect to the host across several ports | loopback still answers |
| Read-only target | write into the mounted target | write into scratch succeeds |
| Scratch-only writes | write outside scratch | write inside scratch succeeds |
| Memory limit | allocate past the cap | a smaller allocation succeeds |
| Process limit | fork past the cap | a few processes succeed |

Two failures from real runs, both of which looked like success:

- A "loopback still works" control ran when nothing was listening, so it reported
  *closed* and proved nothing. Bind a listener first, then connect.
- An HTTP probe dialled `127.0.0.1` against a server bound to `::1` and returned
  `ECONNREFUSED` for every case, which read as "everything is denied". Dial the
  address the server actually bound, and always include a request that must
  succeed.

When a control fails, suspect the instrument before the target. A `devcontainer
build` inside a VM whose Docker is overlay-on-overlay dies with dpkg `unable to
install ... Invalid cross-device link` on gnupg packages. That is nested
storage, not a defect in what you are testing. A control that fails for its own
reason can still separate two cases if they diverge earlier than the failure -
say so explicitly rather than discarding the run.

## Getting evidence back out

Treat anything the sandbox wrote as hostile data. Promote named files rather than
copying directories, and never follow a symlink out.

Python is the right tool because it exposes real directory-relative, no-follow
opens; Node has no `openat`. Verified present here: Python 3.14 with
`os.O_NOFOLLOW` and `dir_fd` support.

The shape: open the scratch root and the destination root as directory
descriptors and keep them; for each allowlisted relative path, open no-follow
from the scratch descriptor, `fstat` it and require a regular file with link
count 1 within an explicit byte bound, read exactly that many bytes, `fstat`
again and reject any change, then create the destination no-follow and
exclusively. Never reopen by path.

From an OrbStack machine, the Mac can also read `~/OrbStack/<machine>/...`
directly, which is convenient but is still sandbox-authored content: apply the
same care.

## Gotchas that cost time

- **`su <user> -c` resets `PATH`.** An image whose tooling lives in a
  non-standard prefix then reports `command not found`, which reads as a broken
  image. Use `docker run --user <user>` so the image's own `ENV PATH` applies.
- **Mounting a volume over the image's tool prefix blanks it.** If you need a
  fetched runtime to persist, `docker commit` the prepped container instead of
  mounting a volume over the directory that holds it.
- **A disposable copy beats a read-only mount when the target must be
  writable.** Some builds insist on writing beside their source. Copy the target
  into the sandbox (`git archive` is a clean way) and never expose the
  authoritative checkout. Verify afterwards that the real one is untouched.
- **Clean up.** Delete the machine, container and volumes once evidence is
  promoted, and record the commands needed to rebuild it.

## When you cannot enforce every control

Do not run the code. Report which specific control is missing and give a
validation plan the owner can run instead. A partial sandbox that is described
as complete is worse than no sandbox, because the results get believed.
