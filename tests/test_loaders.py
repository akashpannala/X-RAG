"""Loaders: extension gate + image detection."""
from pathlib import Path

import pytest

from backend.l01_connectors.loaders import check_supported, is_image


def test_supported_extensions(tmp_path):
    for name in ("a.pdf", "b.txt", "c.md", "d.csv", "e.png"):
        check_supported(tmp_path / name)


def test_unsupported_extension_raises(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        check_supported(tmp_path / "evil.exe")


def test_is_image():
    assert is_image(Path("x.png"))
    assert is_image(Path("x.JPG"))
    assert not is_image(Path("x.pdf"))
