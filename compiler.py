"""
compiler.py - Handles C++ compilation using g++.

Writes source to a temp directory, invokes g++ with debug symbols,
parses the output into structured diagnostics, and returns results.

On Windows with MinGW, the compiled binary needs runtime DLLs (libstdc++-6.dll,
libgcc_s_seh-1.dll, libwinpthread-1.dll) that live alongside g++. We copy them
into the temp directory so the executable is self-contained and GDB can run it
without PATH tricks.
"""

import os
import re
import subprocess
import tempfile
import shutil


def compile_source(source_code: str) -> dict:
    """
    Compile C++ source code with debug symbols.

    Returns a dict with:
        success   : bool
        binary    : str | None
        work_dir  : str | None
        errors    : list[dict]
        raw_output: str
    """
    work_dir = tempfile.mkdtemp(prefix="minidebug_")
    src_path = os.path.join(work_dir, "program.cpp")
    bin_path = os.path.join(work_dir, "program")

    if os.name == "nt":
        bin_path = bin_path + ".exe"

    try:
        # Monaco sends \r\n on Windows; g++ counts each \r and \n as separate lines.
        normalized_source = source_code.replace('\r\n', '\n').replace('\r', '\n')
        with open(src_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(normalized_source)
    except OSError as e:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _error_result(None, [], f"Failed to write source file: {e}")

    if os.name == "nt":
        _copy_mingw_dlls(work_dir)

    cmd = ["g++", "-g", "-O0", "-Wall", "-Wextra", src_path, "-o", bin_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _error_result(None, [], "g++ not found. Please install MinGW-w64 or GCC.")
    except subprocess.TimeoutExpired:
        shutil.rmtree(work_dir, ignore_errors=True)
        return _error_result(None, [], "Compilation timed out after 30 seconds.")

    raw = result.stderr
    diagnostics = _parse_diagnostics(raw, src_path)

    if result.returncode != 0:
        return {"success": False, "binary": None, "work_dir": work_dir,
                "errors": diagnostics, "raw_output": raw}

    return {"success": True, "binary": bin_path, "work_dir": work_dir,
            "errors": diagnostics, "raw_output": raw}


def cleanup_work_dir(work_dir: str) -> None:
    if work_dir and os.path.isdir(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)


def _error_result(work_dir, diagnostics, message):
    return {
        "success": False, "binary": None, "work_dir": work_dir,
        "errors": diagnostics + [{"type": "error", "line": None,
                                   "column": None, "message": message}],
        "raw_output": message,
    }


_DIAG_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s+(?P<kind>error|warning|note):\s+(?P<msg>.+)$"
)


def _parse_diagnostics(raw: str, src_path: str) -> list:
    diagnostics = []
    seen = set()
    for line in raw.splitlines():
        m = _DIAG_RE.match(line.strip())
        if m:
            key = (m.group("line"), m.group("msg"))
            if key in seen:
                continue
            seen.add(key)
            diagnostics.append({
                "type": m.group("kind"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "message": m.group("msg").strip(),
            })
    return diagnostics


def _copy_mingw_dlls(work_dir: str) -> None:
    """Copy MinGW runtime DLLs into work_dir so the binary runs standalone under GDB."""
    try:
        result = subprocess.run(["where", "g++"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return
        mingw_bin = os.path.dirname(result.stdout.strip().split('\n')[0].strip())
        for dll in ["libstdc++-6.dll", "libgcc_s_seh-1.dll", "libgcc_s_dw2-1.dll", "libwinpthread-1.dll"]:
            src = os.path.join(mingw_bin, dll)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(work_dir, dll))
    except Exception:
        pass
