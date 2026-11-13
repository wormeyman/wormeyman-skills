---
name: decompiling-with-ghidra
description: Use when reading a compiled binary as C with Ghidra - decompiling a function, checking how a game or program branches, or answering "what does this function do" from a binary. Built for large binaries that ship debug info (DWARF), such as Factorio's Linux headless builds, where Ghidra's default analysis runs for hours. Also use when Ghidra, analyzeHeadless, PyGhidra, Jython, REA or a Ghidra skill or MCP comes up, when a Ghidra run is slow or its C is full of undefined/param_N/in_RDI, or when an objdump address does not match Ghidra's. Covers the 4-minute debug-info-only import, the PIE address shift, argument types from C++ mangled names, compiler clones, calls that never return, the GUI steps, and when objdump is the better tool.
---

# Decompiling with Ghidra

Turn a function in a big binary into readable C in minutes, not hours. The numbers
come from Factorio's 257 MB Linux headless binary (free to download, ships DWARF)
and from small test programs built with GCC 16 and clang, on Linux desktops with 8
and 16 threads, 2026-11-12 and 2026-11-13.

## First: is Ghidra the right tool?

- **For constants and data, use `objdump` + the debug info instead.** `objdump -d -l -C
  --start-address --stop-address` plus `llvm-symbolizer --inlining` found every noise
  constant in about 2 minutes. Ghidra adds nothing there.
- **For control flow - "which branch wins", "what order are checks done" - use Ghidra.**
  Reading branches out of raw assembly is slow and error-prone. The C shows them directly.

## What it covers

Nothing here is specific to Factorio. What matters is the binary. Check it with
`file <bin>` (`with debug_info, not stripped`) or `readelf -S <bin> | grep debug_info`.

| Binary | Fit |
|---|---|
| Linux ELF with DWARF, C or C++, 64-bit | The case this was built for: fast import, names, types |
| Same, 32-bit | Works, and GCC's register-passing clones are handled. `main` came out unreadable (its stack-aligning start confuses Ghidra); other functions were fine |
| Linux ELF with symbols, no DWARF | Logic right, names right, argument types from C++ names. Fields show as raw offsets like `this + 8`. A static method gets a fake `this` (the header warns) |
| Stripped ELF | `FUN_00101540` names, no types, and `find` finds nothing, not even `main`. Pass addresses from objdump. Logic was still right on a small test |
| Windows PE | Not covered: debug info is a separate PDB, and names need Ghidra's Microsoft demangler |
| macOS Mach-O | Not covered: debug info usually sits in a separate `.dSYM` the script does not load |

Signatures from mangled names apply to C++ only. Plain C names carry no types.

## The one setting that matters

Ghidra's default analysis runs about 30 analyzers over every function. On the Factorio
binary that ran **past 2 hours without finishing** (16 GB heap). The script turns off
everything except **DWARF**, **Demangler GNU** and **Apply Data Archives** (which gives
`strlen`, `printf` and other C library calls their arguments). That finished in **4-6
minutes** on an 8-core i7-6700 and in about 2.5 on a 16-thread i5-14400F, with about
3 GB of heap. Skipping analysis entirely (`-noanalysis`) is fast but gives useless C: no
names, no types, 9,522 lines for a 2.7 KB function.

## Command line (preferred): `scripts/ghidra_decompile.py`

A PyGhidra script run by uv. It needs Ghidra 12.x (Arch package `ghidra`, which ships
PyGhidra), Java 25 or newer, and `llvm-dwarfdump` (package `llvm`) for one check. The
script's header pins the pyghidra wheel from `/opt/ghidra`. Edit it if Ghidra lives
elsewhere.

```bash
S=~/.claude/skills/decompiling-with-ghidra/scripts/ghidra_decompile.py
$S import  <binary> <project_dir>               # once per binary version, ~2.5-6 min
$S find    <project_dir> 'Surface::collide'     # names -> file + Ghidra addresses
$S decompile <project_dir> 0x18eea40 'Surface::collideWithEntity' --out <dir>
```

- **Import into a new, empty folder**, one per binary, named after the version (for
  example `~/ghidra-projects/factorio-2.1.23`). Keep it: it is about 1.1 GB, and every
  later `find` or `decompile` opens it in about 15 s. Import refuses a folder that
  already holds a project, and a file that is not ELF. If import fails, it removes the
  folder it made.
- **One run per project at a time.** Ghidra locks the project, and an open Ghidra GUI
  counts. A second run stops with "is locked". Wait for the first, then retry.
- `decompile` takes **file addresses** (what objdump and readelf print), names as
  `find` prints them, or mangled names. It shifts addresses for you. Namespaces can be
  left off when the short name is unique (`pick` for `(anonymous_namespace)::pick`).
  Several targets in one call share one start-up.
- **Bad targets are skipped, not guessed.** An address in the middle of a function is
  refused with the real start ("inside X, which starts at file 0x..."). So is an
  address outside code (for example in `.rodata`), bad hex, an unknown name, and a name
  that fits several functions (overloads, thunks), which lists them all. The rest of the
  batch still runs, and the exit code is 1. Read the `SKIPPED` lines.
- Each output is `<name>@<file address>.c`, so overloads do not overwrite each other.
- `find` lists functions in the binary only. Marks: `[clone .isra.0]`, `[thunk]`,
  `[PLT stub for an import]` and `[arguments changed by clang]`. Each line ends with the
  mangled name, which tells overloads apart. With no match it says so.
- `--save` keeps the disassembly and signature changes in the project, which helps
  if someone will open it in the GUI later. Without it the project is not changed.
- To check the skill on a new machine or Ghidra version, build a small C++ program
  with `g++ -O2 -g`, without `-g`, and stripped, and compare the C with the source.
- Run it from a scratch directory, and send `--out` there too.

### The header of each `.c` file

Read it before the C. It holds both addresses, the prototype, how many callees had
their signatures set, and where the signature came from:

- `debug info` - DWARF had a real prototype. GCC builds and clang test builds did.
- `mangled name (debug info was empty)` - DWARF came through as `void f(void)`, as on
  Factorio, so the script used the C++ name. `` `this` assumed `` means it added a
  `this` pointer, which is wrong for a static method. Mangled names have no return
  type, so a struct returned by value shows up as an extra first pointer argument (the
  hidden return slot), and the names after it are shifted. On Factorio,
  `Surface::collide` starts `(Surface *this, Surface *param_1, ...)`: that `this` is
  really the return slot, and `param_1` is the real `this`.
- `inferred (compiler clone)`, `inferred (thunk)` or `inferred (clang changed the
  arguments: DW_CC_nocall)` - the declared arguments are wrong for this code, so the
  decompiler worked them out. These read as `param_1..N`. Map them to the source by hand.
  `arguments in registers (__regparm3)` is the 32-bit case below.
- `none (...)` - no debug info and no C++ name, as in a stripped binary or plain C.

## What the script fixes, so the C is not quietly wrong

1. **Addresses are shifted for position-independent (PIE) binaries.** Ghidra loads a
   64-bit PIE at `0x100000` and a 32-bit one at `0x10000`, so objdump's `0x24f4370` is
   Ghidra's `0x25f4370`. The script reads `ELF Original Image Base` and shifts for
   you, and `import` prints the shift. In the GUI, add it yourself.
2. **DWARF-only analysis names functions but does not disassemble them.** In the
   listing they show as raw bytes (`?? 55h`). The script disassembles from the entry
   point. In the GUI press **D** on the first byte (not F - the function exists).
3. **Factorio's debug info gave every function `void f(void)`.** Ghidra could not use
   its register locations, and the C filled with `in_RDI`, `in_RSI`, `extraout_RAX`.
   The DWARF options `Default Calling Convention` and `Ignore Parameter Storage Info`
   did not fix it (tested). The script keeps a real DWARF prototype when there is one,
   and only otherwise applies the one the C++ mangled name spells out, plus `this` for
   methods (Ghidra has no x86-64 `__thiscall`).
4. **Compiler clones take different arguments from their declaration.** At `-O2` GCC
   makes copies named like `Picker::wins(...) [clone .isra.0]` (also `.constprop`,
   `.part`, `.cold`, `.lto_priv`, and in C `sumpt.constprop.0.isra.0`) that pass a field
   instead of `this`, or split a struct into separate registers. Forcing the declared
   signature onto one gave C that looked right and was wrong (`(int)this < 0` for a
   plain `int`). Clang does the same with no name change: it dropped an unused first
   argument of `pick(int unused, int a, int b)`, so the DWARF prototype put `unused`
   where `a` really is. Clang marks such functions `DW_CC_nocall` in the debug info, which
   Ghidra ignores, so `import` reads the mark with `llvm-dwarfdump` (about 10 s on
   Factorio, which has none). For all of these the script lets the decompiler infer the
   arguments, and stores the result so callers pass the right ones. On 32-bit x86, GCC
   also passes a clone's arguments in EAX, EDX and ECX, so the script switches those to
   `__regparm3`. All of this matched the machine code on the test builds.
5. **Library calls and calls that never return.** DWARF-only analysis leaves the PLT
   (the jump table for imported functions) as bare bytes and does not know that
   `__cxa_throw`, `std::__throw_*`, `exit`, `_Unwind_Resume` and `__stack_chk_fail`
   never return. Then calls lose their arguments, and the C runs on past a throw into
   the next block's cleanup code. `import` turns every PLT entry into a function and
   marks Ghidra's list of no-return functions plus a few more, imported or not
   (Factorio's `_Unwind_Resume` is inside the binary). A plain name on that list only
   counts for a C function: Factorio's Lua has a C++ `panic` that returns, and it is left
   alone. A project made by an older version
   of the script gets this done in memory on each `decompile`, or once with `--save`.

## Reading the C

- **Calibrate first.** Before trusting C for an open question, decompile one function
  whose behaviour is already known (from notes, a test, or the source) and check that
  the C says the same. On 2026-11-12, `generateEntities` showed exactly the compare the
  notes had read by hand, which is what made `Surface::collide` worth reading.
- The C is evidence about the code, not about which path the program takes. Confirm
  with a measurement where it matters.
- **`printf`-style calls can show too few arguments.** GCC sometimes keeps a value in
  a register across a call to its own function, and the decompiler then drops it. The
  format string is in the C, so count its `%` codes against the arguments.
- **`catch` blocks do not show.** A `try`/`catch` reads as the `try` part only.
- Harmless noise: `DuplicateNameException: codecvt already exists` while importing,
  a `DWARFImportSummary` ERROR list of unrecoverable location expressions, and
  `Unresolved local var` comments.
- **"Control flow encountered bad instruction data" is not noise.** It meant a fake
  function start or a call that never returns but was not marked. Check the address,
  and check which call comes just before the cut.
- Offsets like `this + 0x24` are struct fields Ghidra has no layout for. The debug info
  often lacks class layouts too. Name what you learn in your notes, not by guessing types.

## Finding callers

DWARF-only analysis does not disassemble function bodies, so Ghidra has no list of
who calls what. Use objdump with the mangled name from `find`:

```bash
objdump --disassemble --no-show-raw-insn <bin> | grep 'call.*<_ZN7Surface21collideWithTileCommon'
```

Each hit is a call address. On the Factorio binary this took 6 s and found 4 callers.

## GUI steps (for a person at the desktop)

1. Start Ghidra. Its heap defaults to a quarter of RAM (7.8 GiB on a 31 GiB box), which was
   enough. To raise it, add `GHIDRA_GUI_MAXMEM=16G` under Environment variables in the
   KDE menu editor (right-click Ghidra, Edit Application). Keep it well under free RAM.
2. File, New Project, Non-Shared. File, Import File, pick the binary (about 50 s).
3. Open it. When asked "Analyze?", click Yes, then **Deselect All**, then check only
   **DWARF**, **Demangler GNU** and **Apply Data Archives**. Analyze (4-5 min).
   **Ctrl+S** right away.
4. Press **G**, type the Ghidra address (file address + shift) or use the Symbol Tree
   filter. Press **D** on the first byte if it shows `??`. **Ctrl+E** opens the
   Decompiler if it is closed. Save again.

The GUI does not get fixes 4 and 5 by itself. A project imported with the script and
saved with `decompile --save` carries them for the functions decompiled.

A person can drive the GUI while Claude watches with screenshots (`spectacle
--background --fullscreen --nonotify --output <png>`, with `WAYLAND_DISPLAY` set to the
session's socket in `$XDG_RUNTIME_DIR`). The command line is faster for the agent itself.

## Ruled out (2026-11-12) - do not re-test without a new reason

- **REA** (`morluto/rea`): waits for Ghidra's full default analysis before answering
  and does not change analyzer settings, so it never got past the 2-hour analysis.
  6.9.0 added an opt-in checkpoint, but still runs the full analysis first.
- **skills.sh Ghidra skills** (mitsuhiko `ghidra`, trailofbits `ghidra-headless`, the
  zhaoxuya520 one): wrappers around the default analysis with a timeout, and none of
  them knows the traps above.
- **Jython**: Python 2.7, only an optional extension in Ghidra 12. Use PyGhidra.
- **Java GhidraScripts via analyzeHeadless** (a pre-script that sets the analyzers and a
  post-script that decompiles) work, but cost 30-60 s of start-up per run, and Ghidra
  refuses a script that has a copy in a parent folder with a misleading
  `Failed to find source bundle containing script`.
- **Ghidra's format-string analyzer on one function** (2026-11-13): run on just the
  target, it added no `printf` arguments, likely because DWARF-only analysis does not
  mark the format string as data.
- Worth a look later: **ReVa** (`cyberkaida/reverse-engineering-assistant`), an MCP
  server inside a running Ghidra, for working live in a session instead of batches.

## Python, Java and machine notes

- The script caps Python below 3.15 because JPype (PyGhidra's bridge to Java) had no
  3.15 wheel. uv otherwise picks 3.15 and fails building JPype (it needs Apache Ant).
- **Ghidra 12.2 needs Java 25** (`application.java.min=25` in
  `/opt/ghidra/Ghidra/application.properties`). It does not use the system default
  `java`. It uses the JDK saved in `~/.config/ghidra/ghidra_<version>/java_home.save`.
  On the test machine that file named Java 25 while `archlinux-java` defaulted to 21. If the
  wrong Java starts, fix that file or set `JAVA_HOME_OVERRIDE` in
  `/opt/ghidra/support/launch.properties`.
- Installing Ghidra needs sudo, so the user types the password. The
  `getting-command-output` skill covers doing that in a logged tmux window.
- The import is the only heavy step, so run it on the fastest machine available. The
  finished project folder can be copied to another machine and opened as is.
