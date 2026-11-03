import unittest
import subject
class CryptoChecks(unittest.TestCase):
    def test_label(self): self.assertTrue(subject.public_label().startswith('DEMO_'))
    def test_format(self): self.assertEqual(len(subject.digest('demo')), 32)
