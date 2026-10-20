"""
debugger.py - Manages a persistent GDB session using the MI2 protocol.

GDB MI2 output line prefixes:
  ^  result record      (^done, ^error, ^running)
  *  async exec record  (*stopped, *running)
  =  async notify       (=thread-created, =library-loaded)
  ~  console stream     (human-readable GDB text)
  @  target stream      (inferior stdout — unreliable on Windows MinGW)
  &  log stream         (GDB internal messages)

Execution command flow:
  1. Send command  →  GDB replies  <token>^running
  2. Async events arrive  (library loads, thread events)
  3. Execution stops  →  *stopped,reason="...",frame={...}
  4. GDB prompt  (gdb)
"""

import re
import subprocess
import threading
import queue
import time


class GDBSession:
    """
    Wraps a single GDB process. Thread-safe — Flask request threads call public methods.
    """

    def __init__(self, binary_path: str):
        self.binary_path = binary_path
        self.process = None
        self._reader_thread = None
        self._output_queue = queue.Queue()
        self._program_output = []
        self._lock = threading.Lock()
        self._token = 0
        self._stopped_info = {}
        self._is_running = False
        self._started = False

    def start(self) -> dict:
        if self._started:
            return {"success": False, "error": "Session already started."}
        cmd = ["gdb", "--interpreter=mi2", "--quiet", self.binary_path]
        try:
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError:
            return {"success": False, "error": "GDB not found. Please install GDB."}
        except OSError as e:
            return {"success": False, "error": f"Failed to start GDB: {e}"}

        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()
        self._drain_until_prompt(timeout=5)
        self._started = True
        return {"success": True}

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            try:
                self._send_raw("-gdb-exit\n")
                self.process.wait(timeout=3)
            except Exception:
                self.process.kill()
        self._started = False
        self._is_running = False

    def is_alive(self) -> bool:
        return self._started and self.process is not None and self.process.poll() is None

    def set_breakpoint(self, line: int) -> dict:
        resp = self._send_command(f"-break-insert {line}")
        if resp["class"] == "done":
            return {"success": True, "breakpoint": _parse_bkpt_block(resp["payload"])}
        return {"success": False, "error": _extract_error(resp)}

    def remove_breakpoint(self, bp_number: int) -> dict:
        resp = self._send_command(f"-break-delete {bp_number}")
        if resp["class"] == "done":
            return {"success": True}
        return {"success": False, "error": _extract_error(resp)}

    def list_breakpoints(self) -> dict:
        resp = self._send_command("-break-list")
        if resp["class"] == "done":
            return {"success": True, "breakpoints": _parse_bkpt_table(resp["payload"])}
        return {"success": True, "breakpoints": []}

    def run(self) -> dict:
        with self._lock:
            self._program_output.clear()
            self._stopped_info = {}
        resp = self._send_command("-exec-run", wait_for_stop=True, timeout=10)
        return self._build_state(resp)

    def continue_exec(self) -> dict:
        resp = self._send_command("-exec-continue", wait_for_stop=True, timeout=10)
        return self._build_state(resp)

    def step_over(self) -> dict:
        resp = self._send_command("-exec-next", wait_for_stop=True, timeout=8)
        return self._build_state(resp)

    def step_into(self) -> dict:
        resp = self._send_command("-exec-step", wait_for_stop=True, timeout=8)
        return self._build_state(resp)

    def step_out(self) -> dict:
        resp = self._send_command("-exec-finish", wait_for_stop=True, timeout=8)
        return self._build_state(resp)

    def interrupt(self) -> dict:
        resp = self._send_command("-exec-interrupt", wait_for_stop=True, timeout=3)
        return self._build_state(resp)

    def get_variables(self) -> dict:
        resp = self._send_command("-stack-list-variables --simple-values")
        if resp["class"] == "done":
            return {"success": True, "variables": _parse_variables(resp["payload"])}
        return {"success": True, "variables": []}

    def get_stack(self) -> dict:
        resp = self._send_command("-stack-list-frames")
        if resp["class"] == "done":
            return {"success": True, "frames": _parse_frames(resp["payload"])}
        return {"success": True, "frames": []}

    def get_program_output(self) -> list:
        with self._lock:
            return list(self._program_output)

    def get_current_location(self) -> dict:
        with self._lock:
            return dict(self._stopped_info)

    def get_execution_status(self) -> str:
        if not self._started:
            return "not_started"
        with self._lock:
            reason = self._stopped_info.get("reason", "")
        if "exited" in reason:
            return "exited"
        with self._lock:
            running = self._is_running
        if running:
            return "running"
        if self._stopped_info:
            return "stopped"
        return "not_started"

    def _next_token(self) -> int:
        with self._lock:
            self._token += 1
            return self._token

    def _send_raw(self, text: str) -> None:
        if self.process and self.process.poll() is None:
            self.process.stdin.write(text)
            self.process.stdin.flush()

    def _send_command(self, cmd: str, wait_for_stop: bool = False, timeout: float = 5) -> dict:
        token = self._next_token()
        self._send_raw(f"{token}{cmd}\n")
        lines = self._collect_response(token, wait_for_stop=wait_for_stop, timeout=timeout)
        return _parse_result_record(token, lines)

    def _collect_response(self, token: int, wait_for_stop: bool, timeout: float) -> list:
        collected = []
        deadline = time.monotonic() + timeout
        got_result = False
        got_stop = False

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                line = self._output_queue.get(timeout=min(remaining, 0.15))
            except queue.Empty:
                if got_result and (not wait_for_stop or got_stop):
                    break
                continue

            collected.append(line)
            self._process_async_line(line)

            if line.startswith(str(token) + "^"):
                got_result = True
                with self._lock:
                    self._is_running = "running" in line[len(str(token)):].split(",")[0]

            if line.startswith("*stopped") or "reason=\"exited" in line:
                got_stop = True
                with self._lock:
                    self._is_running = False

            if "=thread-group-exited" in line and wait_for_stop:
                got_stop = True
                with self._lock:
                    self._is_running = False

            if got_result and (not wait_for_stop or got_stop):
                self._drain_tail(collected)
                break

        return collected

    def _process_async_line(self, line: str) -> None:
        if line.startswith("@"):
            with self._lock:
                self._program_output.append(_unescape_mi_str(line[1:].strip()))
            return
        if line.startswith("*stopped"):
            with self._lock:
                self._stopped_info = _parse_stopped_record(line)
                self._is_running = False
            return
        if line.startswith("*running"):
            with self._lock:
                self._is_running = True

    def _drain_tail(self, collected: list, wait: float = 0.08) -> None:
        time.sleep(wait)
        while True:
            try:
                extra = self._output_queue.get_nowait()
                collected.append(extra)
                self._process_async_line(extra)
            except queue.Empty:
                break

    def _drain_until_prompt(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self._output_queue.get(timeout=0.1)
            except queue.Empty:
                break

    def _read_output(self) -> None:
        try:
            for line in self.process.stdout:
                stripped = line.rstrip("\r\n")
                if stripped:
                    self._output_queue.put(stripped)
        except Exception:
            pass

    def _build_state(self, resp: dict) -> dict:
        status = self.get_execution_status()
        location = self.get_current_location()
        variables = []
        stack = []
        if status == "stopped":
            variables = self.get_variables().get("variables", [])
            stack = self.get_stack().get("frames", [])
        state = {
            "success": resp["class"] not in ("error", "timeout"),
            "status": status,
            "location": location,
            "variables": variables,
            "stack": stack,
            "program_output": self.get_program_output(),
        }
        if resp["class"] == "error":
            state["error"] = _extract_error(resp)
            state["success"] = False
        return state


def _parse_result_record(token: int, lines: list) -> dict:
    prefix = str(token) + "^"
    for line in lines:
        if line.startswith(prefix):
            rest = line[len(prefix):]
            comma = rest.find(",")
            if comma == -1:
                return {"class": rest.strip(), "payload": "", "raw_lines": lines}
            return {"class": rest[:comma], "payload": rest[comma + 1:], "raw_lines": lines}
    return {"class": "timeout", "payload": "", "raw_lines": lines}


def _unescape_mi_str(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "").replace("\\\\", "\\")


def _extract_error(resp: dict) -> str:
    m = re.search(r'msg="((?:[^"\\]|\\.)*)"', resp.get("payload", ""))
    if m:
        return _unescape_mi_str('"' + m.group(1) + '"')
    return resp.get("payload", "") or "Unknown GDB error"


def _parse_stopped_record(line: str) -> dict:
    """
    Parse a *stopped MI record.
    Example: *stopped,reason="breakpoint-hit",frame={func="main",file="...",line="4",...}
    """
    info = {}
    reason_m = re.search(r'reason="([^"]*)"', line)
    if reason_m:
        info["reason"] = reason_m.group(1)
    frame_m = re.search(r'frame=\{([^}]*)\}', line)
    if frame_m:
        for key in ("func", "file", "fullname", "line", "addr"):
            m = re.search(rf'{key}="([^"]*)"', frame_m.group(1))
            if m:
                val = m.group(1).replace("\\\\", "\\")
                info[key] = int(val) if key == "line" else val
    code_m = re.search(r'exit-code="([^"]*)"', line)
    if code_m:
        info["exit_code"] = code_m.group(1)
    return info


def _parse_bkpt_block(payload: str) -> dict:
    bp = {}
    bkpt_m = re.search(r'bkpt=\{([^}]+)\}', payload)
    block = bkpt_m.group(1) if bkpt_m else payload
    for key in ("number", "line", "file", "addr", "func"):
        m = re.search(rf'{key}="([^"]*)"', block)
        if m:
            val = m.group(1)
            bp[key] = int(val) if key in ("number", "line") else val
    return bp


def _parse_bkpt_table(payload: str) -> list:
    bps = []
    for block in re.findall(r'bkpt=\{([^}]+)\}', payload):
        bp = {}
        for key in ("number", "line", "file", "addr", "enabled", "type"):
            m = re.search(rf'{key}="([^"]*)"', block)
            if m:
                val = m.group(1)
                bp[key] = int(val) if key in ("number", "line") else val
        if "number" in bp:
            bps.append(bp)
    return bps


def _parse_variables(payload: str) -> list:
    """GDB returns: variables=[{name="x",type="int",value="10"},...]"""
    variables = []
    for block in re.findall(r'\{([^}]+)\}', payload):
        name_m = re.search(r'name="([^"]*)"', block)
        if not name_m:
            continue
        var = {"name": name_m.group(1)}
        type_m = re.search(r'type="([^"]*)"', block)
        if type_m:
            var["type"] = type_m.group(1)
        value_m = re.search(r'value="((?:[^"\\]|\\.)*)"', block)
        var["value"] = _unescape_mi_str('"' + value_m.group(1) + '"') if value_m else "<unavailable>"
        variables.append(var)
    return variables


def _parse_frames(payload: str) -> list:
    """GDB returns: stack=[frame={level="0",func="main",file="...",line="4",...},...]"""
    frames = []
    for block in re.findall(r'frame=\{([^}]+)\}', payload):
        frame = {}
        for key in ("level", "func", "file", "line", "addr"):
            m = re.search(rf'{key}="([^"]*)"', block)
            if m:
                val = m.group(1)
                frame[key] = int(val) if key in ("level", "line") else val
        if "level" in frame:
            frames.append(frame)
    return frames
