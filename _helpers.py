"""Shared data loading and metrics for the RDM dashboard.

Loads the DMP and ERB exports from ``data/`` and exposes tidy dataframes
and metric functions for the overview and per-department dashboards.
"""

from __future__ import annotations

import json
from collections import Counter
from functools import cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DMP_FILE = DATA_DIR / "DMPs_2025_09_10_onwards.csv"
ERB_FILE = DATA_DIR / "ERBs_2025_09_10_onwards.csv"
HISTORICAL_DMP_FILE = DATA_DIR / "dmps-2024-2025.json"
FEEDBACK_SURVEY_FILE = DATA_DIR / "feedback-survey-responses.csv"

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

# DMP feedback survey columns (names match the export after cleaning).
FEEDBACK_LIKERT_COLS = [
    "Finding the DMP template in the TU/e Research Cockpit was easy",
    "The process of completing my DMP was easy",
    "The instructions and guidance provided by the system were clear",
]
FEEDBACK_CONTACT_COL = "Did you have contact with a data steward?"
FEEDBACK_STEWARD_COL = "How helpful was the advice of the data steward?"

# Canonical response order (1..5) for both scales.
FEEDBACK_LIKERT_ORDER = [
    "Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree",
]
FEEDBACK_STAR_ORDER = [
    "1 star", "2 stars", "3 stars", "4 stars", "5 stars",
]

# Department metadata loaded from data/departments.json (schema.org JSON-LD).
DEPARTMENTS_FILE = DATA_DIR / "departments.json"

_SLUG_MAP = {
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

_ABBR_MAP = {
    "Industrial Design (ID)": "ID",
    "Industrial Engineering and Innovation Sciences (IE&IS)": "IE&IS",
    "Built Environment (BE)": "BE",
    "Mathematics and Computer Science (M&CS)": "M&CS",
    "Biomedical Engineering (BmE)": "BmE",
    "Mechanical Engineering (ME)": "ME",
    "Applied Physics and Science Education (AP&SE)": "APSE",
    "Electrical Engineering (EE)": "EE",
    "Chemical Engineering and Chemistry (CE&C)": "CE&C",
}


def _load_departments() -> dict:
    """Load department metadata from ``DEPARTMENTS_FILE``.

    Returns a dict with keys: ``names`` (list), ``slugs``, ``abbreviations``,
    ``wikidata`` (each a dict mapping name -> value).
    """
    with open(DEPARTMENTS_FILE) as f:
        data = json.load(f)
    depts = data.get("department", [])
    names = [d["name"] for d in depts]
    slugs = {}
    abbrs = {}
    wikidata = {}
    for d in depts:
        name = d["name"]
        slugs[name] = _SLUG_MAP.get(name, "")
        abbrs[name] = _ABBR_MAP.get(name, "")
        identifiers = d.get("identifier", {})
        if isinstance(identifiers, dict) and identifiers.get("propertyID") == "wikidata":
            wikidata[name] = identifiers["value"]
        elif isinstance(identifiers, list):
            for id_ in identifiers:
                if isinstance(id_, dict) and id_.get("propertyID") == "wikidata":
                    wikidata[name] = id_["value"]
                    break
    return {
        "names": names,
        "slugs": slugs,
        "abbreviations": abbrs,
        "wikidata": wikidata,
    }


_DEPARTMENT_DATA = _load_departments()

DEPARTMENTS: list[str] = _DEPARTMENT_DATA["names"]
DEPT_SLUGS: dict[str, str] = _DEPARTMENT_DATA["slugs"]
DEPT_ABBREVIATIONS: dict[str, str] = _DEPARTMENT_DATA["abbreviations"]
DEPT_WIKIDATA: dict[str, str] = _DEPARTMENT_DATA["wikidata"]


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
    """Parse a JSON array string into a list.

    Falls back to comma-splitting for plain comma-separated values (e.g.
    ``metadata_standard``). Empty/null -> [].
    """
    if pd.isna(val) or val in ("", "null", "[]"):
        return []
    try:
        v = json.loads(val)
    except (json.JSONDecodeError, TypeError):
        # Not JSON — treat as comma-separated plain string.
        return [p.strip() for p in str(val).split(",") if p.strip()]
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
    if "status_history" in df.columns:
        df["status_history_parsed"] = df["status_history"].map(_parse_json_list)
    for c in ("days_to_first_submission", "days_to_first_response", "days_to_first_approval"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("issue_creation_time", "latest_status_time", "erb_link_creation_date", "gold_processed_at"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
    return df


@cache
def load_historical_dmps() -> int:
    """Total DMPs from the 2024–2025 historical JSON (sum of all observations)."""
    with open(HISTORICAL_DMP_FILE) as f:
        data = json.load(f)
    return sum(
        obs["schema:value"]["schema:value"]
        for obs in data.get("observation", [])
    )


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


@cache
def load_feedback_survey() -> pd.DataFrame:
    """Load the DMP feedback survey responses.

    The export has a UTF-8 BOM and non-breaking spaces in the header names;
    both are cleaned up here. Column names match the survey wording.
    """
    df = pd.read_csv(FEEDBACK_SURVEY_FILE, encoding="utf-8-sig")
    df.columns = [c.replace("\xa0", "").strip() for c in df.columns]
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
    n_sharing = int(df["data_sharing"].isin(["inside_eea", "outside_eea"]).sum()) if n else 0
    n_tue_storage = int(
        df["data_storage_list"].map(
            lambda v: any(s in TUE_STORAGE for s in v)
        ).sum()
    ) if n else 0
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
        "Data sharing agreement": n_sharing,
        "Data sharing agreement rate": n_sharing / n if n else 0,
        "TU/e storage": n_tue_storage,
        "TU/e storage rate": n_tue_storage / n if n else 0,
        "Repository selected": n_repo,
        "Repository selection rate": n_repo / n if n else 0,
        "Trusted repository": n_trusted,
        "Trusted repository rate": n_trusted / n if n else 0,
        "Archived at RAPS": n_raps,
        "RAPS archival rate": n_raps / n if n else 0,
    }


def kpi_html(df: pd.DataFrame, dept: str | None = None, show_trend: bool = True) -> str:
    """Return an HTML string for the KPI card grid.

    If ``dept`` is given (a full department name from ``DEPARTMENTS``), its
    abbreviation is appended to each KPI description.

    Set ``show_trend=False`` to suppress the year-over-year trend indicator
    (e.g. when historical data lacks a purpose breakdown).
    """
    k = kpi_table(df)
    n = k["Total DMPs"]
    abbr = DEPT_ABBREVIATIONS.get(dept, dept) if dept else None

    total_desc = "Total DMPs submitted this period"
    if "issue_creation_time" in df.columns:
        dates = df["issue_creation_time"].dropna()
        if len(dates):
            start = dates.min().strftime("%B %Y")
            end = dates.max().strftime("%B %Y")
            total_desc = f"Total DMPs submitted from {start} to {end}"
            if abbr:
                total_desc = f"Total DMPs submitted at {abbr} from {start} to {end}"

    items = []

    trend_delta = ""
    if show_trend:
        prev_total = load_historical_dmps()
        delta = n - prev_total
        pct_change = delta / prev_total if prev_total else 0
        glyph = "\u25b2" if delta >= 0 else "\u25bc"
        trend_class = "trend-up" if delta >= 0 else "trend-down"
        trend_delta = (
            f'<div class="kpi-delta">'
            f'<span class="{trend_class}">{glyph} {abs(delta)} ({abs(pct_change):.0%})</span>'
            f' vs 2024\u20132025</div>'
        )

    total_card = (
        '<div class="kpi-card kpi-blue">'
        '<div class="kpi-label"><p>Total DMPs</p></div>'
        '<div class="kpi-value"><p>' + str(len(df)) + '</p></div>'
        f'{trend_delta}'
        f'<div class="kpi-desc">{total_desc}</div>'
        '</div>'
    )

    if abbr:
        pct_kpis = [
            ("Approval rate", k["Approval rate"],
             f'{k["Approved DMPs"]} of {n} DMPs are approved at {abbr}'),
            ("DMPs with ERB", k["ERB linkage rate"],
             f'{k["Linked ERB"]} of {n} DMPs are linked to an ERB at {abbr}'),
            ("Data sharing agreement", k["Data sharing agreement rate"],
             f'{k["Data sharing agreement"]} of {n} DMPs require a data sharing agreement at {abbr}'),
            ("TU/e storage", k["TU/e storage rate"],
             f'{k["TU/e storage"]} of {n} DMPs use TU/e-supported storage at {abbr}'),
            ("Trusted repository", k["Trusted repository rate"],
             f'{k["Trusted repository"]} of {n} DMPs use a trusted data repository at {abbr}'),
            ("Archived at RAPS", k["RAPS archival rate"],
             f'{k["Archived at RAPS"]} of {n} DMPs at {abbr} are archived at RAPS'),
        ]
    else:
        pct_kpis = [
            ("Approval rate", k["Approval rate"],
             f'{k["Approved DMPs"]} of {n} DMPs are approved'),
            ("DMPs with ERB", k["ERB linkage rate"],
             f'{k["Linked ERB"]} of {n} DMPs are linked to an ERB'),
            ("Data sharing agreement", k["Data sharing agreement rate"],
             f'{k["Data sharing agreement"]} of {n} DMPs require a data sharing agreement'),
            ("TU/e storage", k["TU/e storage rate"],
             f'{k["TU/e storage"]} of {n} DMPs use TU/e-supported storage'),
            ("Trusted repository", k["Trusted repository rate"],
             f'{k["Trusted repository"]} of {n} DMPs use a trusted data repository'),
            ("Archived at RAPS", k["RAPS archival rate"],
             f'{k["Archived at RAPS"]} of {n} DMPs are archived at RAPS'),
        ]
    for label, value, desc in pct_kpis:
        items.append(gauge_svg(value, label, desc))

    return '<div class="kpi-header">' + total_card + '<div class="kpi-grid">' + "".join(items) + "</div></div>"


def render_chart(fig, width: int = 900, height: int = 450) -> str:
    """Render a Plotly figure as an inline SVG image (no JS needed)."""
    import plotly.io as pio
    svg = pio.to_image(fig, format="svg", width=width, height=height)
    return (
        f'<div style="width:100%;max-width:{width}px;margin:0 auto 1.5rem">'
        f'{svg.decode()}</div>'
    )


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


def dmps_by_department_purpose(df: pd.DataFrame) -> pd.DataFrame:
    """DMP counts per department split by purpose (Q1 / cross-cutting).

    Returns one row per (department, purpose) with the DMP count, so the
    rows can be stacked to decompose each department's total. ``is_scientific``
    is mapped to ``Scientific`` (true) / ``Educational`` (false) / ``Unknown``
    (null); the three categories sum to the department's total DMP count.
    """
    rows = []
    for dept in DEPARTMENTS:
        sub = filter_department(df, dept)
        n_sci = int((sub["is_scientific"] == True).sum())
        n_edu = int((sub["is_scientific"] == False).sum())
        n_unk = int(sub["is_scientific"].isna().sum())
        for label, count in (
            ("Scientific", n_sci),
            ("Educational", n_edu),
            ("Unknown", n_unk),
        ):
            rows.append({"Department": dept, "Purpose": label, "DMPs": count})
    return pd.DataFrame(rows)


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
    return pd.DataFrame({
        "Category": ["Using Trusted Repository", "Not Using Trusted Repository"],
        "DMPs": [trusted, n - trusted],
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


def archive_split(df: pd.DataFrame) -> pd.DataFrame:
    """Split DMPs by TU/e archive (RAPS) archival usage (Q6)."""
    n = len(df)
    if not n:
        return pd.DataFrame(columns=["Category", "DMPs"])
    using = int((df["archive_location"] == "tue_archive").sum())
    return pd.DataFrame({
        "Category": ["Using TU/e archive", "Not using TU/e archive"],
        "DMPs": [using, n - using],
    })


def storage_split(df: pd.DataFrame) -> pd.DataFrame:
    """Split DMPs by TU/e-compliant storage usage (Q3)."""
    n = len(df)
    if not n:
        return pd.DataFrame(columns=["Category", "DMPs"])

    compliant = int(
        df["data_storage_list"].map(
            lambda v: any(s in TUE_STORAGE for s in v)
        ).sum()
    )
    non_compliant = n - compliant
    return pd.DataFrame({
        "Category": ["Using TU/e storage", "Not using TU/e storage"],
        "DMPs": [compliant, non_compliant],
    })


# Standard TU/e storage services shown in the "TU/e data storage" chart (Q3).
TU_E_STORAGE_SOLUTIONS = {
    "TU/e Network Drive",
    "Microsoft SharePoint/Teams",
    "Microsoft OneDrive",
    "SURF Research Drive",
}


def _canonical_storage_solution(item: str) -> str | None:
    """Map a raw ``data_storage_list`` item to its canonical TU/e service name."""
    s = " ".join(str(item).split())
    if len(s) >= 3 and s[0:2].isdigit() and s[2] == " ":
        s = s[3:]
    return s if s in TU_E_STORAGE_SOLUTIONS else None


def storage_solution_by_department(df: pd.DataFrame) -> pd.DataFrame:
    """DMP counts per TU/e storage service and department (Q3).

    A DMP can list several services, so DMP counts across rows sum to more
    than the number of DMPs.
    """
    if not len(df):
        return pd.DataFrame(columns=["Department", "Solution", "DMPs"])
    rows = []
    for dept in DEPARTMENTS:
        sub = filter_department(df, dept)
        counts = Counter()
        for services in sub["data_storage_list"]:
            for item in services:
                sol = _canonical_storage_solution(item)
                if sol:
                    counts[sol] += 1
        for sol, n in counts.items():
            rows.append({"Department": dept, "Solution": sol, "DMPs": n})
    return pd.DataFrame(rows)


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


def revision_summary(df: pd.DataFrame) -> dict:
    """Headline revision metrics (Q7)."""
    n = len(df)
    if not n:
        return {
            "DMPs with \u22651 revision": 0,
            "% with \u22651 revision": 0,
            "Avg revisions per DMP": 0,
        }

    def n_revisions(seq):
        return sum(1 for s in seq if s == "Revision requested")

    counts = df["ordered_status_transition_list"].map(n_revisions)
    n_rev = int((counts > 0).sum())
    return {
        "DMPs with \u22651 revision": n_rev,
        "% with \u22651 revision": float((counts > 0).mean()),
        "Avg revisions per DMP": float(counts.mean()),
    }


# Q2 additions --------------------------------------------------------------

def erb_approval_by_department(df_dmps: pd.DataFrame, df_erbs: pd.DataFrame) -> pd.DataFrame:
    """ERB approval rate per department (Q2)."""
    out = []
    for dept in DEPARTMENTS:
        sub_dmps = filter_department(df_dmps, dept)
        keys = set(sub_dmps["issue_key"])
        sub_erbs = df_erbs[df_erbs["related_dmp"].isin(keys)]
        n = len(sub_erbs)
        approved = int(sub_erbs["is_approved"].fillna(False).sum()) if n else 0
        out.append({
            "Department": dept,
            "ERBs": n,
            "Approved": approved,
            "Approval rate": approved / n if n else 0,
        })
    return pd.DataFrame(out)


def erb_integration_timing(df_dmps: pd.DataFrame) -> pd.DataFrame:
    """Distribution of days to ERB link creation (Q2)."""
    if not len(df_dmps):
        return pd.DataFrame(columns=["Metric", "Value"])
    s = df_dmps.loc[df_dmps["days_to_erb_link_creation"].notna(), "days_to_erb_link_creation"]
    s = pd.to_numeric(s, errors="coerce").dropna()
    if not len(s):
        return pd.DataFrame(columns=["Metric", "Value"])
    return pd.DataFrame({
        "Metric": ["Median", "Mean", "25th pct", "75th pct"],
        "Value": [s.median(), s.mean(), s.quantile(0.25), s.quantile(0.75)],
    })


# Q4 -------------------------------------------------------------------------

def data_sharing_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Breakdown of data-sharing destinations (Q4)."""
    if not len(df):
        return pd.DataFrame(columns=["Destination", "DMPs"])
    label_map = {
        "no": "No sharing",
        "inside_eea": "Inside EEA",
        "outside_eea": "Outside EEA",
    }
    s = df["data_sharing"].fillna("(unknown)").replace({"null": "(unknown)"})
    s = s.map(lambda v: label_map.get(v, v))
    counts = s.value_counts().reset_index()
    counts.columns = ["Destination", "DMPs"]
    return counts


def special_category_summary(df: pd.DataFrame) -> dict:
    """Special-category (DPIA-relevance proxy) rate (Q4)."""
    n = len(df)
    if not n:
        return {"Special-category rate": 0}
    sc = int(df["has_special_category"].fillna(False).sum())
    return {"Special-category rate": sc / n}


# Q8 / Q9 -------------------------------------------------------------------

def _sorted_history(row) -> list:
    """Parse status_history into a chronologically-sorted list of (status, ts)."""
    hist = row.get("status_history_parsed")
    if not hist:
        return []
    pairs = []
    for ev in hist:
        if not isinstance(ev, dict):
            continue
        st = ev.get("status")
        ts = ev.get("timestamp")
        if st is None or ts is None:
            continue
        dt = pd.to_datetime(ts, errors="coerce", utc=True)
        if pd.notna(dt):
            pairs.append((st, dt))
    pairs.sort(key=lambda p: p[1])
    return pairs


def days_to_first_submission(df: pd.DataFrame) -> pd.Series:
    """Days from DMP creation to first 'Submitted' status (Q8).

    Uses the pre-computed ``days_to_first_submission`` column from the
    Cockpit export when available; falls back to computing it from
    ``status_history`` if the column is absent.
    """
    if not len(df):
        return pd.Series(dtype=float)
    if "days_to_first_submission" in df.columns:
        return df["days_to_first_submission"].astype(float)
    out = []
    for _, row in df.iterrows():
        created = row["issue_creation_time"]
        if pd.isna(created):
            out.append(None)
            continue
        pairs = _sorted_history(row)
        first_sub = next((ts for st, ts in pairs if st == "Submitted"), None)
        out.append((first_sub - created).days if first_sub is not None else None)
    return pd.Series(out, index=df.index)


def first_response_time(df: pd.DataFrame) -> pd.Series:
    """Days from first 'Submitted' to the next status transition (Q9).

    Uses the pre-computed ``days_to_first_response`` column from the
    Cockpit export when available; falls back to computing it from
    ``status_history`` if the column is absent.
    """
    if not len(df):
        return pd.Series(dtype=float)
    if "days_to_first_response" in df.columns:
        return df["days_to_first_response"].astype(float)
    out = []
    for _, row in df.iterrows():
        pairs = _sorted_history(row)
        # find first Submitted
        sub_idx = next((i for i, (st, _) in enumerate(pairs) if st == "Submitted"), None)
        if sub_idx is None or sub_idx + 1 >= len(pairs):
            out.append(None)
            continue
        sub_ts = pairs[sub_idx][1]
        next_ts = pairs[sub_idx + 1][1]
        out.append((next_ts - sub_ts).days if next_ts >= sub_ts else None)
    return pd.Series(out, index=df.index)


# Q10 -----------------------------------------------------------------------

_HELP_FIELDS = ["data_repository", "metadata_standard", "processing_tools_list"]


def help_needed_rate(df: pd.DataFrame) -> pd.DataFrame:
    """'I need advice' rate per DMP field (Q10)."""
    n = len(df)
    if not n:
        return pd.DataFrame(columns=["Field", "DMPs", "Rate"])
    rows = []
    for field in _HELP_FIELDS:
        count = int(df[field].map(
            lambda v: any("i need advice" in str(x).lower() for x in v)
        ).sum())
        rows.append({"Field": field, "DMPs": count, "Rate": count / n})
    combined = int(df.apply(
        lambda r: any("i need advice" in str(x).lower() for f in _HELP_FIELDS for x in r[f]),
        axis=1,
    ).sum())
    rows.append({"Field": "Any field (combined)", "DMPs": combined, "Rate": combined / n})
    return pd.DataFrame(rows)


def gauge_svg(value_float: float, label: str, description: str | None = None) -> str:
    """Return an inline SVG circle gauge for a decimal value 0-1."""
    pct = max(0.0, min(1.0, value_float))
    pct_display = f"{pct:.0%}"
    x = 66
    y = 66
    r = 52
    t = 12
    circumference = 2 * 3.14159265 * r
    offset = circumference * (1 - pct)
    ca_str = f"{round(circumference, 1)}"
    off_str = f"{round(offset, 1)}"
    desc_html = f'<div class="kpi-desc">{description}</div>' if description else ""
    return (
        '<div class="kpi-card kpi-circle">'
        '<div class="gauge-wrap">'
        '<svg class="gauge-svg" viewBox="0 0 132 132" width="132" height="132">'
        '<circle cx="{x}" cy="{y}" r="{r}" '
        'fill="none" stroke="var(--rdm-100)" stroke-width="{t}" />'
        '<circle cx="{x}" cy="{y}" r="{r}" '
        'fill="none" stroke="var(--kpi-accent, var(--rdm-700))" '
        'stroke-width="{t}" stroke-linecap="round" '
        'transform="rotate(-90 {x} {y})" '
        'stroke-dasharray="{ca}" stroke-dashoffset="{off}" />'
        '<text class="gauge-value" x="{x}" y="{y}" '
        'text-anchor="middle" dominant-baseline="central" '
        'style="fill:var(--slate-800,#111827);font-size:32px;font-weight:700">'
        '{pct_display}</text>'
        '</svg>'
        '</div>'
        '<div class="kpi-label">{label}</div>'
        '{desc_html}'
        '</div>'
    ).format(
        label=label, x=x, y=y, r=r, t=t,
        ca=ca_str, off=off_str,
        pct_display=pct_display,
        desc_html=desc_html,
    )


# Purpose filtering -----------------------------------------------------------

def filter_by_purpose(df: pd.DataFrame, purpose: bool | None) -> pd.DataFrame:
    """Filter DMPs by purpose. None = all, True = scientific, False = educational."""
    if purpose is None:
        return df
    return df[df["is_scientific"] == purpose].copy()


PURPOSES = [("all", None), ("scientific", True), ("educational", False)]


def purpose_toggle_html() -> str:
    """Render the purpose toggle button group."""
    buttons = []
    for value, _ in PURPOSES:
        cls = "purpose-btn active" if value == "all" else "purpose-btn"
        label = {"all": "All purposes", "scientific": "Scientific",
                 "educational": "Educational"}[value]
        buttons.append(f'  <button class="{cls}" data-purpose="{value}">{label}</button>')
    return (
        '<div class="purpose-toggle">\n'
        + "\n".join(buttons)
        + "\n</div>"
    )

# Render department abbreviations -----------------------------------------------------------
def render_department_abbreviations(font_size: str = "0.85em") -> str:
    parts = []
    for dept in sorted(DEPARTMENTS, key=lambda d: DEPT_ABBREVIATIONS[d]):
        abbr = DEPT_ABBREVIATIONS[dept]
        parts.append(f'<b>{abbr}</b> = {dept}')
    return f'<p style="font-size:{font_size};color:#6b7280"><i>{"</i>, <i>".join(parts)}</i></p>'


def process_kpi_html(df: pd.DataFrame, dept: str | None = None,
                     purpose: str | None = None) -> str:
    """Return an HTML string for the process-evaluation KPI card grid.

    Three cards: revision requested rate gauge, data steward response time
    number card, and 'I need advice' rate gauge.

    If ``dept`` is given, the department abbreviation is appended to
    descriptions.  If ``purpose`` is "scientific" or "educational", the study
    type is inserted into the descriptions ("all" / None keeps the generic
    wording).
    """
    n = len(df)
    abbr = DEPT_ABBREVIATIONS.get(dept, dept) if dept else None
    pword = purpose if purpose in ("scientific", "educational") else None
    ptext = f"{pword} DMPs" if pword else "DMPs"

    # Revision requested rate
    with_rev = int(df["ordered_status_transition_list"].map(
        lambda v: any(s == "Revision requested" for s in v)
    ).sum()) if n else 0
    rev_rate = with_rev / n if n else 0

    # Data steward response time (only DMPs with a response >= 1 day after submission)
    resp = first_response_time(df).dropna()
    resp = resp[resp >= 1]
    median_days = resp.median() if len(resp) else None
    mean_days = resp.mean() if len(resp) else None
    n_resp = len(resp)

    # Help needed rate
    needs_help = int(df.apply(
        lambda r: any(
            "i need advice" in str(x).lower()
            for f in _HELP_FIELDS
            for x in r.get(f, [])
        ),
        axis=1,
    ).sum()) if n else 0
    help_rate = needs_help / n if n else 0

    # Build cards
    if abbr:
        rev_desc = f'{with_rev} of {n} {ptext} at {abbr} sent back for revision'
    else:
        rev_desc = f'{with_rev} of {n} {ptext} sent back for revision'
    rev_gauge = gauge_svg(rev_rate, "Revision requested rate", rev_desc)

    if median_days is not None and not pd.isna(median_days):
        subj = f"{pword} DMP" if pword else "DMP"
        desc = f"Median response time across {n_resp} {subj} submissions"
        if mean_days is not None:
            desc += f" ({mean_days:.1f} days mean)"
        if abbr:
            desc = f"{desc} at {abbr}"
        resp_card = (
            '<div class="kpi-card kpi-blue">'
            '<span class="info-tip" aria-label="Calculation note">'
            '<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">'
            '<circle cx="8" cy="8" r="7.2" fill="none" stroke="currentColor" stroke-width="1.4"/>'
            '<path d="M8 7.2v3.6M8 5.1h.01" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round"/></svg>'
            '<span class="info-tip-text">Only DMPs with a response at least 1 day '
            'after submission are included (responses under 1 day are excluded).</span>'
            '</span>'
            '<div class="kpi-label"><p>Data Steward Response Time</p></div>'
            f'<div class="kpi-value"><p>{median_days:.1f} days</p></div>'
            f'<div class="kpi-desc">{desc}</div>'
            '</div>'
        )
    else:
        resp_card = (
            '<div class="kpi-card kpi-blue">'
            '<div class="kpi-label"><p>Data Steward Response Time</p></div>'
            '<div class="kpi-value"><p>N/A</p></div>'
            '<div class="kpi-desc">No response time data available</div>'
            '</div>'
        )

    if abbr:
        help_desc = f'{needs_help} of {n} {ptext} at {abbr} requested help'
    else:
        help_desc = f'{needs_help} of {n} {ptext} requested help'
    help_gauge = gauge_svg(help_rate, "'I need advice' at first submission", help_desc)

    return '<div class="kpi-grid">' + rev_gauge + resp_card + help_gauge + '</div>'


# Feedback survey -------------------------------------------------------------

def feedback_breakdown() -> pd.DataFrame:
    """Response counts and shares for the four DMP feedback survey questions.

    Returns a long-form DataFrame with columns ``Aspect``, ``Response``,
    ``Count`` and ``Share`` (0-1).  The three Likert items use the canonical
    ``Strongly Disagree`` ... ``Strongly Agree`` order; the data steward
    question uses ``1 star`` ... ``5 stars`` and only includes respondents who
    had contact with a data steward.  Zero-count categories are kept so every
    aspect spans the same 1-5 scale.
    """
    df = load_feedback_survey()
    rows = []

    def add(aspect: str, counts: pd.Series, order: list[str], n: int) -> None:
        for label in order:
            c = int(counts.get(label, 0))
            rows.append({
                "Aspect": aspect, "Response": label, "Count": c,
                "Share": c / n if n else 0.0,
            })

    for col in FEEDBACK_LIKERT_COLS:
        add(col, df[col].value_counts(), FEEDBACK_LIKERT_ORDER, len(df))

    stew = df[df[FEEDBACK_STEWARD_COL].notna()]
    n_stew = len(stew)
    counts = stew[FEEDBACK_STEWARD_COL].astype(int).value_counts()
    for i, label in enumerate(FEEDBACK_STAR_ORDER, start=1):
        c = int(counts.get(i, 0))
        rows.append({
            "Aspect": FEEDBACK_STEWARD_COL, "Response": label, "Count": c,
            "Share": c / n_stew if n_stew else 0.0,
        })
    return pd.DataFrame(rows)


def feedback_legend_html(kind: str = "likert") -> str:
    """Legend for a 1-5 response scale (``likert`` or ``stars``)."""
    if kind == "stars":
        labels = FEEDBACK_STAR_ORDER
    else:
        labels = FEEDBACK_LIKERT_ORDER
    items = "".join(
        f'<li><span class="legend-swatch" data-level="{i}"></span>{label}</li>'
        for i, label in reversed(list(enumerate(labels, start=1)))
    )
    return f'<div class="feedback-legend"><ul>{items}</ul></div>'


def feedback_bar_html(rows: pd.DataFrame, title: str, n: int) -> str:
    """Return an HTML figure with a single horizontal stacked bar.

    ``rows`` is the ``feedback_breakdown()`` slice for one aspect, already in
    1-5 order.  Each segment is sized by its share; a count label is shown
    only when the segment is wide enough to fit.  The figcaption reports the
    share of positive responses (levels 4-5), with a tooltip explaining the
    definition for the applicable scale.
    """
    segs = []
    for level, (_, r) in reversed(list(enumerate(rows.iterrows(), start=1))):
        pct = r["Share"] * 100
        count = int(r["Count"])
        label = f'<span class="seg-count">{pct:.0f}%</span>' if pct >= 9 else ""
        segs.append(
            f'<div class="feedback-seg" data-level="{level}" '
            f'style="flex-grow:{pct:.4f}" '
            f'title="{r["Response"]}: {count} ({pct:.0f}%)">{label}</div>'
        )

    positive = rows["Count"].iloc[-2:].sum() / n
    if "star" in rows["Response"].iloc[0]:
        tip = "Share of respondents who rated the data steward's advice 4 or 5 stars."
    else:
        tip = 'Share of responses that were "Agree" or "Strongly Agree" '
        tip += "(levels 4-5 of the 5-point scale)."
    positive_html = (
        f'<span class="feedback-positive info-tip" tabindex="0">'
        f'{positive:.0%} positive'
        f'<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">'
        f'<circle cx="8" cy="8" r="7.2" fill="none" stroke="currentColor" stroke-width="1.4"/>'
        f'<path d="M8 7.2v3.6M8 5.1h.01" stroke="currentColor" stroke-width="1.6" '
        f'stroke-linecap="round"/></svg>'
        f'<span class="info-tip-text">{tip}</span></span>'
    )
    return (
        f'<figure class="feedback-bar-figure">'
        f'<figcaption>'
        f'<span class="feedback-title">{title} <span class="feedback-n">(n = {n})</span></span> '
        f'{positive_html}'
        f'</figcaption>'
        f'<div class="feedback-bar" role="img" aria-label="{title}">{"".join(segs)}</div>'
        f'</figure>'
    )


def feedback_survey_html() -> str:
    """The complete survey widget: legends plus the four stacked bars."""
    fb = feedback_breakdown()
    df = load_feedback_survey()
    n = len(df)
    n_stew = int(df[FEEDBACK_STEWARD_COL].notna().sum())
    parts = []
    for col in FEEDBACK_LIKERT_COLS:
        parts.append(feedback_bar_html(fb[fb["Aspect"] == col], col, n))
        parts.append(feedback_legend_html("likert"))
    parts.append(feedback_bar_html(
        fb[fb["Aspect"] == FEEDBACK_STEWARD_COL],
        FEEDBACK_STEWARD_COL, n_stew,
    ))
    parts.append(feedback_legend_html("stars"))
    return "\n".join(parts)
