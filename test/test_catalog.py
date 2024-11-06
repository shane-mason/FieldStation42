from fs42.catalog import ShowCatalog
from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint
import unittest

TEST_CONF = {"network_name": "TEST"}

class TestCatalogHints(unittest.TestCase):

    def test_process_subdir_not(self):
        hints = ShowCatalog._process_hints("should be none")
        self.assertEqual(len(hints), 0)

    def test_process_subdir_month(self):
        hints = ShowCatalog._process_hints("March")
        self.assertEqual(len(hints), 1)
        self.assertIsInstance(hints[0], MonthHint)

    def test_process_subdir_quarter(self):
        hints = ShowCatalog._process_hints("q1")
        self.assertEqual(len(hints), 1)
        self.assertIsInstance(hints[0], QuarterHint)

    def test_process_subdir_range(self):
        hints = ShowCatalog._process_hints("March 1 - March 15")
        self.assertEqual(len(hints), 1)
        self.assertIsInstance(hints[0], RangeHint)

    def test_process_subdir_path(self):
        hints = ShowCatalog._process_hints("somepath/somedir/March 1 - March 15")
        self.assertEqual(len(hints), 1)
        self.assertIsInstance(hints[0], RangeHint)
        hints = ShowCatalog._process_hints("December/somedir/March 1 - March 15")
        self.assertEqual(len(hints), 1)
        self.assertIsInstance(hints[0], RangeHint)


