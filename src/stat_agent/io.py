"""Bounded local table ingestion. No model or generated code is executed."""
import csv
import hashlib
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from .schemas import SourceProfile

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLS = 200


def read_table(path: Path, sheet: str | int = 0) -> tuple[pd.DataFrame, SourceProfile]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        raise ValueError("Only CSV and XLSX are supported in v0.1.")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Input exceeds the 20 MiB baseline limit.")
    snapshot = path.read_bytes()
    if len(snapshot) > MAX_BYTES:
        raise ValueError("Input exceeds the 20 MiB baseline limit.")
    if suffix == ".csv":
        with StringIO(snapshot.decode("utf-8-sig"), newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader, [])
            if len(headers) > MAX_COLS:
                raise ValueError("CSV exceeds 200 columns.")
            count = 0
            for row in reader:
                if not row:
                    continue
                count += 1
                if len(row) != len(headers):
                    raise ValueError(f"CSV row {reader.line_num} does not match the header width.")
                if count > MAX_ROWS:
                    raise ValueError("CSV exceeds 100000 rows.")
        frame = pd.read_csv(BytesIO(snapshot), encoding="utf-8-sig", nrows=MAX_ROWS + 1)
    else:
        with ZipFile(BytesIO(snapshot)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Uncompressed XLSX exceeds 100 MiB.")
        raw = pd.read_excel(BytesIO(snapshot), sheet_name=sheet, header=None, nrows=MAX_ROWS + 2, engine="openpyxl")
        headers = raw.iloc[0].tolist() if not raw.empty else []
        frame = raw.iloc[1:].copy()
        frame.columns = headers
        frame = frame.reset_index(drop=True).infer_objects()
    if not headers or any(pd.isna(h) or not str(h).strip() for h in headers):
        raise ValueError("Every column must have a non-empty header.")
    headers = [str(h) for h in headers]
    if len(set(headers)) != len(headers):
        raise ValueError("Duplicate column names are not supported.")
    frame.columns = headers
    if frame.empty or len(frame) > MAX_ROWS or len(headers) > MAX_COLS:
        raise ValueError("Expected 1–100000 rows and 1–200 columns.")
    return frame, SourceProfile(
        file_name=path.name, sha256=hashlib.sha256(snapshot).hexdigest(),
        format=suffix[1:], extraction_method="pandas local table reader",
        sheet=sheet if suffix == ".xlsx" else None,
        uncertainties=["Inferred dtypes do not establish measurement scales or study design."],
    )
