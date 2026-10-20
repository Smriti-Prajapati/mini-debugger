"use strict";

const state = {
  editor: null,
  compiled: false,
  debugActive: false,
  debugRunning: false,
  breakpoints: [],
  execDecorations: [],
  bpDecorations: [],
  currentLine: null,
};

const $ = id => document.getElementById(id);

const btnCompile    = $("btnCompile");
const btnRun        = $("btnRun");
const btnDebugStart = $("btnDebugStart");
const btnDebugRun   = $("btnDebugRun");
const btnStepOver   = $("btnStepOver");
const btnStepInto   = $("btnStepInto");
const btnStepOut    = $("btnStepOut");
const btnContinue   = $("btnContinue");
const btnDebugStop  = $("btnDebugStop");

require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min/vs" } });

require(["vs/editor/editor.main"], function () {
  state.editor = monaco.editor.create($("monacoEditor"), {
    language: "cpp",
    theme: "vs-dark",
    value: "",
    fontSize: 13,
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
    fontLigatures: true,
    lineNumbers: "on",
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    renderLineHighlight: "line",
    glyphMargin: true,
    folding: false,
    wordWrap: "off",
    automaticLayout: true,
    tabSize: 4,
    insertSpaces: true,
    scrollbar: { vertical: "auto", horizontal: "auto" },
  });

  state.editor.onMouseDown(e => {
    if (!state.debugActive) return;
    const { type, position } = e.target;
    if (type === 2 || type === 3) toggleBreakpoint(position.lineNumber);
  });

  $("programOutput").innerHTML = '<span class="placeholder">Program output will appear here after running.</span>';
  $("debugLog").innerHTML = '<span class="placeholder">Debugger events will appear here.</span>';

  document.addEventListener("keydown", e => {
    if (e.ctrlKey && e.key === "b") { e.preventDefault(); handleCompile(); }
    if (!state.debugActive) return;
    if (e.key === "F5")  { e.preventDefault(); handleDebugRun(); }
    if (e.key === "F8")  { e.preventDefault(); handleContinue(); }
    if (e.key === "F10") { e.preventDefault(); handleStepOver(); }
    if (e.key === "F11" && !e.shiftKey) { e.preventDefault(); handleStepInto(); }
    if (e.key === "F11" &&  e.shiftKey) { e.preventDefault(); handleStepOut(); }
  });

  if (window.lucide) lucide.createIcons();
});

// Compile

btnCompile.addEventListener("click", handleCompile);

async function handleCompile() {
  if (!state.editor) return;
  const source = state.editor.getValue();
  if (!source.trim()) { toast("Editor is empty", "error"); return; }
  if (state.debugActive) await handleDebugStop();

  setStatus("running", "Compilingâ€¦");
  btnCompile.disabled = true;

  try {
    const res  = await fetch("/api/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    const data = await res.json();

    renderDiagnostics(data.errors || []);
    switchTab("compiler");

    const errorCount = (data.errors || []).filter(e => e.type === "error").length;
    const warnCount  = (data.errors || []).filter(e => e.type === "warning").length;

    if (data.success) {
      state.compiled = true;
      updateDebugButtons();
      setStatus("exited", "Compiled OK");
      logDebug(`Compiled successfully. ${warnCount} warning(s).`);
      toast(`Compiled successfully${warnCount ? ` (${warnCount} warning${warnCount > 1 ? "s" : ""})` : ""}`, "success");
    } else {
      state.compiled = false;
      updateDebugButtons();
      setStatus("error", `${errorCount} error(s)`);
      logDebug(`Compilation failed: ${errorCount} error(s), ${warnCount} warning(s).`);
      toast(`Compilation failed: ${errorCount} error(s)`, "error");
    }
  } catch (e) {
    toast("Network error during compile", "error");
    setStatus("error", "Network error");
  } finally {
    btnCompile.disabled = false;
  }
}

// Run

btnRun.addEventListener("click", handleRun);

async function handleRun() {
  if (!state.compiled) { toast("Compile first", "error"); return; }

  setStatus("running", "Runningâ€¦");
  btnRun.disabled = true;
  $("programOutput").innerHTML = "";
  switchTab("output");

  try {
    const res  = await fetch("/api/run", { method: "POST" });
    const data = await res.json();

    if (data.success || data.stdout !== undefined) {
      const out = (data.stdout || "") + (data.stderr ? `\n[stderr]\n${data.stderr}` : "");
      $("programOutput").textContent = out || "(no output)";
      setStatus(data.exit_code === 0 ? "exited" : "error",
                data.exit_code === 0 ? "Exited (0)" : `Exited (${data.exit_code})`);
      logDebug(`Process exited with code ${data.exit_code}`);
    } else {
      $("programOutput").textContent = data.error || "Run failed.";
      setStatus("error", "Runtime error");
    }
  } catch (e) {
    toast("Network error during run", "error");
    setStatus("error", "Network error");
  } finally {
    btnRun.disabled = false;
  }
}

// Debug: start / stop

btnDebugStart.addEventListener("click", handleDebugStart);

async function handleDebugStart() {
  if (!state.compiled) { toast("Compile first", "error"); return; }

  btnDebugStart.disabled = true;
  setStatus("running", "Starting GDBâ€¦");

  try {
    const res  = await fetch("/api/debug/start", { method: "POST" });
    const data = await res.json();

    if (data.success) {
      state.debugActive  = true;
      state.debugRunning = false;
      state.breakpoints  = [];
      clearExecDecoration();
      updateDebugButtons();
      setStatus("stopped", "Ready â€” set breakpoints");
      logDebug("GDB session started. Set breakpoints then click â–¶ Run.");
      toast("Debug session started", "success");
      renderBreakpointList();
    } else {
      setStatus("error", "GDB error");
      toast(data.error || "Failed to start GDB", "error");
      btnDebugStart.disabled = false;
    }
  } catch (e) {
    toast("Network error", "error");
    btnDebugStart.disabled = false;
  }
}

btnDebugStop.addEventListener("click", handleDebugStop);

async function handleDebugStop() {
  try { await fetch("/api/debug/stop", { method: "POST" }); } catch (_) {}

  state.debugActive  = false;
  state.debugRunning = false;
  state.breakpoints  = [];
  clearExecDecoration();
  clearBpDecorations();
  renderBreakpointList();
  updateDebugButtons();
  setStatus("exited", "Session stopped");
  logDebug("Debug session ended.");
  renderVariables([]);
  renderStack([]);
  renderStatusPanel({});
}

// Debug: execution controls

btnDebugRun.addEventListener("click", () => execDebugCommand("/api/debug/run",       "Runningâ€¦"));
btnStepOver.addEventListener("click", () => execDebugCommand("/api/debug/step-over", "Steppingâ€¦"));
btnStepInto.addEventListener("click", () => execDebugCommand("/api/debug/step-into", "Steppingâ€¦"));
btnStepOut .addEventListener("click", () => execDebugCommand("/api/debug/step-out",  "Steppingâ€¦"));
btnContinue.addEventListener("click", () => execDebugCommand("/api/debug/continue",  "Continuingâ€¦"));

async function handleDebugRun()  { await execDebugCommand("/api/debug/run",       "Runningâ€¦"); }
async function handleStepOver()  { await execDebugCommand("/api/debug/step-over", "Steppingâ€¦"); }
async function handleStepInto()  { await execDebugCommand("/api/debug/step-into", "Steppingâ€¦"); }
async function handleStepOut()   { await execDebugCommand("/api/debug/step-out",  "Steppingâ€¦"); }
async function handleContinue()  { await execDebugCommand("/api/debug/continue",  "Continuingâ€¦"); }

async function execDebugCommand(url, statusMsg) {
  if (!state.debugActive) return;
  setDebugBusy(true, statusMsg);
  switchTab("output");
  try {
    const res  = await fetch(url, { method: "POST" });
    const data = await res.json();
    if (!data.success && data.error) {
      toast(data.error, "error");
      logDebug(`Error: ${data.error}`);
    }
    applyDebugState(data);
  } catch (e) {
    toast("Network error", "error");
  } finally {
    setDebugBusy(false);
  }
}

// Breakpoints

async function toggleBreakpoint(line) {
  if (!state.debugActive) return;
  const existing = state.breakpoints.find(bp => bp.line === line);
  if (existing) await removeBreakpoint(existing.number, line);
  else await addBreakpoint(line);
}

async function addBreakpoint(line) {
  try {
    const res  = await fetch("/api/debug/breakpoint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line }),
    });
    const data = await res.json();
    if (data.success && data.breakpoint) {
      const bp = { number: data.breakpoint.number, line: data.breakpoint.line || line };
      state.breakpoints.push(bp);
      logDebug(`Breakpoint ${bp.number} set at line ${bp.line}`);
    } else {
      toast(data.error || "Could not set breakpoint", "error");
      logDebug(`Failed to set breakpoint at line ${line}: ${data.error || "unknown error"}`);
    }
  } catch (e) {
    toast("Network error", "error");
  }
  renderBreakpointList();
  renderBpDecorations();
}

async function removeBreakpoint(bpNumber, line) {
  try {
    const res  = await fetch(`/api/debug/breakpoint/${bpNumber}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      state.breakpoints = state.breakpoints.filter(bp => bp.number !== bpNumber);
      logDebug(`Breakpoint ${bpNumber} removed (line ${line})`);
    } else {
      toast(data.error || "Could not remove breakpoint", "error");
    }
  } catch (e) {
    toast("Network error", "error");
  }
  renderBreakpointList();
  renderBpDecorations();
}

// Apply debug state

function applyDebugState(data) {
  if (!data) return;
  const { status, location, variables, stack, program_output } = data;

  if (program_output && program_output.length > 0) {
    $("programOutput").textContent = program_output.join("");
    switchTab("output");
  }

  if (status === "exited") {
    const code = location && location.exit_code != null ? ` (${location.exit_code})` : "";
    setStatus("exited", `Exited${code}`);
    logDebug(`Program exited. Reason: ${(location && location.reason) || "exited"}${code}`);
    clearExecDecoration();
    renderVariables([]);
    renderStack([]);
    renderStatusPanel({});
  } else if (status === "stopped") {
    setStatus("stopped", `Paused â€” line ${(location && location.line) || "?"}`);
    if (location && location.line) {
      highlightExecLine(location.line);
      logDebug(`Stopped at ${location.func || ""}:${location.line} (${location.reason || ""})`);
    }
    renderVariables(variables || []);
    renderStack(stack || []);
    renderStatusPanel(location || {});
  } else if (status === "running") {
    setStatus("running", "Runningâ€¦");
    clearExecDecoration();
  } else if (status === "not_started") {
    setStatus("stopped", "Ready");
  }

  state.debugRunning = (status === "running");
  updateDebugButtons();
}

// Rendering

function renderDiagnostics(errors) {
  const list  = $("diagnosticsList");
  const badge = $("compilerBadge");
  const errCount = errors.filter(e => e.type === "error").length;

  if (errors.length === 0) {
    list.innerHTML = '<span class="placeholder">No diagnostics.</span>';
    badge.textContent = "0";
    badge.classList.add("hidden");
    return;
  }

  badge.textContent = errCount;
  badge.classList.toggle("hidden", errCount === 0);

  list.innerHTML = errors.map(e => {
    const icon = e.type === "error" ? "x-circle" : e.type === "warning" ? "alert-triangle" : "info";
    return `
      <div class="diag-item ${e.type}">
        <span class="diag-icon"><i data-lucide="${icon}"></i></span>
        <span class="diag-loc">${e.line ? `L${e.line}` : "â€”"}</span>
        <span class="diag-msg">${escHtml(e.message)}</span>
      </div>`;
  }).join("");

  if (window.lucide) lucide.createIcons();
}

function renderVariables(variables) {
  const panel = $("varPanel");
  if (!variables || variables.length === 0) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = `
    <table class="var-table">
      <thead><tr><th>Name</th><th>Type</th><th>Value</th></tr></thead>
      <tbody>${variables.map(v => `
        <tr>
          <td class="var-name">${escHtml(v.name)}</td>
          <td class="var-type">${escHtml(v.type || "")}</td>
          <td class="var-value">${escHtml(v.value || "<unavailable>")}</td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderStack(frames) {
  const panel = $("stackPanel");
  if (!frames || frames.length === 0) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = frames.map((f, i) => `
    <div class="stack-frame ${i === 0 ? "current" : ""}">
      <div class="frame-func"><span class="frame-level">#${f.level}</span>${escHtml(f.func || "??")}</div>
      <div class="frame-loc">${escHtml(f.file || "")}${f.line ? `:${f.line}` : ""}</div>
    </div>`).join("");
}

function renderStatusPanel(location) {
  const panel = $("debugStatusPanel");
  if (!location || Object.keys(location).length === 0) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = [["Reason", location.reason], ["Function", location.func], ["Line", location.line]]
    .map(([k, v]) => `<div class="status-row"><span class="key">${k}</span><span class="val accent">${escHtml(String(v || "â€”"))}</span></div>`)
    .join("");
}

function renderBreakpointList() {
  const list = $("bpList");
  if (state.breakpoints.length === 0) {
    list.innerHTML = '<li class="list-empty">No breakpoints set</li>';
    return;
  }
  const sorted = [...state.breakpoints].sort((a, b) => a.line - b.line);
  list.innerHTML = sorted.map(bp => `
    <li class="bp-item" data-bp="${bp.number}">
      <span class="bp-dot"></span>
      <span class="bp-line">Line ${bp.line}</span>
      <button class="bp-remove" data-bp="${bp.number}" data-line="${bp.line}">
        <i data-lucide="x"></i>
      </button>
    </li>`).join("");

  list.querySelectorAll(".bp-remove").forEach(btn => {
    btn.addEventListener("click", () =>
      removeBreakpoint(parseInt(btn.dataset.bp), parseInt(btn.dataset.line))
    );
  });

  if (window.lucide) lucide.createIcons();
}

// Monaco decorations

function highlightExecLine(line) {
  if (!state.editor) return;
  state.currentLine = line;
  state.execDecorations = state.editor.deltaDecorations(state.execDecorations, [{
    range: new monaco.Range(line, 1, line, 1),
    options: {
      isWholeLine: true,
      className: "exec-line-decoration",
      glyphMarginClassName: "exec-line-gutter",
      overviewRuler: { color: "#388bfd", position: monaco.editor.OverviewRulerLane.Left },
    },
  }]);
  state.editor.revealLineInCenterIfOutsideViewport(line);
}

function clearExecDecoration() {
  if (!state.editor) return;
  state.execDecorations = state.editor.deltaDecorations(state.execDecorations, []);
  state.currentLine = null;
}

function renderBpDecorations() {
  if (!state.editor) return;
  state.bpDecorations = state.editor.deltaDecorations(state.bpDecorations,
    state.breakpoints.map(bp => ({
      range: new monaco.Range(bp.line, 1, bp.line, 1),
      options: {
        glyphMarginClassName: "bp-gutter-decoration",
        overviewRuler: { color: "#f85149", position: monaco.editor.OverviewRulerLane.Right },
      },
    }))
  );
}

function clearBpDecorations() {
  if (!state.editor) return;
  state.bpDecorations = state.editor.deltaDecorations(state.bpDecorations, []);
}

// Status and button state

function setStatus(dotClass, labelText) {
  $("statusDot").className = `status-dot ${dotClass}`;
  $("statusLabel").textContent = labelText;
}

function updateDebugButtons() {
  const { compiled, debugActive, debugRunning } = state;
  const debugStopped = debugActive && !debugRunning;

  btnRun        .disabled = !compiled || debugActive;
  btnDebugStart .disabled = !compiled || debugActive;
  btnDebugStop  .disabled = !debugActive;
  btnDebugRun   .disabled = !debugActive || debugRunning;
  btnStepOver   .disabled = !debugStopped;
  btnStepInto   .disabled = !debugStopped;
  btnStepOut    .disabled = !debugStopped;
  btnContinue   .disabled = !debugStopped;
}

function setDebugBusy(busy, statusMsg) {
  state.debugRunning = busy;
  if (busy) setStatus("running", statusMsg || "Runningâ€¦");
  updateDebugButtons();
}

function resetCompiledState() {
  state.compiled = state.debugActive = state.debugRunning = false;
  state.breakpoints = [];
  clearExecDecoration();
  clearBpDecorations();
  renderBreakpointList();
  updateDebugButtons();
  setStatus("", "Not started");
}

// Tabs

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  $("tabOutput")  .classList.toggle("hidden", name !== "output");
  $("tabCompiler").classList.toggle("hidden", name !== "compiler");
  $("tabDebuglog").classList.toggle("hidden", name !== "debuglog");
}

// Bottom panel: collapse toggle + drag-to-resize

const bottomPanel = $("bottomPanel");
const workspace   = document.querySelector(".workspace");

$("panelToggle").addEventListener("click", () => {
  bottomPanel.classList.toggle("collapsed");
  workspace.classList.toggle("panel-collapsed");
});

(function initResize() {
  const handle = $("panelResizeHandle");
  if (!handle) return;

  let startY = 0;
  let startH = 0;

  handle.addEventListener("mousedown", e => {
    e.preventDefault();
    startY = e.clientY;
    startH = bottomPanel.getBoundingClientRect().height;

    // Remove collapsed state when user starts dragging
    bottomPanel.classList.remove("collapsed");
    workspace.classList.remove("panel-collapsed");

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup",   onMouseUp);
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  });

  function onMouseMove(e) {
    const delta  = startY - e.clientY; // dragging up = bigger panel
    const newH   = Math.max(80, Math.min(startH + delta, window.innerHeight * 0.8));
    bottomPanel.style.height = newH + "px";
    workspace.style.height   = `calc(100vh - var(--topbar-h) - ${newH}px)`;
    if (state.editor) state.editor.layout();
  }

  function onMouseUp() {
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup",   onMouseUp);
    document.body.style.cursor    = "";
    document.body.style.userSelect = "";
  }
})();

// Debug log

function logDebug(msg) {
  const pre = $("debugLog");
  const placeholder = pre.querySelector(".placeholder");
  if (placeholder) placeholder.remove();
  pre.textContent += `[${new Date().toLocaleTimeString("en-US", { hour12: false })}] ${msg}\n`;
  pre.scrollTop = pre.scrollHeight;
}

// Toast

function toast(msg, type = "") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => {
    el.classList.add("fade-out");
    el.addEventListener("transitionend", () => el.remove());
  }, 2200);
}

// Utilities

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

