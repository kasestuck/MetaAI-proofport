"""Inventory model."""
from legacy_shop import mathutils


class Item(object):
    def __init__(self, name, price, qty, added):
        self.name = name
        self.price = price
        self.qty = qty
        self.added = added

    def __cmp__(self, other):
        return cmp(self.name, other.name)

    def __repr__(self):
        return 'Item(%r, %r, %r, %r)' % (self.name, self.price, self.qty, self.added)


class Inventory(object):
    def __init__(self):
        self.items = {}

    def __nonzero__(self):
        return len(self.items) > 0

    def add(self, item):
        if self.items.has_key(item.name):
            raise KeyError, "duplicate item: %s" % item.name
        self.items[item.name] = item

    def names(self):
        names = self.items.keys()
        names.sort()
        return names

    def total_value(self):
        total = 0.0
        for name, item in self.items.iteritems():
            total += item.price * item.qty
        return total

    def low_stock(self, threshold=5):
        return [n for n in self.names() if self.items[n].qty < threshold]

    def average_price_cents(self):
        prices = [int(i.price * 100) for i in self.items.values()]
        return mathutils.mean(prices)

    def cheapest(self):
        ordered = self.items.values()
        ordered.sort()
        by_price = sorted(ordered, cmp=lambda a, b: cmp(a.price, b.price))
        return by_price[0]
