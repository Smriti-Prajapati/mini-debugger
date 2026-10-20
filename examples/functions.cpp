// functions.cpp — Demonstrates nested function calls.
// Good for: step-into/step-out, watching the call stack grow and shrink.

#include <iostream>

int multiply(int a, int b) {
    int result = a * b;
    return result;
}

int square(int n) {
    int result = multiply(n, n);
    return result;
}

int sumOfSquares(int x, int y) {
    int sx = square(x);
    int sy = square(y);
    int total = sx + sy;
    return total;
}

int main() {
    int a = 3;
    int b = 4;

    int answer = sumOfSquares(a, b);

    std::cout << "Sum of squares of " << a << " and " << b
              << " = " << answer << std::endl;

    return 0;
}
