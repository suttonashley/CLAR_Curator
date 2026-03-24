"""
Generate a .clar ZIP archive from a structured integration spec.

NOTE: The XML templates used here are PLACEHOLDERS. They must be updated
after inspecting your sample .clar files with:

    python -m clar_curator.inspector.clar_inspector path/to/sample.clar

Once you have the real internal structure, replace the template strings below
with accurate representations of your organisation's .clar schema.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class IntegrationSpec:
    """
    A normalised, schema-agnostic description of a Workday Studio integration.

    This is the intermediate representation produced by the AI layer and
    consumed by the generator. Fields will expand as you reverse-engineer
    your sample .clar files.
    """

    name: str
    description: str = ""
    version: str = "1.0"

    # Source / target systems
    source_system: str = ""
    target_system: str = ""

    # Field mappings: list of {"source": ..., "target": ..., "transform": ...}
    field_mappings: list[dict[str, str]] = field(default_factory=list)

    # XSLT transformation logic (raw XSLT string if provided)
    xslt: str = ""

    # Connection / delivery settings
    delivery_type: str = "SFTP"  # SFTP | FTP | HTTPS | EIB | etc.
    delivery_config: dict[str, Any] = field(default_factory=dict)

    # Raw extras from the AI layer that don't fit above buckets
    extras: dict[str, Any] = field(default_factory=dict)


def generate(spec: IntegrationSpec, output_path: str | Path) -> Path:
    """
    Build a .clar ZIP archive from the given IntegrationSpec.

    Returns the path to the generated file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _write_manifest(zf, spec)
        _write_integration_xml(zf, spec)
        if spec.xslt:
            _write_xslt(zf, spec)

    output_path.write_bytes(buf.getvalue())
    return output_path


# ---------------------------------------------------------------------------
# Internal file writers — update these after inspecting your sample .clar files
# ---------------------------------------------------------------------------

def _write_manifest(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    """Write the archive manifest / metadata file."""
    # TODO: replace with the actual manifest format from your .clar samples
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <name>{_esc(spec.name)}</name>
  <description>{_esc(spec.description)}</description>
  <version>{_esc(spec.version)}</version>
  <created>{datetime.utcnow().isoformat()}Z</created>
</manifest>
"""
    zf.writestr("META-INF/manifest.xml", manifest.encode("utf-8"))


def _write_integration_xml(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    """Write the main integration definition XML."""
    # TODO: replace with the actual integration XML structure from your .clar samples
    mappings_xml = "\n".join(
        f'    <mapping source="{_esc(m.get("source", ""))}" '
        f'target="{_esc(m.get("target", ""))}" '
        f'transform="{_esc(m.get("transform", ""))}" />'
        for m in spec.field_mappings
    )

    integration_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<integration name="{_esc(spec.name)}">
  <metadata>
    <description>{_esc(spec.description)}</description>
    <sourceSystem>{_esc(spec.source_system)}</sourceSystem>
    <targetSystem>{_esc(spec.target_system)}</targetSystem>
  </metadata>
  <fieldMappings>
{mappings_xml}
  </fieldMappings>
  <delivery type="{_esc(spec.delivery_type)}" />
</integration>
"""
    safe_name = spec.name.replace(" ", "_")
    zf.writestr(f"integration/{safe_name}.xml", integration_xml.encode("utf-8"))


def _write_xslt(zf: zipfile.ZipFile, spec: IntegrationSpec) -> None:
    """Write an XSLT transformation file if one was generated."""
    safe_name = spec.name.replace(" ", "_")
    zf.writestr(f"xslt/{safe_name}_transform.xsl", spec.xslt.encode("utf-8"))


def _esc(value: str) -> str:
    """Escape a string for safe inclusion in XML attribute/text values."""
    return (
        value.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;")
    )
