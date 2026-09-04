# rdm-dash / Context

_Documentation of how the project is built, where data flows, and key conventions
so that future contributors can find their way._

---

## 1. What this project is

An interactive **Research Data Management (RDM) dashboard** for
**Eindhoven University of Technology (TU/e)**.
It answers research questions derived from the RDM Policy Implementation
Report using **Data Management Plan (DMP)** and **Ethical Review Board (ERB)**
exports from the TU/e Research Cockpit.

**Reporting period:** September 2025 – August 2026.
**Authors:** Nami Sunami and Liz Guzman-Ramirez (TU/e Data Stewards).
**License:** MIT (`LICENSE`).

---

## 2. Tech stack & hosting

| Layer | Tech |
|-------|------|
| Framework | [Quarto](https://quarto.org) ≥ 1.9 |
| Language | Python 3.14 (declared in `Pipfile`) |
| Data | [pandas](https://pandas.pydata.org), [Plotly](https://plotly.com) |
| Charts | Plotly Express (bar, histogram, stacked) |
| Styling | Quarto + custom CSS (`cosmo` theme, see `styles.css`) |
| Host | [Codeberg Pages](https://codeberg.org/tue-datastewards/rdm-dash) |

### 2.1 Python environment

The project uses **Pipenv** (not `.venv/` directly).
```bash
pipenv install --dev
pipenv run quarto preview    # live-reload
```

- `Pipfile` — declares `pandas`, `plotly`, and dev-`frictionless`.
- `Pipfile.lock` — pinned lockfile.
- `_site/`, `.quarto/`, `.venv/` are **gitignored**; the source CSVs in `data/`
  are tracked in git.

### 2.2 Deployment

The `main` branch is published via **Forgejo Actions** (Codeberg's Forgejo-based CI):

1. Push to `main` → workflow triggers.
2. Workflow runs `quarto render`.
3. `actions/deploy-pages@v4` uploads `_site/` to Pages.

Manual setup needed in Codeberg UI: **Settings → Pages → enable**;
**Settings → Actions → enable**.

---

## 3. Project structure

```
rdm-dash/
├── _quarto.yml          # Site config: navbar, CSS, theme (cosmo), execute: echo: false
├── index.qmd            # Overview dashboard: 1 integer card + 5 circle gauges + charts
├── data-storage.qmd     # Data storage, FAIR data adoption, repository & archival charts
├── process-eval.qmd     # Process evaluation metrics
├── communication-training.qmd  # Outreach activities
├── about.qmd            # Credits / about
├── queries.md           # Source SQL queries
├── _helpers.py            # Shared data loading + metric functions (~830 lines)
├── styles.css             # Custom CSS (RDM Handbook purple palette, gauges, navbar, sidebar)
├── data/
│   ├── DMPs_*.csv       # 19 cols, ~2200 rows
│   ├── ERBs_*.csv       # 5 cols, ~1250 rows
│   ├── departments.json # schema.org JSON-LD with Wikidata IDs (tracked in git)
│   ├── DMPs.schema.json # Frictionless table schema
│   └── ERBs.schema.json # Frictionless table schema
├── Pipfile / Pipfile.lock
└── .gitignore
```

### 3.1 Pages

| Page | Description | Key sections |
|------|-------------|--------------|
| **index.qmd** | Overview dashboard (all departments) | DMPs per dept, Compliance, Data handling, Workflow |
| **data-storage.qmd** | Storage, repositories & archival with dept dropdown | TU/e storage donut, FAIR Data Adoption, Repository choice, Archival |
| **process-eval.qmd** | Process quality metrics | KPI grid + charts |
| **communication-training.qmd** | Outreach activities | Metrics + tables |
| **about.qmd** | Credits | Text only |

> **Sidebar navigation** is configured in `_quarto.yml`.
> The old `dept-*.qmd` per-department files were removed in commit
> `850cfc8`; department views now live inside `index.qmd`,
> `data-storage.qmd` and `process-eval.qmd` with a JavaScript-based dropdown
> selector (`dept-select`) plus an All/Scientific/Educational purpose
> toggle (`purpose-toggle`) that shows/hides matching `.purpose-content`
> panels.

---

## 4. Data pipeline

```
TU/e Research Cockpit
  ├── gold tables (dmp_gold_fact_dedup, erb_gold_fact_dedup)
  └── SQL filter: issue_creation_time >= '2025-09-01'
        ↓ export CSV
data/DMPs_2025_09_10_onwards.csv  (19 cols)
data/ERBs_2025_09_10_onwards.csv  (5 cols, foreign keys → DMPs.issue_key)
        ↓ _helpers.py (load_dmps, load_erbs)
  - JSON list parsing
  - Bool coercion
  - numeric coercion (pre-computed day columns)
  - datetime coercion
  - department filtering
        ↓ metric functions
  - kpi_table → dict of totals/rates
  - kpi_html → HTML string of KPI cards
  - approval_by_department, dmps_by_department_purpose, etc.
        ↓ index.qmd, data-storage.qmd, process-eval.qmd
  - Plotly Express charts
  - `display(HTML(...))` for KPI gauges
```

### 4.1 Key data concepts

- **DMP status flow:** Draft → Submitted → Revision requested → Revised → Approved / Rejected
- **Actual DMPs only:** `load_dmps()` keeps only genuine DMPs. Rows with an
  empty status history (never-submitted drafts), DMPs currently **Retracted**,
  and non-DMP task items that never entered the real workflow (statuses such
  as *Done* / *Work in progress* / *In Progress*) are excluded from all
  counts and rates (see `_helpers.py::_is_actual_dmp()`).
- **ERB decision flow:** Conditional → Approved / Rejected / Retracted / Revisions → In progress
- **Trusted repositories:** 4TU.ResearchData, Zenodo, OSF, Figshare
- **TU/e storage:** 01 TU/e Network Drive, 02 Microsoft SharePoint/Teams, 04 SURF Research Drive
- **Archiving:** `archive_location == "tue_archive"` = RAPS archival
- **Pre-computed timing:** `days_to_first_submission` (Q8) and `days_to_first_response`
  (Q9) ship pre-computed in the export; `days_to_first_approval` is reserved
  (not currently consumed)

### 4.2 Data schemas

Schema files and the source CSVs are tracked in git.
Frictionless schemas describe columns, types, and primary/foreign keys.

### 4.3 Department metadata

```data/departments.json``` uses [schema.org](https://schema.org) JSON-LD to describe TU/e as an
``Organization`` with nine ``department`` sub-Organization entries. Each department carries a
``PropertyValue`` identifier with ``propertyID: "wikidata"`` and the corresponding Wikidata Q ID.

All department constants in ``_helpers.py`` (``DEPARTMENTS``, ``DEPT_SLUGS``, ``DEPT_ABBREVIATIONS``,
``DEPT_WIKIDATA``) are derived from this file at import time. To change a department's name,
Wikidata ID, or add a department, edit ``data/departments.json`` (not Python code).

Wikidata IDs were sourced from the ``has part`` (P527) statements on
`Q280824 (TU/e) <https://www.wikidata.org/wiki/Q280824>`_.

---

## 5. Styling conventions

### 5.1 Color tokens

The site uses the **RDM Handbook** purple palette (`rdm.tue.nl`):

| Token | Value | Usage |
|-------|-------|-------|
| `--rdm-700` | `#742459` | Link color, active accent, gauge fill |
| `--rdm-50` | `#fdf0f7` | Hover backgrounds, sidebar active |
| `--rdm-100` | `#fae1f0` | Gauge background arcs |
| `--slate-600` | `#303846` | Navbar background |
| `--slate-800` | `#111827` | Gauge value text, KPI values |

### 5.2 KPI cards

- All KPI cards have `min-height: 150px` for uniform spacing.
- **Integer cards** ("Total DMPs"): plain `.kpi-card kpi-blue` with the numeric value.
- **Percentage cards**: circle gauge SVGs (see `_helpers.py::gauge_svg()`).
- **No accent bar** — the old `.kpi-card::before` pseudo-element was removed.

#### Circle gauge format

```svg
<circle cx="66" cy="66" r="52" fill="none" stroke="var(--rdm-100)" stroke-width="12"/>
<circle cx="66" cy="66" r="52" fill="none" stroke="var(--kpi-accent)"
        stroke-width="12" stroke-linecap="round" transform="rotate(-90 66 66)"
        stroke-dasharray="326.7" stroke-dashoffset="114.4"/>
<text class="gauge-value" x="66" y="66" text-anchor="middle"
      dominant-baseline="central"
      style="...font-size:32px;font-weight:700">65%</text>
```

The fill circle's circumference is `2πr = 326.7`.
`stroke-dashoffset = 326.7 * (1 - pct)` controls the fill percentage,
starting from 12 o'clock via `rotate(-90)`.

### 5.3 Navbar

Full-width slate background (`#303846`) with white text.
Hover/active links use `--rdm-300` / `--rdm-200` purple.
A square TU/e logo (`images/logo.svg`, purple `#742459`
background with white logo) sits left of the title, sized via
`.navbar .navbar-brand img.navbar-logo` (`max-height: 2rem`).

### 5.4 Sidebar

Button-style navigation with active/highlight states using RDM purple.
Sidebar-subtitle class for muted secondary text, shown in breadcrumbs.

### 5.5 Plotly chart conventions

- **`color_discrete_map` is ignored for `px.pie`** — it is silently dropped,
  leaving Plotly's default palette. Apply segment colors directly instead:
  `fig.update_traces(marker_colors=[...])`, ordered to match `df["Category"]`.
- **`px.pie` sorts slices by value by default** — add `sort=False` in
  `fig.update_traces(...)` to keep a fixed category order regardless of the
  segment sizes.
- **Donuts render squashed at the default 900px width** of `render_chart()` —
  render pie/donut figures at ~500px (`h.render_chart(fig, width=500,
  height=450)`) so the circle stays circular.

---

## 6. `_helpers.py` — functions overview

| Category | Functions |
|----------|-----------|
| Loaders | `load_dmps()`, `load_erbs()` — with caching, JSON parsing, bool coercion. `load_dmps()` keeps only actual DMPs (see `_is_actual_dmp()`) |
| Helpers | `in_department()`, `filter_department()`, `department_erbs()`, `_parse_json_list()`, `_to_bool()`, `_is_actual_dmp()` |
| KPI | `kpi_table()`, `kpi_html()`, `gauge_svg()` — circle SVG generator |
| Overview | `approval_by_department()`, `dmps_by_department_purpose()` |
| Q3 (storage) | `storage_split()`, `storage_solution_by_department()`, `_canonical_storage_solution()` |
| Q5 (repos) | `repository_breakdown()`, `trusted_repository_split()` — returns exactly two groups: "Plan to Use Trusted Repository" / "Not Using Trusted Repository" |
| Q6 (archival) | `archive_split()` — binary TU/e archive (RAPS) usage |
| Q9 (response) | `first_response_time()` — reads pre-computed column; `status_history` fallback |
| Process | `process_kpi_html()` — revision/response/help-need cards (`_HELP_FIELDS`) |
| Feedback | `feedback_survey_html()`, `feedback_breakdown()`, `feedback_legend_html()`, `feedback_bar_html()`, `load_feedback_survey()` |
| Communication | `communication_kpi_html()`, `communication_attendees_by_department()`, `load_communication_efforts()` |
| Purpose | `filter_by_purpose()`, `purpose_toggle_html()`, `render_department_abbreviations()` |

### 6.1 KPI card generation

`kpi_html(df)` generates the shared KPI grid HTML:

- One integer card for "Total DMPs" (`kpi-card kpi-blue`)
- Six circle gauge cards via `gauge_svg()` for: Approval, ERB, Data sharing
  agreement, TU/e storage, Trusted repository, RAPS
- Each card includes a short `.kpi-desc` line (e.g. "1419 of 2174 DMPs are
  approved"); the Total DMPs card's description also shows the DMP creation
  date range for the current filter

### 6.2 `gauge_svg()`

Takes `value_float` (0–1) and `label`, returns a complete HTML string with
embedded SVG circle gauge.  The percentage is rendered as an SVG `<text>`
element centered in the circle.

---

## 7. How to work on this project

### 7.1 Setup (fresh clone)

```bash
git clone ssh://git@codeberg.org/tue-datastewards/rdm-dash.git
cd rdm-dash
pipenv install --dev
```

### 7.2 Add data

Place the two CSV exports from the Research Cockpit in `data/`:

```
data/DMPs_2025_09_10_onwards.csv
data/ERBs_2025_09_10_onwards.csv
```

The `frictionless` dev tool can validate them:

```bash
pipenv run python -c "from frictionless import validate; validate('data/DMPs.schema.json')"
pipenv run python -c "from frictionless import validate; validate('data/ERBs.schema.json')"
```

### 7.3 Preview

```bash
pipenv run quarto preview
```

Opens `http://localhost:8080`.
Changes to `.qmd`, `_quarto.yml`, and `styles.css` trigger live rebuilds.

> **No manual re-render by default.** The live preview rebuilds automatically
> on save, so changes to `.qmd`, `_quarto.yml`, and `styles.css` do not require
> running `quarto render` afterwards. **Do NOT run `quarto render` while the
> live preview is active** — it disrupts/restarts the preview server. Only
> render (7.4) when the user explicitly asks, or when a full `_site/` build is
> needed for deployment.

### 7.4 Full render

```bash
pipenv run quarto render
```

Produces `_site/` for inspection or deployment.

### 7.5 Troubleshooting

#### `BadResource: Bad resource ID`

Deno Sass cache corruption during live preview.

```bash
pkill -9 -f "quarto preview"
rm -rf ~/Library/Caches/quarto/sass .quarto
pipenv run quarto preview
```

#### `ModuleNotFoundError` / `rpds` errors

Make sure you're inside the Pipenv environment:

```bash
pipenv run quarto preview
```

#### Codeberg Pages not updating

Check **Settings → Actions** is enabled in the Codeberg UI.
The workflow file is `.forgejo/workflows/deploy-pages.yml` and
triggers on `push main`.

---

## 8. Key files at a glance

| Path | Role |
|------|------|
| `_quarto.yml` | Site config: navbar, sidebar, CSS, theme, code-hidden |
| `index.qmd` | Homepage — 1 integer card + 5 circle gauges + all charts |
| `data-storage.qmd` | Storage, repositories & archival with dept dropdown |
| `process-eval.qmd` | Process quality KPI grid + feedback survey |
| `_helpers.py` | All data logic — loaders, filters, metrics, HTML builders |
| `styles.css` | RDM purple palette, KPI gauges, navbar, sidebar styling |
| `data/departments.json` | schema.org JSON-LD department definitions with Wikidata IDs |
| `data/*.schema.json` | Frictionless schemas for data validation |
| `Pipfile` | Dependencies: `pandas`, `plotly`, dev `frictionless` |
| `.gitignore` | Keeps `_site/`, `.quarto/`, `.venv/` out of git |

---

_Last updated: 2026-08-12_
