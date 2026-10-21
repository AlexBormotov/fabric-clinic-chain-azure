import sys


def test_python_matches_fabric_runtime():
    assert sys.version_info[:2] == (3, 13)
