import compiler

# Exact source from the screenshot - missing semicolon on line 10
source = """\
#include <iostream>
using namespace std;

int calculateSum(int a, int b) {
    int sum = a + b;
    return sum;
}

int main() {
    int numbers[] = {10, 20, 30}
    int total = 0;

    for (int i = 0; i < 3; i++) {
        total += numbers[i];
    }

    int result = calculateSum(total, 5);

    cout << "Total: " << total << endl;
    cout << "Result: " << result << endl;

    return 0;
}"""

print("Line 10 is:", repr(source.splitlines()[9]))
print()
r = compiler.compile_source(source)
print("raw g++ output:")
print(r['raw_output'])
print()
print("parsed errors:")
for e in r['errors']:
    print(e)
compiler.cleanup_work_dir(r['work_dir'])
