// factorial.cpp — Iterative factorial with a local variable accumulator.
// Good for: watching n and result change each iteration.

#include <iostream>

long long factorial(int n) {
    long long result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

int main() {
    for (int n = 0; n <= 10; n++) {
        std::cout << n << "! = " << factorial(n) << std::endl;
    }
    return 0;
}
