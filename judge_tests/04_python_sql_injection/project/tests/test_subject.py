import unittest
import subject
class QueryChecks(unittest.TestCase):
    def test_query(self): self.assertEqual(subject.build_query('demo'), "SELECT name FROM items WHERE id = 'demo'")
    def test_empty(self): self.assertTrue(isinstance(subject.build_query(''), str))
