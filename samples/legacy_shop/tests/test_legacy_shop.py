import os
import unittest

from legacy_shop import textutils, mathutils, dates, config, inventory

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'sample_data')


class TextTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(textutils.slugify('Big Red Widget!'), 'big-red-widget')

    def test_top_words(self):
        self.assertEqual(textutils.top_words('a b a c b a', 2), [('a', 3), ('b', 2)])

    def test_center_title(self):
        self.assertEqual(textutils.center_title('HI', 10), '    HI')


class MathTests(unittest.TestCase):
    def test_mean_is_integer_division(self):
        self.assertEqual(mathutils.mean([1, 2, 4]), 2)

    def test_round_half_up(self):
        self.assertEqual(mathutils.round_to_dollar(2.5), 3)

    def test_factorial(self):
        self.assertEqual(mathutils.factorial(20), 2432902008176640000)


class DateTests(unittest.TestCase):
    def test_days_between(self):
        self.assertEqual(dates.days_between('2026-10-01', '2026-10-27'), 26)

    def test_age_label(self):
        self.assertEqual(dates.age_label(3), 'fresh')


class ConfigTests(unittest.TestCase):
    def test_load(self):
        settings = config.load_config(os.path.join(DATA, 'shop.conf'))
        self.assertEqual(settings['low_stock_threshold'], 5)
        self.assertEqual(settings['open_days'][0], 'mon')


class InventoryTests(unittest.TestCase):
    def test_duplicate(self):
        inv = inventory.Inventory()
        inv.add(inventory.Item('a', 1.0, 1, '2026-01-01'))
        self.assertRaises(KeyError, inv.add, inventory.Item('a', 2.0, 1, '2026-01-01'))


if __name__ == '__main__':
    unittest.main()
