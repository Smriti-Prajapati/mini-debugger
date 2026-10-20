"""
app.py - Flask routes and session management.

Sessions are keyed by a UUID cookie. Each session holds one GDBSession
and the temp directory from the most recent compile.

LOCAL-ONLY — do not expose to the public internet.
"""

import os
import re
import uuid
import subprocess
import threading
import time
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS

import compiler
import debugger
import compiler_explorer

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
CORS(app)

_sessions: dict[str, dict] = {}
_sessions_lock = threading.Lock()
_STALE_TIMEOUT = 600


def _get_or_create_session_id() -> str:
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    return session["sid"]


def _get_debug_session(sid: str):
    with _sessions_lock:
        entry = _sessions.get(sid)
    return entry.get("gdb_session") if entry else None


def _cleanup_session(sid: str) -> None:
    with _sessions_lock:
        entry = _sessions.pop(sid, None)
    if not entry:
        return
    gdb = entry.get("gdb_session")
    if gdb:
        gdb.stop()
    work_dir = entry.get("work_dir")
    if work_dir:
        compiler.cleanup_work_dir(work_dir)


def _reap_stale_sessions() -> None:
    while True:
        time.sleep(60)
        now = time.time()
        stale = []
        with _sessions_lock:
            for sid, entry in list(_sessions.items()):
                if now - entry.get("last_used", now) > _STALE_TIMEOUT:
                    stale.append(sid)
        for sid in stale:
            _cleanup_session(sid)


threading.Thread(target=_reap_stale_sessions, daemon=True).start()


def _touch(sid: str) -> None:
    with _sessions_lock:
        if sid in _sessions:
            _sessions[sid]["last_used"] = time.time()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/compile", methods=["POST"])
def api_compile():
    sid = _get_or_create_session_id()
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")

    if not source.strip():
        return jsonify({"success": False, "errors": [
            {"type": "error", "line": None, "column": None, "message": "No source code provided."}
        ], "raw_output": ""}), 400

    _cleanup_session(sid)
    result = compiler.compile_source(source)

    with _sessions_lock:
        _sessions[sid] = {
            "gdb_session": None,
            "work_dir": result.get("work_dir"),
            "binary": result.get("binary"),
            "source": source,
            "last_used": time.time(),
        }

    return jsonify({"success": result["success"], "errors": result["errors"],
                    "raw_output": result["raw_output"]})


@app.route("/api/run", methods=["POST"])
def api_run():
    sid = _get_or_create_session_id()
    _touch(sid)

    with _sessions_lock:
        entry = _sessions.get(sid)

    if not entry or not entry.get("binary"):
        return jsonify({"success": False, "error": "No compiled binary. Compile first."}), 400

    binary = entry["binary"]
    if not os.path.isfile(binary):
        return jsonify({"success": False, "error": "Binary not found. Please recompile."}), 400

    try:
        result = subprocess.run([binary], capture_output=True, text=True,
                                timeout=10, encoding="utf-8", errors="replace")
        return jsonify({"success": True, "stdout": result.stdout,
                        "stderr": result.stderr, "exit_code": result.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Program exceeded 10 second time limit.",
                        "stdout": "", "stderr": "", "exit_code": -1})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/debug/start", methods=["POST"])
def api_debug_start():
    sid = _get_or_create_session_id()
    _touch(sid)

    with _sessions_lock:
        entry = _sessions.get(sid)

    if not entry or not entry.get("binary"):
        return jsonify({"success": False, "error": "No compiled binary. Compile first."}), 400

    binary = entry["binary"]
    if not os.path.isfile(binary):
        return jsonify({"success": False, "error": "Binary not found. Please recompile."}), 400

    old_gdb = entry.get("gdb_session")
    if old_gdb:
        old_gdb.stop()

    gdb = debugger.GDBSession(binary)
    result = gdb.start()
    if not result["success"]:
        return jsonify(result), 500

    with _sessions_lock:
        if sid in _sessions:
            _sessions[sid]["gdb_session"] = gdb
            _sessions[sid]["last_used"] = time.time()

    return jsonify({"success": True, "status": "ready",
                    "message": "GDB session started. Set breakpoints, then click Run."})


@app.route("/api/debug/stop", methods=["POST"])
def api_debug_stop():
    sid = _get_or_create_session_id()
    _cleanup_session(sid)
    return jsonify({"success": True, "status": "not_started"})


@app.route("/api/debug/breakpoint", methods=["POST"])
def api_set_breakpoint():
    sid = _get_or_create_session_id()
    _touch(sid)
    data = request.get_json(silent=True) or {}
    line = data.get("line")
    if not isinstance(line, int) or line < 1:
        return jsonify({"success": False, "error": "Invalid line number."}), 400
    gdb = _get_debug_session(sid)
    if not gdb or not gdb.is_alive():
        return jsonify({"success": False, "error": "No active debug session."}), 400
    return jsonify(gdb.set_breakpoint(line))


@app.route("/api/debug/breakpoint/<int:bp_number>", methods=["DELETE"])
def api_remove_breakpoint(bp_number: int):
    sid = _get_or_create_session_id()
    _touch(sid)
    gdb = _get_debug_session(sid)
    if not gdb or not gdb.is_alive():
        return jsonify({"success": False, "error": "No active debug session."}), 400
    return jsonify(gdb.remove_breakpoint(bp_number))


@app.route("/api/debug/breakpoints", methods=["GET"])
def api_list_breakpoints():
    sid = _get_or_create_session_id()
    _touch(sid)
    gdb = _get_debug_session(sid)
    if not gdb or not gdb.is_alive():
        return jsonify({"success": True, "breakpoints": []})
    return jsonify(gdb.list_breakpoints())


@app.route("/api/debug/run",       methods=["POST"])
def api_debug_run():       return _exec_command(lambda gdb: gdb.run())

@app.route("/api/debug/continue",  methods=["POST"])
def api_debug_continue():  return _exec_command(lambda gdb: gdb.continue_exec())

@app.route("/api/debug/step-over", methods=["POST"])
def api_debug_step_over(): return _exec_command(lambda gdb: gdb.step_over())

@app.route("/api/debug/step-into", methods=["POST"])
def api_debug_step_into(): return _exec_command(lambda gdb: gdb.step_into())

@app.route("/api/debug/step-out",  methods=["POST"])
def api_debug_step_out():  return _exec_command(lambda gdb: gdb.step_out())


@app.route("/api/debug/state", methods=["GET"])
def api_debug_state():
    sid = _get_or_create_session_id()
    _touch(sid)
    gdb = _get_debug_session(sid)
    if not gdb or not gdb.is_alive():
        return jsonify({"success": True, "status": "not_started",
                        "location": {}, "variables": [], "stack": [], "program_output": []})

    status = gdb.get_execution_status()
    location = gdb.get_current_location()
    variables = []
    stack = []
    if status == "stopped":
        variables = gdb.get_variables().get("variables", [])
        stack = gdb.get_stack().get("frames", [])

    return jsonify({"success": True, "status": status, "location": location,
                    "variables": variables, "stack": stack,
                    "program_output": gdb.get_program_output()})


@app.route("/api/examples", methods=["GET"])
def api_examples():
    examples_dir = os.path.join(os.path.dirname(__file__), "examples")
    try:
        files = sorted(f for f in os.listdir(examples_dir) if f.endswith(".cpp"))
        return jsonify({"success": True, "examples": files})
    except Exception:
        return jsonify({"success": True, "examples": []})


@app.route("/api/examples/<filename>", methods=["GET"])
def api_example_source(filename: str):
    if not re.match(r'^[\w\-]+\.cpp$', filename):
        return jsonify({"success": False, "error": "Invalid filename."}), 400
    examples_dir = os.path.join(os.path.dirname(__file__), "examples")
    path = os.path.join(examples_dir, filename)
    if not os.path.abspath(path).startswith(os.path.abspath(examples_dir)):
        return jsonify({"success": False, "error": "Access denied."}), 403
    if not os.path.isfile(path):
        return jsonify({"success": False, "error": "Example not found."}), 404
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    return jsonify({"success": True, "source": source, "filename": filename})


@app.route("/api/explore/info", methods=["GET"])
def api_explore_info():
    return jsonify(compiler_explorer.get_compiler_info())


@app.route("/api/explore/assembly", methods=["POST"])
def api_explore_assembly():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "").strip()
    opt_level = data.get("opt_level", "O0")
    if not source:
        return jsonify({"success": False, "error": "No source code provided."}), 400
    if len(source) > 100_000:
        return jsonify({"success": False, "error": "Source too large (max 100 KB)."}), 400
    return jsonify(compiler_explorer.generate_assembly(source, opt_level))


@app.route("/api/explore/gimple", methods=["POST"])
def api_explore_gimple():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "").strip()
    if not source:
        return jsonify({"success": False, "error": "No source code provided."}), 400
    if len(source) > 100_000:
        return jsonify({"success": False, "error": "Source too large (max 100 KB)."}), 400
    return jsonify(compiler_explorer.generate_gimple(source))


def _exec_command(fn):
    sid = _get_or_create_session_id()
    _touch(sid)
    gdb = _get_debug_session(sid)
    if not gdb or not gdb.is_alive():
        return jsonify({"success": False,
                        "error": "No active debug session. Start debugging first."}), 400
    try:
        return jsonify(fn(gdb))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("Mini Debugger — http://127.0.0.1:5000")
    print("NOTE: This is a local-only tool. Do not expose to the internet.")
    app.run(debug=False, host="127.0.0.1", port=5000)
