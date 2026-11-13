#!/usr/bin/env -S uv run --quiet --script
# /// script
# # Capped below 3.15: JPype (pyghidra's bridge to Java) had no 3.15 wheel on 2026-11-12,
# # and building it from source needs Apache Ant. Raise the cap once a cp315 wheel exists.
# # The wheel path is Arch's `ghidra` 12.2 package; a Ghidra update may rename the file.
# requires-python = ">=3.14,<3.15"
# dependencies = [
#   "pyghidra @ file:///opt/ghidra/Ghidra/Features/PyGhidra/pypkg/dist/pyghidra-3.2.0-py3-none-any.whl",
# ]
# ///
"""Read big ELF binaries that ship debug info (DWARF) with Ghidra, from the command line.

    ghidra_decompile.py import <binary> <project_dir> [--full-analysis]
        New project, one binary, in a folder that holds no project yet. Analyzes
        with ONLY the DWARF, GNU demangler and data-archive analyzers, then turns
        the PLT stubs into named functions, marks the functions that never return,
        and records which functions clang changed the arguments of (DW_CC_nocall,
        read with llvm-dwarfdump). 257 MB Factorio headless: ~2.5 min on an
        i5-14400F, ~4-6 min on an 8-core i7-6700. Ghidra's defaults ran past 2 h.

    ghidra_decompile.py find <project_dir> <text> [--limit N]
        Functions whose name (Ghidra's or the mangled one) contains the text, with
        FILE addresses (what objdump/readelf print), and marks for clones, thunks,
        PLT stubs and clang-changed arguments. Overloads show their mangled names.

    ghidra_decompile.py decompile <project_dir> <target>... --out <dir> [--save]
        <target>: a FILE address (0x1989690), a name as `find` prints it (the
        namespaces can be left off when that is unique), or a mangled name.
        Writes <name>@<file address>.c per target. A bad target is reported and
        skipped, and the exit code is then 1. Without --save the project is left
        unchanged.

One process per project at a time: Ghidra locks it (an open GUI counts).
Set GHIDRA_INSTALL_DIR if Ghidra is not at /opt/ghidra.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("GHIDRA_INSTALL_DIR", "/opt/ghidra")

import pyghidra  # noqa: E402

# "Apply Data Archives" gives imported C library calls (strlen, printf) their signatures.
KEEP_ANALYZERS = {"DWARF", "Demangler GNU", "Apply Data Archives"}
# Compiler-made copies whose real arguments differ from the declaration (GCC). Also
# matches C names like sumpt.constprop.0.isra.0.
CLONE_RE = re.compile(r"\.(isra|constprop|part|cold|lto_priv|clone|specialized)\.\d")
# Itanium thunks: _ZTh (non-virtual), _ZTv (virtual), _ZTc (covariant return).
THUNK_PREFIXES = ("_ZTh", "_ZTv", "_ZTc")
# Added to Ghidra's own ElfFunctionsThatDoNotReturn list (names without leading '_').
EXTRA_NORETURN = {"cxa_rethrow", "clang_call_terminate", "cxa_bad_typeid",
                  "cxa_throw_bad_array_new_length", "cxa_pure_virtual", "exit", "quick_exit",
                  "Exit", "builtin_unreachable", "Unwind_Resume_or_Rethrow"}
# C++ names in a namespace, matched on the full name (the list above has them only mangled).
NORETURN_PREFIXES = ("std::__throw_", "std::terminate", "std::rethrow_exception", "std::__glibcxx_assert_fail",
                     "__cxxabiv1::__terminate", "__gnu_cxx::__verbose_terminate_handler")
STAMP_KEY = "decompiling-with-ghidra stubs"
NOCALL_KEY = "decompiling-with-ghidra nocall"


class TargetError(Exception):
    """A target that cannot be decompiled; reported, and the batch goes on."""


# ---------- project helpers ----------

def open_existing(project_dir: Path):
    gprs = sorted(project_dir.glob("*.gpr"))
    if not gprs:
        raise SystemExit(f"no Ghidra project (*.gpr) in {project_dir}")
    if len(gprs) > 1:
        raise SystemExit(f"{project_dir} holds {len(gprs)} projects ({', '.join(g.name for g in gprs)}); "
                         "use one folder per binary")
    try:
        return pyghidra.open_project(project_dir, gprs[0].stem)
    except Exception as err:  # Java exceptions arrive as plain Exceptions
        if "Lock" in type(err).__name__ or "lock" in str(err):
            raise SystemExit(f"{project_dir} is locked: another Ghidra (a GUI or a second run of this "
                             "script) has it open. Close it and retry.") from None
        raise


def only_program_path(project) -> str:
    paths: list[str] = []
    pyghidra.walk_project(project, lambda f: paths.append(str(f.getPathname())))
    if len(paths) != 1:
        raise SystemExit(f"expected one program in the project, found {paths}; re-import into a new folder")
    return paths[0]


def file_to_ghidra_shift(program) -> int:
    """Ghidra rebases position-independent ELFs: 64-bit to 0x100000, 32-bit to 0x10000.
    Return the amount to add to a file/objdump address (0 when not rebased)."""
    original = pyghidra.program_info(program).getString("ELF Original Image Base", None)
    if original is None:
        return 0
    return program.getImageBase().getOffset() - int(str(original), 16)


# ---------- import ----------

def cmd_import(binary: Path, project_dir: Path, full: bool) -> None:
    if not binary.is_file():
        raise SystemExit(f"{binary} is not a file")
    with binary.open("rb") as fh:
        if fh.read(4) != b"\x7fELF":
            raise SystemExit(f"{binary} is not an ELF file; this script handles Linux ELF binaries only")
    if project_dir.exists() and any(project_dir.glob("*.gpr")):
        raise SystemExit(f"{project_dir} already holds a Ghidra project; import into a new folder "
                         "(re-importing adds a second copy that breaks find/decompile)")
    created = not project_dir.exists()
    project_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", binary.name)
    ok = False
    project = pyghidra.open_project(project_dir, name, create=True)
    try:
        loader = pyghidra.program_loader().project(project).source(str(binary)).name(name)
        t0 = time.monotonic()
        with loader.load() as results:
            results.save(pyghidra.task_monitor())
        print(f"imported in {time.monotonic() - t0:.0f} s", flush=True)
        with pyghidra.program_context(project, "/" + name) as program:
            if not full:
                set_dwarf_only(program)
            t0 = time.monotonic()
            pyghidra.analyze(program)
            print(f"analyzed in {time.monotonic() - t0:.0f} s", flush=True)
            with pyghidra.transaction(program, "stubs and no-return marks"):
                print(fix_stubs(program), flush=True)
                nocall = scan_nocall(binary)
                pyghidra.program_info(program).setString(NOCALL_KEY, nocall)
                if nocall.startswith("unchecked"):
                    print(f"clang argument changes (DW_CC_nocall): {nocall}", flush=True)
                else:
                    print(f"functions whose arguments clang changed (DW_CC_nocall): "
                          f"{len(nocall.split(',')) if nocall else 0}", flush=True)
            program.save("analysis", pyghidra.task_monitor())
            print(f"file->ghidra address shift: +0x{file_to_ghidra_shift(program):x}")
        ok = True
    finally:
        project.close()
        if not ok and created:
            shutil.rmtree(project_dir, ignore_errors=True)


def set_dwarf_only(program) -> None:
    from ghidra.app.plugin.core.analysis import AutoAnalysisManager
    from ghidra.framework.options import OptionType
    from ghidra.program.model.listing import Program

    # Analyzer toggles only exist once the analysis manager has registered them.
    AutoAnalysisManager.getAnalysisManager(program).initializeOptions()
    options = program.getOptions(Program.ANALYSIS_PROPERTIES)
    on: list[str] = []
    with pyghidra.transaction(program, "DWARF-only analyzers"):
        for name in options.getOptionNames():
            name = str(name)
            if "." in name or options.getType(name) != OptionType.BOOLEAN_TYPE:
                continue
            keep = name in KEEP_ANALYZERS
            options.setBoolean(name, keep)
            if keep:
                on.append(name)
    print(f"analyzers on: {sorted(on)}", flush=True)
    if sorted(on) != sorted(KEEP_ANALYZERS):
        print("WARNING: expected analyzers missing; analyzer names may have changed", flush=True)


def noreturn_names() -> set[str]:
    path = Path(os.environ["GHIDRA_INSTALL_DIR"]) / "Ghidra/Features/Base/data/ElfFunctionsThatDoNotReturn"
    names = set(EXTRA_NORETURN)
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line)
    return names


def fix_stubs(program) -> str:
    """DWARF-only analysis leaves the PLT as bare bytes and knows no function that never
    returns. Then calls to strlen/printf show as func_0x..., and code after a call to
    __cxa_throw, __stack_chk_fail or _Unwind_Resume runs on into the next function's
    cleanup code. Make every PLT entry a function (Ghidra turns them into thunks to the
    imports) and mark Ghidra's known no-return names, wherever they live."""
    from ghidra.app.cmd.disassemble import DisassembleCommand
    from ghidra.app.cmd.function import CreateFunctionCmd

    mon = pyghidra.task_monitor()
    fm = program.getFunctionManager()
    listing = program.getListing()
    stubs = 0
    for blk in program.getMemory().getBlocks():
        if not str(blk.getName()).startswith(".plt") or not blk.isExecute():
            continue
        start = 16 if str(blk.getName()) == ".plt" else 0  # .plt's first entry is the resolver
        step = 8 if str(blk.getName()) == ".plt.got" else 16  # .plt.got: jmp + 2 bytes of padding
        for off in range(start, int(blk.getSize()), step):
            addr = blk.getStart().add(off)
            if fm.getFunctionAt(addr) is not None:
                continue
            if listing.getInstructionAt(addr) is None:
                DisassembleCommand(addr, None, True).applyTo(program, mon)
            if listing.getInstructionAt(addr) is not None:
                CreateFunctionCmd(addr).applyTo(program, mon)
                stubs += fm.getFunctionAt(addr) is not None

    names = noreturn_names()
    marked = 0
    funcs = list(fm.getFunctions(True)) + list(fm.getExternalFunctions())
    for f in funcs:
        target = f.getThunkedFunction(True) if f.isThunk() else f
        for cand in (f, target):
            if cand is None:
                continue
            bare = str(cand.getName()).lstrip("_")
            full = str(cand.getName(True)).removeprefix("<EXTERNAL>::")
            # A bare-name match only counts for C-linkage functions (no _Z symbol): Lua's
            # static C++ `panic(lua_State*)` in Factorio returns, and so may Game::exit.
            if (bare in names and c_linkage(program, cand)) or full.startswith(NORETURN_PREFIXES):
                if not f.hasNoReturn():
                    f.setNoReturn(True)
                    marked += 1
                break
    info = pyghidra.program_info(program)
    info.setString(STAMP_KEY, f"{stubs} stubs, {marked} no-return")
    return f"PLT stubs made functions: {stubs}; marked as never returning: {marked}"


def c_linkage(program, fn) -> bool:
    """True when fn has a plain C symbol, not a mangled C++ one. Ghidra files some C
    functions under a namespace from DWARF (__cxxabiv1::__cxa_throw), so the name's
    namespace does not tell."""
    if fn.isExternal():
        orig = fn.getExternalLocation().getOriginalImportedName()
        return not (orig is not None and str(orig).startswith("_Z"))
    return mangled_name(program, fn.getEntryPoint()) is None


def scan_nocall(binary: Path) -> str:
    """FILE addresses of functions clang marked DW_CC_nocall: it changed their arguments
    (dropped an unused one, split a struct) and their debug-info prototype is wrong.
    Ghidra ignores the mark, so read it with llvm-dwarfdump. Returns a comma list of hex
    addresses, "" for none, or "unchecked: <why>"."""
    exe = shutil.which("llvm-dwarfdump")
    if exe is None:
        return "unchecked: llvm-dwarfdump not found (package llvm)"
    if not binary.is_file():
        return f"unchecked: {binary} not found"
    nocall_dies: set[int] = set()
    concrete: list[tuple[int, int | None, bool]] = []  # (low_pc, origin DIE, own nocall)
    off = low = origin = None
    own = False
    is_sub = False

    def finish() -> None:
        if not is_sub:
            return
        if own and off is not None:
            nocall_dies.add(off)
        if low is not None:
            concrete.append((low, origin, own))

    with subprocess.Popen([exe, "--debug-info", str(binary)], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, errors="replace") as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith("0x"):
                finish()
                head, _, tag = line.partition(":")
                is_sub = tag.strip() == "DW_TAG_subprogram"
                off, low, origin, own = int(head, 16), None, None, False
            elif not is_sub:
                continue
            elif "DW_AT_low_pc" in line:
                low = int(line.split("(", 1)[1].split(")", 1)[0], 16)
            elif "DW_CC_nocall" in line:
                own = True
            elif "DW_AT_abstract_origin" in line or "DW_AT_specification" in line:
                origin = int(line.split("(", 1)[1].split()[0].rstrip(")"), 16)
        finish()
    if proc.returncode != 0:
        return f"unchecked: llvm-dwarfdump exited {proc.returncode}"
    hits = sorted({lo for lo, org, mine in concrete if mine or org in nocall_dies})
    return ",".join(f"0x{a:x}" for a in hits)


def nocall_addresses(program, shift: int, scan_if_missing: bool = True) -> tuple[set[int], str]:
    """Ghidra addresses of DW_CC_nocall functions, and a note when the scan did not run."""
    info = pyghidra.program_info(program)
    raw = info.getString(NOCALL_KEY, None)
    note = ""
    if raw is None:  # project made by an older version of this script
        if not scan_if_missing:
            return set(), ""
        raw = scan_nocall(Path(str(program.getExecutablePath())))
        info.setString(NOCALL_KEY, raw)  # kept only if the caller saves (--save)
        note = "clang argument changes: older project, scanned now"
    raw = str(raw)
    if raw.startswith("unchecked"):
        return set(), f"clang argument changes not checked: {raw.removeprefix('unchecked: ')}"
    return {int(a, 16) + shift for a in raw.split(",") if a}, note


# ---------- naming ----------

def internal_functions(program):
    """Functions in executable memory. Skips the fake EXTERNAL block Ghidra adds for
    imports, whose addresses exist nowhere in the file."""
    mem = program.getMemory()
    for fn in program.getFunctionManager().getFunctions(True):
        blk = mem.getBlock(fn.getEntryPoint())
        if blk is not None and blk.isExecute():
            yield fn


def is_plt_stub(fn) -> bool:
    """A PLT entry: a thunk that jumps to an imported (external) function."""
    target = fn.getThunkedFunction(True) if fn.isThunk() else None
    return target is not None and target.isExternal()


def symbol_names(program, addr) -> list[str]:
    return [str(s.getName()) for s in program.getSymbolTable().getSymbols(addr)]


def mangled_name(program, addr) -> str | None:
    """The plain mangled symbol, without a clone suffix if there is one."""
    for n in symbol_names(program, addr):
        if n.startswith("_Z"):
            return n
    return None


def clone_suffix(program, addr) -> str | None:
    for n in symbol_names(program, addr):
        m = CLONE_RE.search(n)
        if m:
            return n[m.start():]
    return None


def is_thunk(program, fn) -> bool:
    m = mangled_name(program, fn.getEntryPoint())
    return bool(fn.isThunk() or (m and m.startswith(THUNK_PREFIXES)))


def normalize(name: str) -> str:
    """One spelling for names, so `find`, the decompiler and the user agree."""
    name = re.sub(r"anon_unknown\.dwarf_[0-9a-f]+", "(anonymous_namespace)", name)
    name = name.removeprefix("<EXTERNAL>::")
    return name.replace("(anonymous namespace)", "(anonymous_namespace)")


def strip_params(name: str) -> str:
    """'ns::f(int) const [clone .isra.0]' -> 'ns::f'; template args are kept."""
    name = normalize(name)
    depth = 0
    for i, ch in enumerate(name):
        if name.startswith("(anonymous_namespace)", i):
            continue
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "(" and depth == 0 and not name[:i].endswith("operator"):
            return name[:i]
    return name


def describe(program, fn, shift: int, nocall: set[int] | frozenset[int] = frozenset()) -> str:
    g = fn.getEntryPoint().getOffset()
    marks = []
    if g in nocall:
        marks.append("arguments changed by clang")
    sfx = clone_suffix(program, fn.getEntryPoint())
    if sfx:
        marks.append(f"clone {sfx}")
    if is_plt_stub(fn):
        marks.append("PLT stub for an import")
    elif is_thunk(program, fn):
        marks.append("thunk")
    mangled = mangled_name(program, fn.getEntryPoint())
    tail = f"  [{', '.join(marks)}]" if marks else ""
    tail += f"  {mangled}" if mangled else ""
    return f"file 0x{g - shift:x}  ghidra 0x{g:x}  {normalize(str(fn.getName(True)))}{tail}"


# ---------- find ----------

def cmd_find(project_dir: Path, needle: str, limit: int) -> None:
    project = open_existing(project_dir)
    try:
        with pyghidra.program_context(project, only_program_path(project)) as program:
            shift = file_to_ghidra_shift(program)
            nocall, _ = nocall_addresses(program, shift, scan_if_missing=False)
            want = normalize(needle)
            n = 0
            for fn in internal_functions(program):
                name = normalize(str(fn.getName(True)))
                if want not in name and not any(needle in s for s in symbol_names(program, fn.getEntryPoint())):
                    continue
                print(describe(program, fn, shift, nocall))
                n += 1
                if n >= limit:
                    print(f"... stopped at --limit {limit}")
                    break
            if n == 0:
                print(f"no function matches {needle!r}. Names use Ghidra's spelling, without "
                      "parameters; try a shorter part, or the mangled name from nm.")
    finally:
        project.close()


# ---------- decompile ----------

def resolve(program, target: str, shift: int):
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", target):
        space = program.getAddressFactory().getDefaultAddressSpace()
        addr = space.getAddress(int(target, 16) + shift)
        blk = program.getMemory().getBlock(addr)
        if blk is None or not blk.isExecute():
            where = f"block {blk.getName()}" if blk else "no memory block"
            raise TargetError(f"{target}: not in executable code ({where}). Pass the FILE address objdump "
                              "prints, not the ghidra address.")
        containing = function_containing(program, addr)
        if containing is not None and containing.getEntryPoint() != addr:
            start = containing.getEntryPoint().getOffset() - shift
            raise TargetError(f"{target}: inside {normalize(str(containing.getName(True)))}, which starts at "
                              f"file 0x{start:x}. Pass that start (or check you passed a file address).")
        return addr
    if target.lower().startswith("0x"):
        raise TargetError(f"{target}: not a hex address")
    want = strip_params(target)
    funcs = [(normalize(str(f.getName(True))), f) for f in internal_functions(program)]
    hits = [f for name, f in funcs if name == want or target in symbol_names(program, f.getEntryPoint())]
    if not hits:  # allow leaving out namespaces and classes: `pick` for `(anonymous_namespace)::pick`
        hits = [f for name, f in funcs if name.endswith("::" + want)]
    if not hits:
        raise TargetError(f"no function named {target} (use `find`; names have no parameters)")
    if len(hits) > 1:
        listing = "; ".join(describe(program, f, shift) for f in hits)
        raise TargetError(f"{target} matches {len(hits)} functions, pass a file address: {listing}")
    return hits[0].getEntryPoint()


def function_containing(program, addr):
    """The function whose body holds addr. DWARF-only functions have no body until they
    are disassembled, so disassemble the nearest function before addr first."""
    fm = program.getFunctionManager()
    fn = fm.getFunctionContaining(addr)
    if fn is not None or fm.getFunctionAt(addr) is not None:
        return fn
    before = fm.getFunctions(addr, False)
    prev = before.next() if before.hasNext() else None
    if prev is None:
        return None
    prepare(program, prev.getEntryPoint())  # caller holds the transaction
    return fm.getFunctionContaining(addr)


def prepare(program, entry):
    """DWARF-only analysis names and bounds functions but does not disassemble them."""
    from ghidra.app.cmd.disassemble import DisassembleCommand
    from ghidra.app.cmd.function import CreateFunctionCmd
    from ghidra.program.model.address import AddressSet

    fm = program.getFunctionManager()
    created = fm.getFunctionAt(entry) is None
    DisassembleCommand(AddressSet(entry), None, True).applyTo(program, pyghidra.task_monitor())
    fn = fm.getFunctionAt(entry)
    if fn is None:
        CreateFunctionCmd(entry).applyTo(program, pyghidra.task_monitor())
        fn = fm.getFunctionAt(entry)
    if fn is None:
        raise TargetError(f"could not create a function at ghidra 0x{entry.getOffset():x}")
    CreateFunctionCmd.fixupFunctionBody(program, fn, pyghidra.task_monitor())
    return fn, created


def debug_info_signature(fn) -> bool:
    """True when DWARF gave a real prototype. On Factorio (clang) DWARF came through as
    `void f(void)`; on GCC test builds it was complete and better than anything else."""
    from ghidra.program.model.data import VoidDataType
    from ghidra.program.model.symbol import SourceType

    if fn.getSignatureSource() != SourceType.IMPORTED:
        return False
    if fn.getParameterCount() > 0:
        return True
    return not isinstance(fn.getReturnType(), VoidDataType)


def set_signature(program, fn, nocall: set[int]) -> str:
    """Decide where this function's signature comes from. Returns a label for the header."""
    from ghidra.app.util.demangler import DemanglerUtil
    from ghidra.app.util.demangler.gnu import GnuDemanglerOptions
    from ghidra.program.model.symbol import SourceType

    entry = fn.getEntryPoint()
    if is_plt_stub(fn):
        return "import (left as is)"
    if entry.getOffset() in nocall:
        # clang dropped or reordered arguments and marked it DW_CC_nocall; the name has
        # no clone suffix and the debug-info prototype is the old one.
        let_decompiler_infer(program, fn)
        return "inferred (clang changed the arguments: DW_CC_nocall)"
    if clone_suffix(program, entry):
        # GCC changed a clone's real arguments (a field instead of `this`, a struct split
        # into registers). Both the declaration and DWARF are then wrong.
        let_decompiler_infer(program, fn)
        return "inferred (compiler clone)"
    if is_thunk(program, fn):
        let_decompiler_infer(program, fn)
        return "inferred (thunk)"
    if debug_info_signature(fn):
        return "debug info"
    mangled = mangled_name(program, entry)
    if mangled is None:
        return "none (no debug info or C++ name)"
    demangled = DemanglerUtil.demangle(program, mangled, entry)
    if demangled is None or demangled.isEmpty():
        return "none (name did not demangle)"
    opts = GnuDemanglerOptions()
    opts.setApplySignature(True)
    opts.setApplyCallingConvention(True)
    opts.setDoDisassembly(True)
    had_dwarf = fn.getSignatureSource() == SourceType.IMPORTED
    fn.setSignatureSource(SourceType.DEFAULT)  # let the demangler overwrite an empty DWARF one
    ok = False
    for obj in demangled:
        ok = bool(obj.applyTo(program, entry, opts, pyghidra.task_monitor())) or ok
    if not ok:
        return "none (demangler declined)"
    this_added = add_this_pointer(program, fn)
    label = "mangled name" + (" (debug info was empty)" if had_dwarf else " (no debug info)")
    return label + ("; `this` assumed" if this_added else "")


def let_decompiler_infer(program, fn) -> None:
    from ghidra.program.model.data import DataType
    from ghidra.program.model.listing import Function
    from ghidra.program.model.symbol import SourceType
    from java.util import ArrayList

    fn.setCustomVariableStorage(False)
    fn.setCallingConvention(program.getCompilerSpec().getDefaultCallingConvention().getName())
    fn.replaceParameters(ArrayList(), Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
                         True, SourceType.DEFAULT)
    fn.setReturnType(DataType.DEFAULT, SourceType.DEFAULT)
    fn.setSignatureSource(SourceType.DEFAULT)


def add_this_pointer(program, fn) -> bool:
    """Ghidra has no x86-64 __thiscall, so the demangler leaves `this` out of methods.
    Mangled names do not say `static`, so a static method also gets one."""
    from ghidra.program.model.data import PointerDataType, Structure
    from ghidra.program.model.listing import Function, GhidraClass, ParameterImpl
    from ghidra.program.model.symbol import SourceType
    from java.util import ArrayList

    parent = fn.getParentNamespace()
    if not isinstance(parent, GhidraClass):
        return False
    params = list(fn.getParameters())
    if params and str(params[0].getName()) == "this":
        return False
    found = ArrayList()
    program.getDataTypeManager().findDataTypes(str(parent.getName()), found)
    struct = next((dt for dt in found if isinstance(dt, Structure)), None)
    new_params = ArrayList()
    new_params.add(ParameterImpl("this", PointerDataType(struct) if struct else PointerDataType(), program))
    for p in params:
        new_params.add(ParameterImpl(p.getName(), p.getDataType(), program))
    cc = "__thiscall" if program.getCompilerSpec().getCallingConvention("__thiscall") else fn.getCallingConventionName()
    fn.updateFunction(cc, fn.getReturn(), new_params,
                      Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS, True, SourceType.ANALYSIS)
    return True


REGPARM_REGS = ("EAX", "EDX", "ECX")


def reads_regparm_registers(program, fn) -> bool:
    """True when the code at fn's entry reads EAX, EDX or ECX before writing it, which
    on 32-bit x86 means GCC passed arguments in registers (regparm). Follows the
    straight-line code up to the first call, jump or return."""
    from ghidra.app.cmd.disassemble import DisassembleCommand
    from ghidra.program.model.address import AddressSet
    from ghidra.program.model.lang import Register

    entry = fn.getEntryPoint()
    listing = program.getListing()
    if listing.getInstructionAt(entry) is None:
        DisassembleCommand(AddressSet(entry), None, True).applyTo(program, pyghidra.task_monitor())
    written: set[str] = set()
    ins = listing.getInstructionAt(entry)
    for _ in range(64):
        if ins is None:
            return False
        ops = [ins.getDefaultOperandRepresentation(i) for i in range(ins.getNumOperands())]
        zeroing = str(ins.getMnemonicString()) in ("XOR", "SUB") and len(ops) == 2 and ops[0] == ops[1]
        if not zeroing:
            for obj in ins.getInputObjects():
                if isinstance(obj, Register):
                    reg = str(obj.getBaseRegister().getName())
                    if reg in REGPARM_REGS and reg not in written:
                        return True
        for obj in ins.getResultObjects():
            if isinstance(obj, Register):
                written.add(str(obj.getBaseRegister().getName()))
        flow = ins.getFlowType()
        if flow.isCall() or flow.isTerminal() or (flow.isJump() and not flow.isConditional()):
            return False
        ins = ins.getNext()
    return False


def settle_inferred(program, decomp, fn) -> str:
    """Finish a function whose arguments the decompiler infers. On 32-bit x86, GCC passes
    a local clone's arguments in EAX, EDX, ECX (regparm) instead of on the stack, and the
    default convention then shows them as in_EAX and friends, so switch to __regparm3.
    Then store what the decompiler infers, so callers pass the right arguments instead
    of none. Returns a note for the header, or ""."""
    note = ""
    if (program.getDefaultPointerSize() == 4
            and program.getCompilerSpec().getCallingConvention("__regparm3") is not None
            and reads_regparm_registers(program, fn)):
        fn.setCallingConvention("__regparm3")
        note = "; arguments in registers (__regparm3)"
    commit_inferred(program, decomp, fn)
    return note


def commit_inferred(program, decomp, fn) -> None:
    """Decompile an inferred function once and store the arguments it found."""
    from ghidra.program.model.pcode import HighFunctionDBUtil
    from ghidra.program.model.symbol import SourceType

    decomp.flushCache()
    res = decomp.decompileFunction(fn, 60, pyghidra.task_monitor())
    high = res.getHighFunction() if res.decompileCompleted() else None
    if high is not None:
        HighFunctionDBUtil.commitParamsToDatabase(high, True, HighFunctionDBUtil.ReturnCommitOption.COMMIT,
                                                  SourceType.ANALYSIS)


def cmd_decompile(project_dir: Path, targets: list[str], out_dir: Path, save: bool) -> int:
    from ghidra.app.decompiler import DecompileOptions, DecompInterface

    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    project = open_existing(project_dir)
    try:
        with pyghidra.program_context(project, only_program_path(project)) as program:
            shift = file_to_ghidra_shift(program)
            decomp = DecompInterface()
            decomp.setOptions(DecompileOptions())
            decomp.openProgram(program)
            try:
                with pyghidra.transaction(program, "decompile prep"):
                    if pyghidra.program_info(program).getString(STAMP_KEY, None) is None:
                        print(fix_stubs(program) + " (older project; done in memory)", flush=True)
                    nocall, note = nocall_addresses(program, shift)
                    if note:
                        print(note, flush=True)
                    jobs = []
                    labels: dict[int, str] = {}  # entry -> signature source; each function once

                    def settle(f) -> str:
                        key = f.getEntryPoint().getOffset()
                        if key not in labels:
                            label = set_signature(program, f, nocall)
                            if label.startswith("inferred"):
                                label += settle_inferred(program, decomp, f)
                            labels[key] = label
                        return labels[key]

                    for target in targets:
                        try:
                            fn, created = prepare(program, resolve(program, target, shift))
                        except TargetError as err:
                            errors.append(str(err))
                            continue
                        # Callees first: an inferred target is stored, and what the
                        # decompiler infers for it depends on its callees' arguments.
                        callees = [c for c in fn.getCalledFunctions(pyghidra.task_monitor())
                                   if not c.isExternal() and not is_plt_stub(c) and c != fn]
                        done = sum(not settle(c).startswith("debug info") for c in callees)
                        source = settle(fn)
                        jobs.append((target, fn, created, source, len(callees), done))
                decomp.flushCache()
                for job in jobs:
                    write_c(decomp, shift, out_dir, *job)
            finally:
                decomp.dispose()
            if save and jobs:
                program.save("decompile prep", pyghidra.task_monitor())
                print("saved disassembly and signature changes into the project")
    finally:
        project.close()
    for e in errors:
        print(f"SKIPPED {e}", file=sys.stderr)
    return 1 if errors else 0


def write_c(decomp, shift, out_dir: Path, target, fn, created, source, n_callees, n_set) -> None:
    t0 = time.monotonic()
    res = decomp.decompileFunction(fn, 600, pyghidra.task_monitor())
    ms = (time.monotonic() - t0) * 1000
    name = normalize(str(fn.getName(True)))
    entry = fn.getEntryPoint().getOffset()
    ok = res.decompileCompleted()
    body = str(res.getDecompiledFunction().getC()) if ok else ""
    proto = str(res.getDecompiledFunction().getSignature()).strip() if ok else "(decompile failed)"
    lines = [
        f"// {name}: file 0x{entry - shift:x}, ghidra 0x{entry:x} (asked for {target})",
        f"// prototype: {proto}",
        f"// signature from: {source}",
        f"// callees: {n_callees}, signatures set or inferred: {n_set}",
        f"// decompile {ms:.0f} ms, completed: {ok}, error: {res.getErrorMessage()}",
    ]
    if created:
        lines.append("// No function started here before: check with objdump that this is a real start.")
    if source.startswith("mangled name"):
        lines.append("// Mangled names have no return type: if this returns a struct by value, the first")
        lines.append("// pointer parameter is the hidden return slot and later names are shifted.")
    if "`this` assumed" in source:
        lines.append("// If the method is static, the `this` here is really the first argument.")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name.replace("::", "__"))[:120]
    path = out_dir / f"{safe}@0x{entry - shift:x}.c"
    path.write_text("\n".join(lines) + "\n" + body)
    print(f"{path}  ({body.count(chr(10))} lines)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import")
    p.add_argument("binary", type=Path)
    p.add_argument("project_dir", type=Path)
    p.add_argument("--full-analysis", action="store_true", help="Ghidra's default analyzers (slow)")
    p = sub.add_parser("find")
    p.add_argument("project_dir", type=Path)
    p.add_argument("needle")
    p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("decompile")
    p.add_argument("project_dir", type=Path)
    p.add_argument("targets", nargs="+")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--save", action="store_true")
    args = parser.parse_args()

    pyghidra.start()
    if args.cmd == "import":
        cmd_import(args.binary, args.project_dir, args.full_analysis)
        return 0
    if args.cmd == "find":
        cmd_find(args.project_dir, args.needle, args.limit)
        return 0
    return cmd_decompile(args.project_dir, args.targets, args.out, args.save)


if __name__ == "__main__":
    sys.exit(main())
