import math


def divide(left, right):
    if isinstance(left, int) and isinstance(right, int):
        return left // right
    return left / right


def dollars(value):
    return int(math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5))


def factorial(n):
    if n < 0:
        raise ValueError('nonnegative required')
    result = 1
    for value in range(2, n + 1):
        result *= value
    return result
