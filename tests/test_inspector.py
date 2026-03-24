"""Tests for the .clar inspector."""

import io
import json
import zipfile

import pytest

from clar_curator.inspector.clar_inspector import inspect, _is_xml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clar(entries: dict[str, bytes]) -> io.BytesIO:
    """Create an in-memory .clar (ZIP) from a dict of filename -> bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_is_xml_detects_xml():
    assert _is_xml(b"<?xml version='1.0'?><root/>")
    assert _is_xml(b"<root/>")
    assert not _is_xml(b"\x89PNG\r\n")


def test_inspect_lists_entries(tmp_path):
    xml = b"<?xml version='1.0'?><integration><name>Test</name></integration>"
    clar = _make_clar({"META-INF/manifest.xml": xml, "integration/test.xml": xml})

    clar_path = tmp_path / "sample.clar"
    clar_path.write_bytes(clar.read())

    result = inspect(clar_path)

    assert "META-INF/manifest.xml" in result["archive_entries"]
    assert "integration/test.xml" in result["archive_entries"]
    assert "META-INF/manifest.xml" in result["xml_schemas"]


def test_inspect_missing_file():
    with pytest.raises(FileNotFoundError):
        inspect("/nonexistent/file.clar")
