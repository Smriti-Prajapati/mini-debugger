import compiler_explorer as ce

SRC = """\
#include <iostream>
int add(int a, int b) {
    int result = a + b;
    return result;
}
int main() {
    int x = add(3, 4);
    std::cout << x << std::endl;
    return 0;
}
"""

print("=== Compiler Info ===")
info = ce.get_compiler_info()
print("version:", info["version"])
print("target:", info["target"])
print("pipeline stages:", [s["stage"] for s in info["pipeline"]])

print("\n=== Assembly (O0) ===")
asm = ce.generate_assembly(SRC, "O0")
print("success:", asm["success"])
print("error:", asm["error"])
if asm["success"]:
    lines = asm["assembly"].splitlines()
    print(f"total lines: {len(lines)}")
    print("first 10 lines:")
    for l in lines[:10]: print(" ", l)
    print("groups:", [g["label"] for g in asm["annotated"]])

print("\n=== GIMPLE ===")
gimple = ce.generate_gimple(SRC)
print("success:", gimple["success"])
print("error:", gimple["error"])
if gimple["success"]:
    print(gimple["gimple"][:600])
