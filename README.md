# Mini Debugger

A graphical debugger for C++ programs, built as a desktop-style web application. Write or load a C++ program, compile it with debug symbols, and debug it through a clean browser-based interface backed by real GDB.

![Mini Debugger UI](docs/screenshot.png)
<!-- Add a screenshot after your first run -->

---

## Features

- **Code editor** — Monaco Editor with C++ syntax highlighting, line numbers, and gutter-click breakpoints
- **Real compilation** — invokes `g++ -g -O0` and displays structured errors with line/column info
- **Persistent GDB session** — one GDB process per browser session, kept alive between commands
- **Breakpoints** — set and remove by clicking the editor gutter or the sidebar list
- **Execution control** — Run, Continue, Step Over, Step Into, Step Out
- **Live variable inspection** — local variables with name, type, and current value after each pause
- **Call stack** — full function call hierarchy with file and line references
- **Current-line highlight** — the active execution line is highlighted in the editor in real time
- **Program output** — captured and displayed in the Output tab
- **Compiler diagnostics** — errors and warnings shown per-line with severity badges
- **Example programs** — loops, arrays, nested functions, factorial, and a syntax error example
- **Keyboard shortcuts** — `Ctrl+B` compile, `F5` run, `F8` continue, `F10` step over, `F11` step into, `Shift+F11` step out

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3 + Flask |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Editor | Monaco Editor 0.44 (CDN) |
| Icons | Lucide (CDN) |
| Compiler | g++ (MinGW-W64 on Windows, GCC on Linux) |
| Debugger | GDB 17+ with `--interpreter=mi2` |
| Communication | REST API (fetch) + synchronous command-response |

---

## Architecture

```
Browser (Monaco + Vanilla JS)
        │  fetch() REST calls
        ▼
Flask app.py  ──►  compiler.py  ──►  g++ subprocess
        │
        └────────►  debugger.py  ──►  GDB subprocess (--interpreter=mi2)
                         │
                         └── GDBSession: stdin/stdout pipes, background reader thread
```

### How GDB integration works

1. **Compilation** — `compiler.py` writes the source to a temp directory, runs `g++ -g -O0 -Wall`, and parses `stderr` into structured diagnostics `{type, line, column, message}`. On Windows, MinGW runtime DLLs are copied into the temp directory so the binary can run standalone.

2. **GDB MI2** — `debugger.py` launches GDB with `--interpreter=mi2`. This mode produces machine-readable output instead of human-readable text. Every command is prefixed with a numeric token (e.g. `42-exec-next`) and GDB responds with a result record prefixed by the same token (e.g. `42^done,...`).

3. **Async output** — A background reader thread continuously reads GDB's stdout into a `queue.Queue`. When an execution command is sent, the main thread waits for both:
   - The result record (`^running` or `^done`)
   - The async stop event (`*stopped,reason="...",frame={...}`)

4. **State extraction** — After each stop, the session calls `-stack-list-variables --simple-values` and `-stack-list-frames` to retrieve the current local variables and call stack via MI2 structured output.

5. **Session lifecycle** — Each browser session (identified by a UUID cookie) owns one `GDBSession`. Sessions are cleaned up when the user clicks Stop, when a new compile replaces the binary, or when the background reaper finds them idle for 10 minutes.

### Debugging workflow

```
User clicks Compile
  → POST /api/compile → g++ → diagnostics JSON → rendered in Compiler tab

User clicks Debug
  → POST /api/debug/start → GDB launched with binary

User clicks gutter line N
  → POST /api/debug/breakpoint {line: N}
  → GDB: -break-insert N → ^done,bkpt={number="1",line="N",...}
  → Red dot appears in editor gutter

User clicks Run (▶)
  → POST /api/debug/run → GDB: -exec-run
  → GDB runs until breakpoint → *stopped,reason="breakpoint-hit",frame={line="N",...}
  → Backend responds with {status, location, variables, stack}
  → Editor highlights line N, variables panel fills, call stack fills

User clicks Step Over
  → POST /api/debug/step-over → GDB: -exec-next
  → *stopped,reason="end-stepping-range",frame={line="N+1",...}
  → UI updates to new line
```

---

## Prerequisites

### Windows (MinGW-W64)

1. Install [MSYS2](https://www.msys2.org/) or [MinGW-W64](https://winlibs.com/) — ensure `g++` and `gdb` are on your `PATH`
2. Python 3.10+ — ensure `python` and `pip` are on your `PATH`

Verify:
```powershell
g++ --version    # should print g++ 12+ or newer
gdb --version    # should print GDB 12+ or newer
python --version # Python 3.10+
```

### Linux / WSL2

```bash
sudo apt install build-essential gdb python3 python3-pip
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/mini-debugger.git
cd mini-debugger

# Install Python dependencies
pip install -r requirements.txt
```

No other installation is required. Monaco Editor and Lucide icons load from CDN on first page load.

---

## Running the Application

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

> **Note:** This application is local-only. Do not expose port 5000 to the public internet. See [Security Considerations](#security-considerations) below.

---

## Example Debugging Walkthrough

1. Open http://127.0.0.1:5000
2. Click **loops** in the Examples sidebar — the loop program loads into the editor
3. Click **Compile** (or press `Ctrl+B`) — the status bar shows "Compiled OK"
4. Click **Debug** — the status bar shows "Ready — set breakpoints"
5. Click the gutter next to line `9` (`sum += i`) — a red dot appears
6. Click **▶** (Run) — execution pauses at line 9, `i = 1`, `sum = 0`
7. Click **→** (Step Over) repeatedly — watch `i` and `sum` change each iteration
8. Click the **Variables** panel to see current values after each step
9. Click **⏩** (Continue) — execution runs to the next breakpoint hit or end
10. Click **■** (Stop) — session ends, gutter clears

---

## Project Structure

```
mini-debugger/
├── app.py          Flask routes and session management
├── compiler.py     g++ compilation and diagnostic parsing
├── debugger.py     GDB MI2 session wrapper
├── requirements.txt
├── templates/
│   └── index.html  Single-page workspace layout
├── static/
│   ├── css/
│   │   └── style.css  Dark theme, full layout
│   └── js/
│       └── app.js     Editor, debug controls, state rendering
├── examples/
│   ├── loops.cpp
│   ├── arrays.cpp
│   ├── functions.cpp
│   ├── factorial.cpp
│   └── syntax_error.cpp
└── README.md
```

---

## Known Limitations

- **Local only** — no authentication, no sandboxing beyond a temp directory. Do not run on a shared or public machine.
- **One session per browser** — sessions are identified by a cookie; multiple tabs share one GDB process.
- **Program output on Windows** — GDB's MI `@`-stream does not capture `std::cout` output on Windows MinGW. The **Run** button (non-debug mode) captures output correctly. During a debug session, output flushed before a breakpoint may not appear until execution ends.
- **Infinite loops** — a program running without a breakpoint will hold the GDB session until Stop is clicked. There is a 10-second timeout on the direct Run command.
- **No conditional breakpoints or watch expressions** — the interface exposes GDB's basic operations only.
- **No multi-file projects** — one source file per session.
- **No remote debugging** — GDB runs on the same machine as the server.

---

## Security Considerations

This tool is designed for **local development use only**.

- Source code is written to `tempfile.mkdtemp()` directories and compiled there. It does not access files outside its temp directory.
- Example filenames are validated with a strict regex before being read.
- Shell commands are invoked with argument lists, never with `shell=True`, to prevent injection.
- The Flask session secret is ephemeral (generated at startup), so cookies are invalidated on restart.
- **The application must not be exposed to the public internet.** It executes arbitrary compiled binaries on the server machine with no sandboxing beyond the OS process boundary.

---

## Future Improvements

- Capture `stdout`/`stderr` during a debug session by redirecting the inferior's output through a pipe
- Conditional breakpoints and watchpoints via GDB MI2
- Multi-file project support with a simple file tree
- Session persistence across page reloads
- Variable editing (assign new values via GDB `-var-assign`)
- Memory view for pointer inspection
- WSL2 integration for Windows users who prefer the Linux GDB experience

---

## Resume Description

> **Mini Debugger** — Built a full-stack graphical C++ debugger using Python/Flask and vanilla JavaScript. Integrated GDB's Machine Interface (MI2) protocol to manage a persistent debug subprocess, implementing real breakpoints, single-step execution, local variable inspection, and call stack display. Compiled programs with `g++` debug symbols and parsed structured diagnostics for in-editor display. Frontend uses Monaco Editor with custom gutter decorations for breakpoints and the active execution line.

---

## Interview Q&A

**Q: Why GDB MI2 instead of standard GDB output?**
A: GDB's default output is designed for humans — it changes format depending on context and is hard to parse reliably. MI2 produces structured `key="value"` records with a token prefix so you can match each response to the command that triggered it. This makes it practical to drive from a program.

**Q: How do you handle the fact that GDB output is asynchronous?**
A: A background daemon thread reads GDB's stdout line by line into a `queue.Queue`. When a command is sent, the request thread waits on the queue, collecting lines until it sees both the result record (`^done` or `^running`) and, for execution commands, the `*stopped` async event. The timeout prevents a missed event from blocking the server forever.

**Q: How does breakpoint setting work end-to-end?**
A: The frontend sends `POST /api/debug/breakpoint { line: N }`. Flask calls `GDBSession.set_breakpoint(N)`, which sends `-break-insert N` to GDB. GDB responds with `^done,bkpt={number="1",line="N",...}`. The number is stored client-side and used for removal (`-break-delete N`). A Monaco `deltaDecorations` call places a red circle in the gutter at that line.

**Q: How does variable inspection work?**
A: After every step or continue that causes a `*stopped` event, the backend sends `-stack-list-variables --simple-values` to GDB. This returns all local variables in the current stack frame as `{name="x",type="int",value="10"}` records. The backend parses these with a regex and returns them as JSON. The frontend renders them in the Variables table.

**Q: Why does program output not appear during debugging on Windows?**
A: MinGW programs write to the Windows console subsystem directly, which GDB's MI `@`-stream (the inferior output channel) does not intercept. On Linux, GDB routes the inferior's stdout through a PTY which appears as `@`-stream lines. The Run button works around this by capturing stdout/stderr directly via `subprocess.run()`.

**Q: What security risks does this application have?**
A: The server compiles and executes arbitrary C++ code submitted by the user. This is safe for local use since the user is submitting their own code, but it would be a critical vulnerability if exposed publicly — there is no sandboxing beyond the OS process boundary. A production version would need containerization (e.g., Docker with resource limits), rate limiting, and authentication.

**Q: How are sessions managed?**
A: Each browser session gets a UUID stored in a signed Flask session cookie. The server maps this UUID to a dict containing the `GDBSession` object, the binary path, and the temp directory. A background thread checks for sessions idle longer than 10 minutes and calls `gdb.stop()` and `shutil.rmtree()` on them.
