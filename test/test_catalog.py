from fs42.catalog import ShowCatalog
from fs42.schedule_hint import MonthHint, QuarterHint, RangeHint

TEST_CONF = {"network_name": "TEST"}

def test_process_subdir_not():
    hints = ShowCatalog._process_hints("should be none")
    assert len(hints) == 0

def test_process_subdir_month():
    hints = ShowCatalog._process_hints("March")
    assert len(hints) == 1
    assert isinstance(hints[0], MonthHint)

def test_process_subdir_quarter():
    hints = ShowCatalog._process_hints("q1")
    assert len(hints) == 1
    assert isinstance(hints[0], QuarterHint)

def test_process_subdir_range():
    hints = ShowCatalog._process_hints("March 1 - March 15")
    assert len(hints) == 1
    assert isinstance(hints[0], RangeHint)

def test_process_subdir_path():
    hints = ShowCatalog._process_hints("somepath/somedir/March 1 - March 15")
    assert len(hints) == 1
    assert isinstance(hints[0], RangeHint)

    hints = ShowCatalog._process_hints("March/somedir/March 1 - March 15")
    assert len(hints) == 1
    assert isinstance(hints[0], RangeHint)
