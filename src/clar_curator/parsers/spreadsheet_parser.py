"""
Parse spreadsheet design documents (.xlsx, .csv) into structured data for the AI layer.
"""

from __future__ import annotations

import json
from pathlib import Path


def parse(file_path: str | Path) -> str:
    """
    Extract structured data from a spreadsheet design document.

    Returns a JSON string representation of all sheets/data, preserving
    column headers and row values so the AI layer has full context.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls", ".xlsm"):
        return _parse_excel(path)
    elif suffix == ".csv":
        return _parse_csv(path)
    else:
        raise ValueError(f"Unsupported spreadsheet format: {suffix}. Expected .xlsx or .csv")


def _parse_excel(path: Path) -> str:
    import pandas as pd

    sheets: dict[str, list[dict]] = {}
    xf = pd.ExcelFile(path)

    for sheet_name in xf.sheet_names:
        df = pd.read_excel(xf, sheet_name=sheet_name, dtype=str).fillna("")
        sheets[sheet_name] = df.to_dict(orient="records")

    return json.dumps(sheets, indent=2, ensure_ascii=False)


def _parse_csv(path: Path) -> str:
    import pandas as pd

    df = pd.read_csv(path, dtype=str).fillna("")
    data = {"Sheet1": df.to_dict(orient="records")}
    return json.dumps(data, indent=2, ensure_ascii=False)
