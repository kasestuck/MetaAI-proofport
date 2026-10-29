"""Command line entry point: python -m legacy_shop.cli inventory.csv 2026-10-27"""
import sys

from legacy_shop import storage, inventory, report


def load_inventory(csv_path):
    inv = inventory.Inventory()
    for row in storage.load_csv(csv_path):
        try:
            item = inventory.Item(row['name'], float(row['price']),
                                  int(row['qty']), row['added'])
            inv.add(item)
        except KeyError, e:
            report.warn("skipping row: %s" % e)
        except ValueError, e:
            report.warn("bad number in row %r: %s" % (row, e))
    return inv


def main(argv):
    if len(argv) < 3:
        print >>sys.stderr, "usage: cli.py inventory.csv YYYY-MM-DD"
        return 2
    inv = load_inventory(argv[1])
    report.print_report(inv, argv[2])
    answer = raw_input("Save snapshot? [y/N] ")
    if answer.lower() == 'y':
        storage.save_snapshot(inv.items, 'snapshot.pkl')
        print "Saved."
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
