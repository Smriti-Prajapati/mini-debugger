import urllib.request, json

BASE = "http://127.0.0.1:5000"

def post(url, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

SRC = """
#include <iostream>
int add(int a, int b) { return a + b; }
int main() {
    int x = add(3, 4);
    std::cout << x << std::endl;
    return 0;
}
"""

print("=== /api/explore/info ===")
info = get(f"{BASE}/api/explore/info")
print("version :", info["version"])
print("target  :", info["target"])
print("pipeline:", [s["stage"] for s in info["pipeline"]])
print("flags   :", list(info["flags_used"].keys()))
print("PASS" if info["version"] else "FAIL")

print("\n=== /api/explore/assembly (O0) ===")
asm = post(f"{BASE}/api/explore/assembly", {"source": SRC, "opt_level": "O0"})
print("success :", asm["success"])
print("groups  :", [g["label"] for g in asm["annotated"]])
print("lines   :", len(asm["assembly"].splitlines()))
print("PASS" if asm["success"] and len(asm["assembly"]) > 50 else "FAIL")

print("\n=== /api/explore/assembly (O2) ===")
asm2 = post(f"{BASE}/api/explore/assembly", {"source": SRC, "opt_level": "O2"})
print("success :", asm2["success"])
print("O2 lines:", len(asm2["assembly"].splitlines()), "(usually fewer than O0)")
print("PASS" if asm2["success"] else "FAIL")

print("\n=== /api/explore/gimple ===")
gimple = post(f"{BASE}/api/explore/gimple", {"source": SRC})
print("success :", gimple["success"])
print("note    :", gimple.get("note","")[:60])
print(gimple["gimple"][:300])
print("PASS" if gimple["success"] and "add" in gimple["gimple"] else "FAIL")

print("\n=== Invalid source (should not crash) ===")
bad = post(f"{BASE}/api/explore/assembly", {"source": "int main(){ BROKEN }}"})
print("success :", bad["success"], "(expected False)")
print("error   :", bad.get("error","")[:80])
print("PASS" if not bad["success"] else "FAIL")
