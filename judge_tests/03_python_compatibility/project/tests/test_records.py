import unittest
import records

class RecordChecks(unittest.TestCase):
    def test_name(self): self.assertEqual(records.format_name(' Demo '), 'demo')
    def test_unicode(self): self.assertEqual(records.format_name('Stra\u00dfe'), 'strasse')
    def test_combine(self): self.assertEqual(records.combine(-2, 3), {'sum': 1, 'label': 'demo'})
