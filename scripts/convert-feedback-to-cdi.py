#!/usr/bin/env python3
"""Combine the DMP feedback survey schema with CSV responses into DDI-CDI JSON-LD.

Loads data/feedback-survey-schema.json (survey structure) and
data/feedback-survey-responses.csv (74 responses), then replaces the
example dataPoint entries with actual coded responses.

Outputs data/feedback-survey-dataset.jsonld.

Usage:
    pipenv run python scripts/convert-feedback-to-cdi.py
    pipenv run python scripts/convert-feedback-to-cdi.py <csv> <schema> <output>
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

# CSV column -> Instance Variable mapping
# Keys are the CSV column names (after stripping trailing whitespace/NBSP).
COLUMN_TO_IV = {
    "ID": "_:iv0",
    "Finding the DMP template in the TU/e Research Cockpit was easy": "_:iv1",
    "The process of completing my DMP was easy": "_:iv2",
    "The instructions and guidance provided by the system were clear": "_:iv3",
    "Did you have contact with a data steward?": "_:iv4",
    "How helpful was the advice of the data steward?": "_:iv5",
    "If you could change anything about the DMP experience, what would it be?": "_:iv6",
}

# Measure variable refs (exclude the ID, only iv1-iv6)
MEASURE_IVS = ["_:iv1", "_:iv2", "_:iv3", "_:iv4", "_:iv5", "_:iv6"]

# Columns used for measureValue (in order)
MEASURE_COLUMNS = [
    "Finding the DMP template in the TU/e Research Cockpit was easy",
    "The process of completing my DMP was easy",
    "The instructions and guidance provided by the system were clear",
    "Did you have contact with a data steward?",
    "How helpful was the advice of the data steward?",
    "If you could change anything about the DMP experience, what would it be?",
]


def strip_col(col: str) -> str:
    """Strip trailing whitespace, NBSP, and BOM artifacts from column names."""
    return col.strip().rstrip("\u00a0").strip()


def load_schema(path: str) -> dict:
    """Load JSON-LD schema, stripping XML comments that are embedded."""
    raw = Path(path).read_text(encoding="utf-8")
    cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    return json.loads(cleaned)


def build_code_maps(schema: dict) -> dict[str, dict[str, str]]:
    """Build lookup maps from each CodeList: { codeListId: { label_text: codeValue } }."""
    code_maps: dict[str, dict[str, str]] = {}
    for node in schema.get("@graph", []):
        if node.get("type") in ("cdi:CodeList", "CodeList"):
            codelist_id = node["id"]
            label_to_code: dict[str, str] = {}
            for code_entry in node.get("cdi:CodeList_has_Code", []):
                category = code_entry["cdi:Code_denotes_Category"]
                label = category["Concept-name"]["en"]
                label_to_code[label] = code_entry["cdi:Code-identifier"]
            code_maps[codelist_id] = label_to_code
    return code_maps


def convert_row_value(col: str, value, code_maps: dict) -> any:
    """Convert a single CSV cell value to the appropriate coded representation.

    - Likert labels -> integer code (1-5)
    - Yes/No -> integer code (1=Yes, 2=No)
    - Steward rating -> int or None
    - Free text -> string or None
    - ID -> integer
    """
    if pd.isna(value):
        return None

    iv = COLUMN_TO_IV.get(col)
    if iv == "_:iv0":
        return int(value)
    if iv in ("_:iv1", "_:iv2", "_:iv3"):
        label = str(value).strip()
        return int(code_maps["_:cl_likert5"].get(label, 0))
    if iv == "_:iv4":
        label = str(value).strip()
        return int(code_maps["_:cl_yesno"].get(label, 0))
    if iv == "_:iv5":
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
    if iv == "_:iv6":
        text = str(value).strip()
        return text if text else None
    return value


def build_datapoints(df: pd.DataFrame, code_maps: dict) -> list[dict]:
    """Convert each CSV row into a DataPoint node."""
    start_times = pd.to_datetime(df["Start time"], format="mixed")
    completion_times = pd.to_datetime(df["Completion time"], format="mixed")

    datapoints: list[dict] = []
    for idx, row in df.iterrows():
        identifier = int(row["ID"])
        values: list[any] = []
        for col in MEASURE_COLUMNS:
            values.append(convert_row_value(col, row[col], code_maps))

        dp: dict = {
            "type": "cdi:DataPoint",
            "tue:identifierValue": str(identifier),
            "tue:responseTimestamps": {
                "tue:startTime": start_times.iloc[idx].isoformat(),
                "tue:completionTime": completion_times.iloc[idx].isoformat(),
            },
            "tue:measureValue": [
                {"tue:variableRef": ref, "tue:value": val}
                for ref, val in zip(MEASURE_IVS, values)
            ],
        }
        datapoints.append(dp)
    return datapoints


def update_schema(schema: dict, df: pd.DataFrame, csv_filename: str) -> dict:
    """Update the schema in-place with real data."""
    code_maps = build_code_maps(schema)
    datapoints = build_datapoints(df, code_maps)

    # Find and update the WideDataSet node
    for node in schema["@graph"]:
        if node.get("id") == "_:wds1":
            node["cdi:DataSet_has_DataPoint"] = datapoints
            break

    # Update the PhysicalDataSet node
    for node in schema["@graph"]:
        if node.get("id") == "_:pds1":
            node["PhysicalDataSet-name"]["en"] = csv_filename
            node["cdi:PhysicalDataSet-physicalFileName"] = csv_filename
            break

    # Update the Study node with collection period
    start_times = pd.to_datetime(df["Start time"], format="mixed")
    end_times = pd.to_datetime(df["Completion time"], format="mixed")
    for node in schema["@graph"]:
        if node.get("id") == "_:_study" or node.get("id") == "_:study":
            node["tue:collectionPeriod"] = {
                "tue:startDate": start_times.min().strftime("%Y-%m-%d"),
                "tue:endDate": end_times.max().strftime("%Y-%m-%d"),
            }
            node["tue:respondentCount"] = len(df)
            break

    return schema


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    csv_path = base / "data" / "feedback-survey-responses.csv"
    schema_path = base / "data" / "feedback-survey-schema.json"
    output_path = base / "data" / "feedback-survey-dataset.jsonld"

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        schema_path = Path(sys.argv[2])
    if len(sys.argv) > 3:
        output_path = Path(sys.argv[3])

    for p in (csv_path, schema_path):
        if not p.exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(1)

    schema = load_schema(str(schema_path))
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [strip_col(c) for c in df.columns]

    schema = update_schema(schema, df, csv_path.name)

    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path} ({len(schema['@graph'])} nodes, {len(df)} responses)")


if __name__ == "__main__":
    main()
