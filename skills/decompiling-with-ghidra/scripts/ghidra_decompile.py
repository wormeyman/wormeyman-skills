#!/usr/bin/env -S uv run --quiet --script
# /// script
# # Capped below 3.15: JPype (pyghidra's bridge to Java) had no 3.15 wheel on 2026-11-12,
# # and building it from source needs Apache Ant. Raise the cap once a cp315 wheel exists.
# requires-python = ">=3.14,<3.15"
# dependencies = [
#   "pyghidra @ file:///opt/ghidra/Ghidra/Features/PyGhidra/pypkg/dist/pyghidra-3.2.0-py3-none-any.whl",
# ]
# ///
"""Read big binaries that ship debug info (DWARF) with Ghidra, from the command line.

    ghidra_decompile.py import <binary> <project_dir> [--full-analysis]
        Import, then analyze with ONLY the DWARF and GNU demangler analyzers.
        257 MB Factorio headless: ~2.5 min on an i5-14400F, ~4-6 min on an 8-core i7-6700. Ghidra's defaults ran past 2 h.

    ghidra_decompile.py find <project_dir> <name-substring> [--limit N]
        List functions whose full name contains the text, with FILE addresses
        (the ones objdump/readelf print) and Ghidra addresses.

    ghidra_decompile.py decompile <project_dir> <target>... --out <dir> [--save]
        <target>: a FILE address (0x1989690) or a full demangled name
        (EntityMapGenerationTask::generateEntities). Writes one .c file per target.
        Before decompiling, each function and its callees get the signature the C++
        mangled name spells out, plus `this` for methods (DWARF import often leaves
        void(void)). --save keeps those fixes and the disassembly in the project.

The pyghidra wheel path above matches Arch's `ghidra` package. Set GHIDRA_INSTALL_DIR
and edit that path if Ghidra lives elsewhere.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("GHIDRA_INSTALL_DIR", "/opt/ghidra")

import pyghidra  # noqa: E402

KEEP_ANALYZERS = {"DWARF", "Demangler GNU"}


# ---------- project helpers ----------

def project_name_for(project_dir: Path) -> str:
    gprs = sorted(project_dir.glob("*.gpr"))
    if not gprs:
        raise SystemExit(f"no Ghidra project (*.gpr) in {project_dir}")
    return gprs[0].stem


def only_program_path(project) -> str:
    paths: list[str] = []
    pyghidra.walk_project(project, lambda f: paths.append(str(f.getPathname())))
    if len(paths) != 1:
        raise SystemExit(f"expected one program in the project, found {paths}")
    return paths[0]


def file_to_ghidra_shift(program) -> int:
    """Ghidra rebases position-independent ELFs (PIE) to 0x100000. Return the amount
    to add to a file/objdump address to get Ghidra's address (0 for non-PIE)."""
    info = pyghidra.program_info(program)
    original = info.getString("ELF Original Image Base", None)
    if original is None:
        return 0
    return program.getImageBase().getOffset() - int(str(original), 16)


# ---------- import ----------

def cmd_import(binary: Path, project_dir: Path, full: bool) -> None:
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", binary.name)
    project_dir.mkdir(parents=True, exist_ok=True)
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
            log = pyghidra.analyze(program)
            print(f"analyzed in {time.monotonic() - t0:.0f} s", flush=True)
            for line in str(log).splitlines():
                if "Total Time" in line:
                    print(line.strip())
            program.save("analysis", pyghidra.task_monitor())
            print(f"file->ghidra address shift: +0x{file_to_ghidra_shift(program):x}")
    finally:
        project.close()


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
            if "." in name:
                continue  # sub-options like "DWARF.Import Functions"
            if options.getType(name) != OptionType.BOOLEAN_TYPE:
                continue
            keep = name in KEEP_ANALYZERS
            options.setBoolean(name, keep)
            if keep:
                on.append(name)
    print(f"analyzers on: {sorted(on)}", flush=True)
    if sorted(on) != sorted(KEEP_ANALYZERS):
        print("WARNING: expected analyzers missing; analyzer names may have changed", flush=True)


# ---------- find ----------

def cmd_find(project_dir: Path, needle: str, limit: int) -> None:
    project = pyghidra.open_project(project_dir, project_name_for(project_dir))
    try:
        with pyghidra.program_context(project, only_program_path(project)) as program:
            shift = file_to_ghidra_shift(program)
            n = 0
            for fn in program.getFunctionManager().getFunctions(True):
                full = str(fn.getName(True))
                if needle not in full:
                    continue
                g = fn.getEntryPoint().getOffset()
                # No size column: DWARF-only bodies read as 1 byte until disassembled.
                print(f"file 0x{g - shift:x}  ghidra 0x{g:x}  {full}")
                n += 1
                if n >= limit:
                    print(f"... stopped at --limit {limit}")
                    break
    finally:
        project.close()


# ---------- decompile ----------

def resolve(program, target: str, shift: int):
    if target.lower().startswith("0x"):
        return program.getAddressFactory().getDefaultAddressSpace().getAddress(int(target, 16) + shift)
    funcs = [f for f in program.getFunctionManager().getFunctions(True) if str(f.getName(True)) == target]
    if not funcs:
        raise SystemExit(f"no function named {target} (try the find command)")
    if len(funcs) > 1:
        found = ", ".join(f"0x{f.getEntryPoint().getOffset() - shift:x}" for f in funcs)
        raise SystemExit(f"{target} is overloaded (file addresses {found}); pass one")
    return funcs[0].getEntryPoint()


def prepare(program, entry):
    """DWARF-only analysis names and bounds functions but does not disassemble them."""
    from ghidra.app.cmd.disassemble import DisassembleCommand
    from ghidra.app.cmd.function import CreateFunctionCmd
    from ghidra.program.model.address import AddressSet

    fm = program.getFunctionManager()
    DisassembleCommand(AddressSet(entry), None, True).applyTo(program, pyghidra.task_monitor())
    fn = fm.getFunctionAt(entry)
    if fn is None:
        CreateFunctionCmd(entry).applyTo(program, pyghidra.task_monitor())
        fn = fm.getFunctionAt(entry)
    if fn is None:
        raise SystemExit(f"could not create a function at {entry}")
    CreateFunctionCmd.fixupFunctionBody(program, fn, pyghidra.task_monitor())
    return fn


def mangled_name(program, addr) -> str | None:
    for sym in program.getSymbolTable().getSymbols(addr):
        if str(sym.getName()).startswith("_Z"):
            return str(sym.getName())
    return None


def apply_mangled_signature(program, fn) -> bool:
    from ghidra.app.util.demangler import DemanglerUtil
    from ghidra.app.util.demangler.gnu import GnuDemanglerOptions
    from ghidra.program.model.symbol import SourceType

    mangled = mangled_name(program, fn.getEntryPoint())
    if mangled is None:
        return False
    demangled = DemanglerUtil.demangle(program, mangled, fn.getEntryPoint())
    if demangled is None or demangled.isEmpty():
        return False
    opts = GnuDemanglerOptions()
    opts.setApplySignature(True)
    opts.setApplyCallingConvention(True)
    opts.setDoDisassembly(True)
    # DWARF's signature outranks the demangler's; drop it so the demangler may apply.
    fn.setSignatureSource(SourceType.DEFAULT)
    ok = False
    for obj in demangled:
        ok = bool(obj.applyTo(program, fn.getEntryPoint(), opts, pyghidra.task_monitor())) or ok
    if ok:
        add_this_pointer(program, fn, demangled.get(0))
    return ok


def add_this_pointer(program, fn, demangled) -> None:
    """x86-64 has no __thiscall model in Ghidra, so the demangler omits `this`."""
    from ghidra.program.model.data import PointerDataType, Structure
    from ghidra.program.model.listing import Function, GhidraClass, ParameterImpl
    from ghidra.program.model.symbol import SourceType
    from java.util import ArrayList

    parent = fn.getParentNamespace()
    if not isinstance(parent, GhidraClass) or "static" in str(demangled.getStorageClass() or ""):
        return
    params = list(fn.getParameters())
    if params and str(params[0].getName()) == "this":
        return
    found = ArrayList()
    program.getDataTypeManager().findDataTypes(str(parent.getName()), found)
    struct = next((dt for dt in found if isinstance(dt, Structure)), None)
    new_params = ArrayList()
    new_params.add(ParameterImpl("this", PointerDataType(struct) if struct else PointerDataType(), program))
    for p in params:
        new_params.add(ParameterImpl(p.getName(), p.getDataType(), program))
    fn.updateFunction(
        fn.getCallingConventionName(),
        fn.getReturn(),
        new_params,
        Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
        True,
        SourceType.ANALYSIS,
    )


def cmd_decompile(project_dir: Path, targets: list[str], out_dir: Path, save: bool) -> None:
    from ghidra.app.decompiler import DecompileOptions, DecompInterface

    out_dir.mkdir(parents=True, exist_ok=True)
    project = pyghidra.open_project(project_dir, project_name_for(project_dir))
    try:
        with pyghidra.program_context(project, only_program_path(project)) as program:
            shift = file_to_ghidra_shift(program)
            decomp = DecompInterface()
            decomp.setOptions(DecompileOptions())
            decomp.openProgram(program)
            try:
                with pyghidra.transaction(program, "decompile prep"):
                    jobs = []
                    for target in targets:
                        fn = prepare(program, resolve(program, target, shift))
                        fixed = apply_mangled_signature(program, fn)
                        callees = list(fn.getCalledFunctions(pyghidra.task_monitor()))
                        fixed_callees = sum(apply_mangled_signature(program, c) for c in callees)
                        jobs.append((target, fn, fixed, len(callees), fixed_callees))
                for job in jobs:
                    write_c(decomp, shift, out_dir, *job)
            finally:
                decomp.dispose()
            if save:
                program.save("signatures from mangled names", pyghidra.task_monitor())
                print("saved fixes into the project")
    finally:
        project.close()


def write_c(decomp, shift, out_dir: Path, target, fn, fixed, n_callees, fixed_callees) -> None:
    t0 = time.monotonic()
    res = decomp.decompileFunction(fn, 600, pyghidra.task_monitor())
    ms = (time.monotonic() - t0) * 1000
    name = str(fn.getName(True))
    entry = fn.getEntryPoint().getOffset()
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name.replace("::", "__"))[:150]
    body = str(res.getDecompiledFunction().getC()) if res.decompileCompleted() else ""
    header = "\n".join([
        f"// {name}: file 0x{entry - shift:x}, ghidra 0x{entry:x} (asked for {target}),"
        f" body {fn.getBody().getNumAddresses()} bytes",
        f"// signature: {fn.getSignature().getPrototypeString()} | cc={fn.getCallingConventionName()}"
        f" | from mangled name: {fixed}",
        f"// callees: {n_callees}, fixed from mangled names: {fixed_callees}",
        f"// decompile {ms:.0f} ms, completed: {res.decompileCompleted()}, error: {res.getErrorMessage()}",
        "// Mangled names carry no return type: a struct returned by value shows up as an",
        "// extra first pointer argument (the hidden return slot), shifting the names after it.",
    ])
    path = out_dir / f"{safe}.c"
    path.write_text(header + "\n" + body)
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
    elif args.cmd == "find":
        cmd_find(args.project_dir, args.needle, args.limit)
    else:
        cmd_decompile(args.project_dir, args.targets, args.out, args.save)
    return 0


if __name__ == "__main__":
    sys.exit(main())
