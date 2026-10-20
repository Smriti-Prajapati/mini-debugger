// arrays.cpp — Demonstrates array traversal and finding a maximum value.
// Good for: stepping through a loop, watching index and max update.

#include <iostream>

int findMax(int arr[], int size) {
    int max = arr[0];
    for (int i = 1; i < size; i++) {
        if (arr[i] > max) {
            max = arr[i];
        }
    }
    return max;
}

int main() {
    int numbers[] = {3, 7, 1, 9, 4, 6, 2};
    int size = 7;

    std::cout << "Array: ";
    for (int i = 0; i < size; i++) {
        std::cout << numbers[i];
        if (i < size - 1) std::cout << ", ";
    }
    std::cout << std::endl;

    int result = findMax(numbers, size);
    std::cout << "Maximum value: " << result << std::endl;

    return 0;
}
