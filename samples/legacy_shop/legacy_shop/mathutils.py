"""Number helpers for prices and statistics."""


def mean(values):
    if not values:
        raise ValueError, "mean of empty list"
    return sum(values) / len(values)


def median(values):
    ordered = sorted(values)
    mid = len(ordered) / 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def percent(part, whole):
    if whole == 0:
        return 0
    return part * 100 / whole


def round_to_dollar(amount):
    """Round a price to whole dollars (halves go up)."""
    return int(round(amount))


def factorial(n):
    result = 1L
    for i in xrange(2, n + 1):
        result *= i
    return result


def price_tiers(prices, size=10):
    """Group prices into buckets of `size` dollars."""
    tiers = {}
    for p in prices:
        key = int(p) / size * size
        tiers.setdefault(key, []).append(p)
    return tiers
