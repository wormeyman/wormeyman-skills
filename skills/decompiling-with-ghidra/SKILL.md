---
name: decompiling-with-ghidra
description: Use when reading a compiled binary as C with Ghidra - decompiling a function, checking how a game or program branches, or answering "what does this function do" from a binary. Built for large binaries that ship debug info (DWARF), such as Factorio's Linux headless builds, where Ghidra's default analysis runs for hours. Also use when Ghidra, analyzeHeadless, PyGhidra, Jython, REA or a Ghidra skill or MCP comes up, when a Ghidra run is slow or its C is full of undefined/param_N/in_RDI, or when an objdump address does not match Ghidra's. Covers the 4-minute debug-info-only import, the PIE address shift, argument types from C++ mangled names, the GUI steps, and when objdump is the better tool.
---

# Decompiling with Ghidra

Turn a function in a big binary into readable C in minutes, not hours. Everything here
was measured on Factorio's 257 MB Linux headless binary (free to download, ships
DWARF) on an 8-core, 31 GiB Linux desktop, 2026-11-12.

## First: is Ghidra the right tool?

- **For constants and data, use `objdump` + the debug info instead.** `objdump -d -l -C
  --start-address --stop-address` plus `llvm-symbolizer --inlining` found every noise
  constant in about 2 minutes. Ghidra adds nothing there.
- **For control flow - "which branch wins", "what order are checks done" - use Ghidra.**
  Reading branches out of raw assembly is slow and error-prone; the C shows them directly.

## What it covers

Nothing here is specific to Factorio; it is just where the numbers come from. What
matters is the binary. Check it with `file <bin>` (`with debug_info, not stripped`) or
`readelf -S <bin> | grep debug_info`.

| Binary | Fit |
|---|---|
| Linux ELF with DWARF, C or C++ | The case this was built for: fast import, names, types |
| Linux ELF with symbols, no DWARF | Untested. Names and C++ signatures should still come from the symbol table, with no types |
| Stripped ELF | Poor. Use `import --full-analysis` so Ghidra finds functions itself, and expect it to be slow on a big binary |
| Windows PE | Not covered: debug info is a separate PDB, and names need Ghidra's Microsoft demangler |
| macOS Mach-O | Not covered: debug info usually sits in a separate `.dSYM` the script does not load |

The address shift and the disassemble step apply to any ELF. Signatures from mangled
names apply to C++ only; plain C names carry no types.

## The one setting that matters

Ghidra's default analysis runs about 30 analyzers over every function. On the Factorio
binary that ran **past 2 hours without finishing** (16 GB heap). Turning everything off
except **DWARF** and **Demangler GNU** finished in **4-6 minutes** with about 3 GB of
heap. Skipping analysis entirely (`-noanalysis`) is fast but gives useless C: no names,
no types, 9,522 lines for a 2.7 KB function.

## Command line (preferred): `scripts/ghidra_decompile.py`

A PyGhidra script run by uv. It needs Ghidra 12.x (Arch package `ghidra`, which ships
PyGhidra) and Java 25+. The script's header pins the pyghidra wheel from
`/opt/ghidra`; edit it if Ghidra lives elsewhere.

```bash
S=~/.claude/skills/decompiling-with-ghidra/scripts/ghidra_decompile.py
$S import  <binary> <project_dir>               # once per binary version, ~4-6 min
$S find    <project_dir> 'Surface::collide'     # names -> file + Ghidra addresses
$S decompile <project_dir> 0x18eea40 'Surface::collideWithEntity' --out <dir>
```

- Keep the project directory (about 2 GB). Every later `find`/`decompile` opens it in
  ~15 s, so the import cost is paid once per binary version. Name it after the version,
  e.g. `~/ghidra-projects/factorio-2.1.23`.
- `decompile` takes **file addresses** (what objdump/readelf print) or full demangled
  names, and shifts addresses for you. Several targets in one call share one start-up.
- Each output `.c` starts with a header: both addresses, the signature used, and how
  many callee signatures were fixed. Read it.
- `--save` keeps the disassembly and signature fixes in the project, which helps if
  someone will open it in the GUI later.
- Run it from a scratch directory, and send `--out` there too.

## Three traps, and what the script does about each

1. **Addresses are shifted for PIE binaries.** Ghidra loads a position-independent
   ELF at `0x100000`, so objdump's `0x24f4370` is Ghidra's `0x25f4370`. Going to the
   objdump address lands in the middle of some other function, and pressing F there
   makes a fake one. The script reads `ELF Original Image Base` and shifts for you; in
   the GUI, add the shift yourself.
2. **DWARF-only analysis names functions but does not disassemble them.** In the
   listing they show as raw bytes (`?? 55h`). The script disassembles from the entry
   point; in the GUI press **D** on the first byte (not F - the function exists).
3. **Arguments come through as `void f(void)`.** On this binary Ghidra could not use
   the debug info's register locations (the `DW_OP_reg*` list in the import summary),
   so every function lost its parameters, and the C fills with `in_RDI`, `in_RSI`,
   `extraout_RAX`. The DWARF options `Default Calling Convention` and `Ignore
   Parameter Storage Info` did not fix it (tested). What works: apply the signature
   the C++ mangled name spells out, then add `this` for methods (Ghidra has no x86-64
   `__thiscall`). The script does this for the function and its callees. One gap
   remains: mangled names carry no return type, so a struct returned by value shows up
   as an extra first pointer argument and shifts the parameter names after it.

## Reading the C

- **Calibrate first.** Before trusting C for an open question, decompile one function
  whose behaviour is already known (from notes, a test, or the oracle) and check that
  the C says the same. On 2026-11-12, `generateEntities` showed exactly the compare the
  notes had read by hand, which is what made `Surface::collide` worth reading.
- The C is evidence about the code, not about which path the game runs. Confirm with a
  measurement where it matters.
- Harmless noise: `DuplicateNameException: codecvt already exists` while importing,
  a `DWARFImportSummary` ERROR list of unrecoverable location expressions, and
  "Control flow encountered bad instruction data" near the end of a function (usually
  just the cleanup and return get cut).
- Offsets like `this + 0x24` are struct fields Ghidra has no layout for. The debug info
  often lacks class layouts too (checked for the noise operations). Name what you
  learn in your notes, not by guessing types.

## GUI steps (for a person at the desktop)

1. Start Ghidra. Its heap defaults to a quarter of RAM (7.8 GiB on a 31 GiB box), which was
   enough. To raise it, add `GHIDRA_GUI_MAXMEM=16G` under Environment variables in the
   KDE menu editor (right-click Ghidra, Edit Application). Keep it well under free RAM.
2. File, New Project, Non-Shared. File, Import File, pick the binary (about 50 s).
3. Open it. When asked "Analyze?", click Yes, then **Deselect All**, then check only
   **DWARF** and **Demangler GNU**. Analyze (4-5 min). **Ctrl+S** right away.
4. Press **G**, type the Ghidra address (file address + shift) or use the Symbol Tree
   filter. Press **D** on the first byte if it shows `??`. **Ctrl+E** opens the
   Decompiler if it is closed. Save again.

A person can drive the GUI while Claude watches with screenshots (`spectacle
--background --fullscreen --nonotify --output <png>`, with `WAYLAND_DISPLAY` set to the
session's socket in `$XDG_RUNTIME_DIR`). The command line is faster for the agent itself.

## Ruled out (2026-11-12) - do not re-test without a new reason

- **REA** (`morluto/rea`): waits for Ghidra's full default analysis before answering
  and does not change analyzer settings, so it never got past the 2-hour analysis.
  6.9.0 added an opt-in checkpoint, but still runs the full analysis first.
- **skills.sh Ghidra skills** (mitsuhiko `ghidra`, trailofbits `ghidra-headless`, the
  zhaoxuya520 one): wrappers around the default analysis with a timeout, and none of
  them knows the three traps above.
- **Jython**: Python 2.7, only an optional extension in Ghidra 12. Use PyGhidra.
- **Java GhidraScripts via analyzeHeadless** (a pre-script that sets the analyzers and a
  post-script that decompiles) work, but cost 30-60 s of start-up per run, and Ghidra
  refuses a script that has a copy in a parent folder with a misleading
  `Failed to find source bundle containing script`.
- Worth a look later: **ReVa** (`cyberkaida/reverse-engineering-assistant`), an MCP
  server inside a running Ghidra, for working live in a session instead of batches.

## Python and machine notes

- The script caps Python below 3.15 because JPype (PyGhidra's bridge to Java) had no
  3.15 wheel; uv otherwise picks 3.15 and fails building JPype (it needs Apache Ant).
- Installing Ghidra needs sudo, so the user types the password; the
  `getting-command-output` skill covers doing that in a logged tmux window.
- The import is the only heavy step, so run it on the fastest machine available. The
  finished project folder can be copied to another machine and opened as is.
