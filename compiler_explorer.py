"""
compiler_explorer.py — Compiler inspection features.

Three output types from C++ source:

1. Assembly (-S): x86-64 Intel-syntax showing how the compiler maps
   source constructs to machine instructions. Architecture-specific.

2. GIMPLE dump (-fdump-tree-gimple): GCC's first internal IR after parsing.
   C++ constructs are lowered to simple three-address statements before
   any optimization pass runs.

3. Compiler info: version, target triple, flag explanations, pipeline stages.
"""

import os
import re
import glob
import subprocess
import tempfile
import shutil


def get_compiler_info() -> dict:
    try:
        ver = subprocess.run(["g++", "--version"], capture_output=True, text=True, timeout=5)
        tgt = subprocess.run(["g++", "-dumpmachine"], capture_output=True, text=True, timeout=5)
        version_str = ver.stdout.strip().splitlines()[0] if ver.returncode == 0 else None
        target_str  = tgt.stdout.strip() if tgt.returncode == 0 else None
    except FileNotFoundError:
        version_str = target_str = None

    return {
        "compiler": "g++ (GCC)",
        "version":  version_str,
        "target":   target_str,
        "flags_used": {
            "-g":    "Embed DWARF debug symbols so GDB can map machine addresses to source lines, variable names, and types.",
            "-O0":   "Disable all optimizations. Variables stay in memory; steps match source lines exactly.",
            "-Wall": "Enable the most common warning classes.",
            "-Wextra": "Enable additional warnings beyond -Wall.",
            "-S":    "Stop after compilation; emit assembly (.s) instead of an object file.",
            "-fdump-tree-gimple": "Write a GIMPLE IR dump alongside the object file.",
        },
        "pipeline": [
            {"stage": "Preprocessing", "tool": "cpp",          "output": "Expanded source (.ii)"},
            {"stage": "Compilation",   "tool": "cc1plus",       "output": "Assembly (.s)"},
            {"stage": "Assembling",    "tool": "as",            "output": "Object file (.o)"},
            {"stage": "Linking",       "tool": "ld / collect2", "output": "Executable (.exe / ELF)"},
        ],
    }


def generate_assembly(source_code: str, opt_level: str = "O0") -> dict:
    """
    Compile source to x86-64 Intel-syntax assembly.

    opt_level: one of O0, O1, O2, O3, Os (default O0)
    Returns: { success, assembly, annotated, flags, note, error }
    """
    opt_level = _sanitize_opt(opt_level)
    work_dir  = tempfile.mkdtemp(prefix="minidebug_asm_")
    src_path  = os.path.join(work_dir, "program.cpp")
    asm_path  = os.path.join(work_dir, "program.s")

    _write_source(src_path, source_code)
    flags = ["g++", "-S", f"-{opt_level}", "-fverbose-asm", "-masm=intel", src_path, "-o", asm_path]

    try:
        result = subprocess.run(flags, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail("g++ not found.", flags)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail("Assembly generation timed out.", flags)

    if result.returncode != 0:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(result.stderr.strip() or "Compilation failed.", flags)

    try:
        with open(asm_path, "r", encoding="utf-8", errors="replace") as f:
            assembly_text = f.read()
    except OSError as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(f"Could not read assembly output: {e}", flags)

    shutil.rmtree(work_dir, ignore_errors=True)

    return {
        "success":   True,
        "assembly":  assembly_text,
        "annotated": _group_assembly(assembly_text),
        "flags":     flags,
        "error":     None,
        "note": (
            "Assembly is x86-64 Intel syntax, specific to this machine's architecture. "
            "With -fverbose-asm, GCC adds source-line comments. "
            "Higher optimization levels may produce more instructions due to inlining, "
            "but typically eliminate redundant loads and stores."
        ),
    }


def generate_gimple(source_code: str) -> dict:
    """
    Produce a GIMPLE intermediate-representation dump.

    GIMPLE reduces C++ to simple three-address statements (assignments,
    comparisons, gotos) before any optimization passes run.

    Returns: { success, gimple, flags, note, error }
    """
    work_dir = tempfile.mkdtemp(prefix="minidebug_gimple_")
    src_path = os.path.join(work_dir, "program.cpp")
    bin_path = os.path.join(work_dir, "program.exe" if os.name == "nt" else "program")

    _write_source(src_path, source_code)
    flags = ["g++", "-O0", "-fdump-tree-gimple", src_path, "-o", bin_path]

    try:
        result = subprocess.run(flags, capture_output=True, text=True, timeout=20, cwd=work_dir)
    except FileNotFoundError:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail("g++ not found.", flags)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail("GIMPLE dump timed out.", flags)

    if result.returncode != 0:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(result.stderr.strip() or "Compilation failed.", flags)

    # GCC writes the dump next to the source: program.cpp.007t.gimple
    # The numeric prefix varies by GCC version so we glob for it.
    dump_files = glob.glob(os.path.join(work_dir, "*.gimple")) or glob.glob("*.gimple")

    if not dump_files:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail("GIMPLE dump file not found. Your GCC version may use a different filename.", flags)

    try:
        with open(dump_files[0], "r", encoding="utf-8", errors="replace") as f:
            gimple_text = f.read()
    except OSError as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _fail(f"Could not read GIMPLE dump: {e}", flags)

    shutil.rmtree(work_dir, ignore_errors=True)

    return {
        "success": True,
        "gimple":  gimple_text,
        "flags":   flags,
        "error":   None,
        "note": (
            "GIMPLE is GCC's first high-level intermediate representation. "
            "Source constructs are lowered to simple three-address statements "
            "before optimization passes run."
        ),
    }


def _sanitize_opt(level: str) -> str:
    level = level.strip().lstrip("-")
    return level if level in ("O0", "O1", "O2", "O3", "Os") else "O0"


def _write_source(path: str, source_code: str) -> None:
    normalized = source_code.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)


def _fail(message: str, flags: list) -> dict:
    return {"success": False, "assembly": None, "gimple": None,
            "annotated": [], "flags": flags, "error": message}


_FUNC_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*:")


def _group_assembly(text: str) -> list:
    """Split assembly into per-function label groups for collapsible UI rendering."""
    groups  = []
    current = {"label": ".preamble", "lines": []}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if _FUNC_LABEL_RE.match(line) and not line.strip().startswith("."):
            if current["lines"]:
                groups.append(current)
            current = {"label": line.rstrip(":").strip(), "lines": []}
        else:
            current["lines"].append(line)

    if current["lines"]:
        groups.append(current)

    return groups
