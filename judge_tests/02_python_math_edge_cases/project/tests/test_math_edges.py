import unittest
import math_edges

class MathChecks(unittest.TestCase):
    def test_division(self):
        self.assertEqual(math_edges.divide(1, 2), 0)
        self.assertEqual(math_edges.divide(-3, 2), -2)
        self.assertEqual(math_edges.divide(1.0, 2), 0.5)
    def test_rounding(self):
        self.assertEqual(math_edges.dollars(2.5), 3)
        self.assertEqual(math_edges.dollars(-2.5), -3)
    def test_factorial(self):
        self.assertEqual(math_edges.factorial(0), 1)
        self.assertEqual(math_edges.factorial(5), 120)
