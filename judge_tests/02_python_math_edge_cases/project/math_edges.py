def divide(left, right):
    return left / right


def dollars(value):
    return int(round(value))


def factorial(n):
    if n < 0:
        raise ValueError('nonnegative required')
    result = 1L
    for value in xrange(2, n + 1):
        result *= value
    return result
