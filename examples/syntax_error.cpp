// syntax_error.cpp — A program with an intentional syntax error.
// Good for: testing compiler diagnostics display.

#include <iostream>

int main() {
    int x = 10;
    int y =  ; // ERROR: missing value

    std::cout << "x + y = " << x + y << std::endl;
    return 0;
}
