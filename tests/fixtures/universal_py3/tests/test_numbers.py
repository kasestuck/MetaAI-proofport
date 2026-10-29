import unittest
from numbers_demo import add, divide


class NumbersTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_divide(self):
        self.assertEqual(divide(7, 2), 3)
