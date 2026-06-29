"""Shared data loading and metrics for the RDM dashboard.

Loads the DMP and ERB exports from ``data/`` and exposes tidy dataframes
and metric functions for the overview and per-department dashboards.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DMP_FILE = DATA_DIR / "DMPs_2025_09_10_onwards.csv"
ERB_FILE = DATA_DIR / "ERBs_2025_09_10_onwards.csv"

# Classification rules -------------------------------------------------------

# Storage solutions considered TU/e-supported (vs. external).
TUE_STORAGE = {
    "01 TU/e Network Drive",
    "02 Microsoft SharePoint/Teams",
    "04 SURF Research Drive",
}

# Repositories considered trusted (FAIR) destinations.
TRUSTED_REPOSITORIES = {
    "4TU.ResearchData",
    "Zenodo",
    "OSF",
    "Figshare",
}

# Main single departments (each gets its own dashboard).
DEPARTMENTS = [
    "Industrial Design (ID)",
    "Industrial Engineering and Innovation Sciences (IE&IS)",
    "Built Environment (BE)",
    "Mathematics and Computer Science (M&CS)",
    "Biomedical Engineering (BmE)",
    "Mechanical Engineering (ME)",
    "Applied Physics and Science Education (AP&SE)",
    "Electrical Engineering (EE)",
    "Chemical Engineering and Chemistry (CE&C)",
]

# URL-friendly slug per department (used for file names).
DEPT_SLUGS = {
    "Industrial Design (ID)": "industrial-design",
    "Industrial Engineering and Innovation Sciences (IE&IS)": "industrial-engineering",
    "Built Environment (BE)": "built-environment",
    "Mathematics and Computer Science (M&CS)": "mathematics-computer-science",
    "Biomedical Engineering (BmE)": "biomedical-engineering",
    "Mechanical Engineering (ME)": "mechanical-engineering",
    "Applied Physics and Science Education (AP&SE)": "applied-physics",
    "Electrical Engineering (EE)": "electrical-engineering",
    "Chemical Engineering and Chemistry (CE&C)": "chemical-engineering",
}


# Parsing helpers -----------------------------------------------------------

_BOOL_COLS_DMP = {
    "is_approved",
    "is_scientific",
    "has_related_erb",
    "has_special_category",
    "ever_approved",
    "has_data_volume_info",
    "has_data_storage_info",
}
_BOOL_COLS_ERB = {
    "is_approved",
    "is_scientific",
    "has_related_dmp",
    "ever_approved",
    "has_special_category",
}
_LIST_COLS_DMP = [
    "ordered_status_transition_list",
    "data_storage_list",
    "data_storage_after_list",
    "data_repository",
    "processing_tools_list",
    "metadata_standard",
    "data_volume_list",
]


def _parse_json_list(val) -> list:
    """Parse a JSON array string into a list. Empty/null -> []."""
    if pd.isna(val) or val in ("", "null", "[]"):
        return []
    try:
        v = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []
    return v if isinstance(v, list) else []


def _to_bool(val):
    if pd.isna(val) or val in ("", "null"):
        return pd.NA
    return val == "true"


# Loaders --------------------------------------------------------------------

@cache
def load_dmps() -> pd.DataFrame:
    """Load and clean the DMP export."""
    df = pd.read_csv(DMP_FILE, dtype=str)
    for c in _BOOL_COLS_DMP:
        if c in df.columns:
            df[c] = df[c].map(_to_bool)
    for c in _LIST_COLS_DMP:
        if c in df.columns:
            df[c] = df[c].map(_parse_json_list)
    for c in ("issue_creation_time", "latest_status_time", "erb_link_creation_date", "gold_processed_at"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df


@cache
def load_erbs() -> pd.DataFrame:
    """Load and clean the ERB export."""
    df = pd.read_csv(ERB_FILE, dtype=str)
    for c in _BOOL_COLS_ERB:
        if c in df.columns:
            df[c] = df[c].map(_to_bool)
    if "ordered_status_transition_list" in df.columns:
        df["ordered_status_transition_list"] = df["ordered_status_transition_list"].map(_parse_json_list)
    for c in ("issue_creation_time", "latest_status_time", "dmp_link_creation_date", "gold_processed_at"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df


# Department filtering -------------------------------------------------------

def in_department(dept_value: str | float, department: str) -> bool:
    """True if ``department`` is one of the (possibly multi) departments listed.

    Department strings may be comma-separated, e.g.
    "Industrial Design (ID), Mechanical Engineering (ME)".
    """
    if pd.isna(dept_value) or not dept_value:
        return False
    parts = [p.strip() for p in dept_value.split(",")]
    return department in parts


def filter_department(df: pd.DataFrame, department: str | None) -> pd.DataFrame:
    """Filter DMPs to a single department (including multi-department DMPs)."""
    if department is None:
        return df
    return df[df["tue_department"].map(lambda v: in_department(v, department))].copy()


def department_erbs(df_dmps_dept: pd.DataFrame, df_erbs: pd.DataFrame) -> pd.DataFrame:
    """ERBs linked to a department's DMPs (via ``related_dmp``)."""
    keys = set(df_dmps_dept["issue_key"])
    return df_erbs[df_erbs["related_dmp"].isin(keys)].copy()


def approval_by_purpose(df: pd.DataFrame) -> pd.DataFrame:
    """Approval counts and rates by purpose (scientific vs. educational)."""
    out = []
    for label, val in [("Scientific", True), ("Educational", False)]:
        sub = df[df["is_scientific"] == val]
        n = len(sub)
        approved = int(sub["is_approved"].fillna(False).sum()) if n else 0
        out.append({
            "Purpose": label,
            "DMPs": n,
            "Approved": approved,
            "Approval rate": approved / n if n else 0,
        })
    return pd.DataFrame(out)


# Metrics -------------------------------------------------------------------

def kpi_table(df: pd.DataFrame) -> dict:
    """Headline KPIs for a DMP dataframe."""
    n = len(df)
    approved = int(df["is_approved"].fillna(False).sum()) if n else 0
    erb_linked = int(df["has_related_erb"].fillna(False).sum()) if n else 0
    n_repo = int(df["data_repository"].map(lambda v: len(v) > 0).sum()) if n else 0
    n_trusted = int(
        df["data_repository"].map(
            lambda v: any(r in TRUSTED_REPOSITORIES for r in v)
        ).sum()
    ) if n else 0
    n_raps = int((df["archive_location"] == "tue_archive").sum()) if n else 0
    return {
        "Total DMPs": n,
        "Approved DMPs": approved,
        "Approval rate": approved / n if n else 0,
        "Linked ERB": erb_linked,
        "ERB linkage rate": erb_linked / n if n else 0,
        "Repository selected": n_repo,
        "Repository selection rate": n_repo / n if n else 0,
        "Trusted repository rate": n_trusted / n if n else 0,
        "Archived at RAPS": n_raps,
        "RAPS archival rate": n_raps / n if n else 0,
    }


def approval_by_department(df: pd.DataFrame) -> pd.DataFrame:
    """Approval counts and rates per department (Q1)."""
    out = []
    for dept in DEPARTMENTS:
        sub = filter_department(df, dept)
        n = len(sub)
        approved = int(sub["is_approved"].fillna(False).sum()) if n else 0
        out.append({
            "Department": dept,
            "DMPs": n,
            "Approved": approved,
            "Approval rate": approved / n if n else 0,
        })
    return pd.DataFrame(out)


def erb_breakdown(df_dmps: pd.DataFrame, df_erbs: pd.DataFrame) -> pd.DataFrame:
    """ERB decision breakdown among ERB-linked DMPs (Q2).

    Classifies each ERB by the highest outcome reached in its status
    history (Approved > Rejected > Retracted > Conditional > Revisions
    > In progress).
    """
    erbs = df_erbs.copy()

    def classify(seq):
        statuses = set(seq or [])
        if "Approved" in statuses:
            return "Approved"
        if "Rejected" in statuses:
            return "Rejected"
        if "Retracted" in statuses:
            return "Retracted"
        if "Conditional approval" in statuses:
            return "Conditional"
        if {"Major revisions", "Minor revisions"} & statuses:
            return "Revisions requested"
        return "In progress"

    erbs["decision"] = erbs["ordered_status_transition_list"].map(classify)
    order = ["Approved", "Conditional", "Revisions requested", "Rejected", "Retracted", "In progress"]
    counts = erbs["decision"].value_counts().reindex(order, fill_value=0).reset_index()
    counts.columns = ["Decision", "ERBs"]
    return counts


def repository_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Repository choice counts (Q5). Explodes the repository list."""
    rows = []
    for _, r in df.iterrows():
        repos = r["data_repository"]
        if not repos:
            rows.append({"Repository": "(none)", "DMPs": 1})
            continue
        for rep in repos:
            rows.append({"Repository": rep, "DMPs": 1})
    if not rows:
        return pd.DataFrame(columns=["Repository", "DMPs"])
    out = pd.DataFrame(rows).groupby("Repository", as_index=False).sum()
    return out.sort_values("DMPs", ascending=False)


def trusted_repository_split(df: pd.DataFrame) -> pd.DataFrame:
    """Split DMPs by trusted-repository usage (Q5)."""
    n = len(df)
    if not n:
        return pd.DataFrame(columns=["Category", "DMPs"])
    trusted = int(df["data_repository"].map(
        lambda v: any(r in TRUSTED_REPOSITORIES for r in v)
    ).sum())
    other = int(df["data_repository"].map(
        lambda v: len(v) > 0 and not any(r in TRUSTED_REPOSITORIES for r in v)
    ).sum())
    none = n - trusted - other
    return pd.DataFrame({
        "Category": ["Trusted repository", "Other / advice", "None selected"],
        "DMPs": [trusted, other, none],
    })


def archive_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Archive location breakdown (Q6)."""
    n = len(df)
    if not n:
        return pd.DataFrame(columns=["Location", "DMPs"])
    loc = df["archive_location"].fillna("(none)").replace({"null": "(none)"})
    counts = loc.value_counts().reset_index()
    counts.columns = ["Location", "DMPs"]
    label_map = {
        "tue_archive": "TU/e archive (RAPS)",
        "other": "Other",
        "other_archive": "Other archive",
        "(none)": "Not archived",
    }
    counts["Location"] = counts["Location"].map(lambda v: label_map.get(v, v))
    return counts


def storage_split(df: pd.DataFrame) -> pd.DataFrame:
    """Split DMPs by TU/e-supported vs. external storage (Q3)."""
    n = len(df)
    if not n:
        return pd.DataFrame(columns=["Category", "DMPs"])

    def uses_tue(v):
        return any(s in TUE_STORAGE for s in v)

    def uses_external(v):
        return any(s not in TUE_STORAGE for s in v)

    tue = int(df["data_storage_list"].map(uses_tue).sum())
    ext = int(df["data_storage_list"].map(uses_external).sum())
    both = int(df["data_storage_list"].map(lambda v: uses_tue(v) and uses_external(v)).sum())
    tue_only = tue - both
    ext_only = ext - both
    neither = n - tue_only - ext_only - both
    return pd.DataFrame({
        "Category": ["TU/e only", "External only", "Both", "None listed"],
        "DMPs": [tue_only, ext_only, both, neither],
    })


def revision_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Distribution of "Revision requested" occurrences per DMP (Q7)."""
    if not len(df):
        return pd.DataFrame(columns=["Revisions", "DMPs"])

    def n_revisions(seq):
        return sum(1 for s in seq if s == "Revision requested")

    counts = df["ordered_status_transition_list"].map(n_revisions)
    out = counts.value_counts().sort_index().reset_index()
    out.columns = ["Revisions", "DMPs"]
    out["Revisions"] = out["Revisions"].map(lambda v: "3+" if v >= 3 else str(v))
    out = out.groupby("Revisions", as_index=False).sum()
    return out
