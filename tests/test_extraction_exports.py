"""main.py does `from extraction import *`: every exported name must exist, or the CLI dies at import."""

import extraction


def test_every_exported_name_is_defined_by_the_package() -> None:
    assert [name for name in extraction.__all__ if not hasattr(extraction, name)] == []
