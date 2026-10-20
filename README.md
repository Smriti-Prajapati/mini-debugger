# Mini Debugger

A browser-based C++ debugger built with Python, Flask, and GDB. Write C++ code in the editor, compile it, set breakpoints, and step through execution.

<img width="1919" height="1024" alt="image" src="https://github.com/user-attachments/assets/2b4be4c1-43cb-427d-bc4e-5d9b04ee48dd" />



---

## What it does

- Compiles C++ with `g++ -g -O0` and shows errors with line numbers
- Runs a real GDB session — breakpoints, step over/into/out, continue
- Shows local variables and call stack while paused
- Highlights the current execution line in the editor
- Generates assembly output and a GIMPLE IR dump for compiler exploration
- Multi-file support — create, rename, and delete files in the sidebar

---

## Stack

- **Backend:** Python + Flask
- **Frontend:** HTML, CSS, vanilla JS
- **Editor:** Monaco Editor (CDN)
- **Compiler:** g++
- **Debugger:** GDB with `--interpreter=mi2`

---

## Requirements

**Windows (MinGW-W64):**
```
g++ --version   # 12 or newer
gdb --version   # 12 or newer
python --version # 3.10+
```

Install MinGW from [winlibs.com](https://winlibs.com/) and make sure `g++` and `gdb` are on your PATH.

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/mini-debugger.git
cd mini-debugger
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**.

---

## Quick walkthrough

1. Write some C++ in the editor (or create a new file with the `+` button)
2. Click **Compile** — errors show up in the Compiler tab
3. Click **Debug** — starts a GDB session
4. Click a line number in the gutter to set a breakpoint
5. Click the run button — execution pauses at the breakpoint
6. Use Step Over / Step Into / Step Out to navigate
7. Check the Variables and Call Stack panels on the right
8. Click **Stop** when done

For assembly output, go to the **Compiler Explorer** tab and click Generate.

---
