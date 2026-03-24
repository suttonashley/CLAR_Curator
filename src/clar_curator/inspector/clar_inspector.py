"""
Inspect and reverse-engineer the internal structure of a .clar file.

A .clar file is a ZIP archive. This module:
  1. Lists all entries in the archive
  2. Extracts and pretty-prints XML files
  3. Produces a schema summary that guides the generator

Run directly:
    python -m clar_curator.inspector.clar_inspector path/to/file.clar
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET


def inspect(clar_path: str | Path) -> dict:
    """
    Open a .clar file and return a structured summary of its contents.

    Returns a dict with:
        {
          "archive_entries": [...],           # all file paths inside the ZIP
          "xml_schemas": {                    # per-XML file tag/attribute summary
              "some/path/file.xml": {
                  "root_tag": "...",
                  "namespaces": {...},
                  "element_tree": {...},      # nested dict of tag -> [child tags]
              }
          },
          "binary_entries": [...],            # non-XML/non-text files
        }
    """
    clar_path = Path(clar_path)
    if not clar_path.exists():
        raise FileNotFoundError(f"File not found: {clar_path}")

    result: dict = {
        "archive_entries": [],
        "xml_schemas": {},
        "binary_entries": [],
    }

    with zipfile.ZipFile(clar_path, "r") as zf:
        for entry in zf.infolist():
            result["archive_entries"].append(entry.filename)

            if entry.filename.endswith("/"):
                continue  # directory entry

            data = zf.read(entry.filename)

            if _is_xml(data):
                try:
                    schema = _parse_xml_schema(data)
                    result["xml_schemas"][entry.filename] = schema
                except ET.ParseError as exc:
                    result["xml_schemas"][entry.filename] = {"parse_error": str(exc)}
            elif not _is_text(data):
                result["binary_entries"].append(entry.filename)

    return result


def pretty_print_xml(clar_path: str | Path, entry_name: str) -> str:
    """Extract and pretty-print a specific XML file from a .clar archive."""
    with zipfile.ZipFile(clar_path, "r") as zf:
        data = zf.read(entry_name)
    return minidom.parseString(data).toprettyxml(indent="  ")


def extract_all(clar_path: str | Path, output_dir: str | Path) -> list[Path]:
    """Extract all contents of a .clar file to output_dir for manual inspection."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    with zipfile.ZipFile(clar_path, "r") as zf:
        zf.extractall(output_dir)
        extracted = [output_dir / name for name in zf.namelist()]

    return extracted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_xml(data: bytes) -> bool:
    stripped = data.lstrip()
    return stripped.startswith(b"<?xml") or stripped.startswith(b"<")


def _is_text(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _parse_xml_schema(data: bytes) -> dict:
    """Build a lightweight schema summary from raw XML bytes."""
    # Collect namespace declarations
    ns_map: dict[str, str] = {}
    for event, (prefix, uri) in ET.iterparse(__import__("io").BytesIO(data), events=["start-ns"]):
        ns_map[prefix or "default"] = uri

    root = ET.fromstring(data)

    return {
        "root_tag": _strip_ns(root.tag),
        "root_attribs": list(root.attrib.keys()),
        "namespaces": ns_map,
        "element_tree": _build_tree(root),
    }


def _build_tree(element: ET.Element, depth: int = 0, max_depth: int = 8) -> dict:
    """Recursively build a nested dict representing the XML element hierarchy."""
    if depth >= max_depth:
        return {"...": "(max depth)"}

    children: dict[str, list] = {}
    seen: set[str] = set()

    for child in element:
        tag = _strip_ns(child.tag)
        if tag not in seen:
            seen.add(tag)
            children[tag] = [_build_tree(child, depth + 1, max_depth)]
        # Collect unique attribute keys across siblings
        children.setdefault(tag, [])

    return {
        "_attrs": list(element.attrib.keys()),
        "_children": children,
    }


def _strip_ns(tag: str) -> str:
    """Remove the {namespace} prefix from an XML tag."""
    return tag.split("}")[-1] if "}" in tag else tag


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m clar_curator.inspector.clar_inspector <file.clar> [--extract <dir>]")
        sys.exit(1)

    path = sys.argv[1]

    if "--extract" in sys.argv:
        idx = sys.argv.index("--extract")
        out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "extracted_clar"
        paths = extract_all(path, out)
        print(f"Extracted {len(paths)} files to: {out}")
    else:
        summary = inspect(path)
        print(json.dumps(summary, indent=2))
