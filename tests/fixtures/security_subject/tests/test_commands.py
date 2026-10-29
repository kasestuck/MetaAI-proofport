import unittest
from commands import add_one, constant_output


class CommandsTests(unittest.TestCase):
    def test_output(self):
        self.assertEqual(constant_output(), 'fixture')

    def test_add(self):
        self.assertEqual(add_one(4), 5)
