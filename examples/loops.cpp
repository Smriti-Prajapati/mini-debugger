// loops.cpp — Demonstrates a loop where a variable changes each iteration.
// Good for: watching a variable update step-by-step with the debugger.

#include <iostream>

int main() {
    int sum = 0;

    for (int i = 1; i <= 5; i++) {
        sum += i;
        std::cout << "i = " << i << ", sum = " << sum << std::endl;
    }

    std::cout << "Final sum: " << sum << std::endl;
    return 0;
}
