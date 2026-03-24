"""
CLI entry point.

Usage:
    # Inspect a sample .clar file (do this first!)
    clar-curator inspect path/to/sample.clar

    # Extract a .clar file to a directory for manual review
    clar-curator inspect path/to/sample.clar --extract ./extracted

    # Generate a .clar from a design document
    clar-curator generate path/to/design.docx --output my_integration.clar
    clar-curator generate path/to/design.pdf --output my_integration.clar
    clar-curator generate path/to/mapping.xlsx --output my_integration.clar
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.syntax import Syntax

console = Console()


@click.group()
def main() -> None:
    """CLAR Curator — auto-generate Workday Studio .clar files from design documents."""


# ---------------------------------------------------------------------------
# inspect command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("clar_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--extract",
    "extract_dir",
    default=None,
    help="Extract archive contents to this directory instead of printing the schema.",
)
def inspect(clar_file: Path, extract_dir: str | None) -> None:
    """Inspect a .clar file and print its internal XML structure."""
    from clar_curator.inspector.clar_inspector import extract_all, inspect as _inspect

    if extract_dir:
        paths = extract_all(clar_file, extract_dir)
        console.print(f"[green]Extracted {len(paths)} files to:[/green] {extract_dir}")
        for p in paths:
            console.print(f"  {p}")
        return

    summary = _inspect(clar_file)
    output = json.dumps(summary, indent=2)
    console.print(Syntax(output, "json", theme="monokai", line_numbers=True))


# ---------------------------------------------------------------------------
# generate command
# ---------------------------------------------------------------------------

@main.command()
@click.argument("design_doc", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output", "-o",
    default="output.clar",
    show_default=True,
    help="Path for the generated .clar file.",
)
@click.option(
    "--model",
    default="claude-opus-4-6",
    show_default=True,
    help="Claude model to use for AI extraction.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the extracted IntegrationSpec without generating the .clar file.",
)
def generate(design_doc: Path, output: str, model: str, dry_run: bool) -> None:
    """Generate a .clar file from a design document (Word, PDF, or spreadsheet)."""
    from clar_curator.ai_layer import extract_spec
    from clar_curator.generator.clar_generator import generate as _generate
    from clar_curator.parsers import document_parser, spreadsheet_parser

    suffix = design_doc.suffix.lower()

    # --- Parse ---
    console.print(f"[bold]Parsing:[/bold] {design_doc.name}")
    try:
        if suffix in (".docx", ".pdf"):
            text = document_parser.parse(design_doc)
        elif suffix in (".xlsx", ".xls", ".xlsm", ".csv"):
            text = spreadsheet_parser.parse(design_doc)
        else:
            console.print(f"[red]Unsupported file type:[/red] {suffix}")
            sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Parse error:[/red] {exc}")
        sys.exit(1)

    console.print(f"  Extracted {len(text):,} characters from design document.")

    # --- AI extraction ---
    console.print(f"\n[bold]Extracting spec with Claude ({model})...[/bold]")
    try:
        spec = extract_spec(text, model=model)
    except Exception as exc:
        console.print(f"[red]AI extraction error:[/red] {exc}")
        sys.exit(1)

    console.print(f"  Integration: [cyan]{spec.name}[/cyan]")
    console.print(f"  Source:      {spec.source_system}")
    console.print(f"  Target:      {spec.target_system}")
    console.print(f"  Mappings:    {len(spec.field_mappings)} fields")
    console.print(f"  Delivery:    {spec.delivery_type}")

    if dry_run:
        console.print("\n[bold yellow]Dry run — spec only:[/bold yellow]")
        import dataclasses
        console.print(Syntax(json.dumps(dataclasses.asdict(spec), indent=2), "json", theme="monokai"))
        return

    # --- Generate .clar ---
    console.print(f"\n[bold]Generating:[/bold] {output}")
    try:
        out_path = _generate(spec, output)
    except Exception as exc:
        console.print(f"[red]Generation error:[/red] {exc}")
        sys.exit(1)

    console.print(f"[green]Done![/green] Written to: {out_path}")
    console.print(
        "\n[yellow]Note:[/yellow] The XML templates in the generator are placeholders. "
        "Run [bold]clar-curator inspect[/bold] on your sample .clar files and update "
        "[bold]src/clar_curator/generator/clar_generator.py[/bold] to match the real schema."
    )


if __name__ == "__main__":
    main()
