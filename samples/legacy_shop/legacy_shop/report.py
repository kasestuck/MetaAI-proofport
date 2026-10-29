"""Plain-text inventory report."""
import sys

from legacy_shop import textutils, dates


def build_report(inventory, today):
    lines = []
    lines.append(textutils.center_title('INVENTORY REPORT'))
    lines.append('=' * 40)
    for name in inventory.names():
        item = inventory.items[name]
        age = dates.days_between(item.added, today)
        lines.append('%-15s %8.2f x %3d  [%s]' % (
            name, item.price, item.qty, dates.age_label(age)))
    lines.append('-' * 40)
    lines.append('Total value: %.2f' % inventory.total_value())
    lines.append('Mean price (cents): %s' % inventory.average_price_cents())
    lines.append('Low stock: %s' % ', '.join(inventory.low_stock()))
    return lines


def print_report(inventory, today):
    for line in build_report(inventory, today):
        print line
    print
    print "Items:", len(inventory.items)


def warn(msg):
    print >>sys.stderr, "WARNING: %s" % msg
