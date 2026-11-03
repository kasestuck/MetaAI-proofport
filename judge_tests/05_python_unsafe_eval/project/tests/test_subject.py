import unittest
import subject
class EvalChecks(unittest.TestCase):
    def test_list(self): self.assertEqual(subject.parse_value('[1, 2]'), [1, 2])
    def test_expression(self): self.assertEqual(subject.parse_value('1 + 2'), 3)
