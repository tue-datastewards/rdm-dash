# rdm-dash

An interactive dashboard about Research Data Management (RDM) at Eindhoven
University of Technology, built with [Quarto](https://quarto.org). Authored by
Nami Sunami and Liz Guzman-Ramirez, TU/e Data Stewards.

The dashboard answers research questions derived from the RDM Policy
Implementation Report using Data Management Plan (DMP) and Ethical Review
Board (ERB) exports from the TU/e Research Cockpit (reporting period
September 2025 – August 2026).

## Prerequisites

- [Quarto](https://quarto.org/docs/get-started/) ≥ 1.9
- [Pipenv](https://pipenv.pyp.org/) for the Python environment
- Python 3.14 (declared in the `Pipfile`)

## Setup

Clone the repository and install the Python environment:

```bash
git clone <repo-url> rdm-dash
cd rdm-dash
pipenv install --dev
```

Runtime dependencies: `pandas`, `plotly`. Dev dependency: `frictionless`
(for validating the data schemas).

### Add the data

The two source CSVs are tracked in git. To refresh them with a new export,
place the files in `data/`:

```
data/DMPs_2025_09_10_onwards.csv   # Data Management Plans (2230 rows × 19 cols)
data/ERBs_2025_09_10_onwards.csv   # Ethical Review Board applications (1259 rows × 5 cols)
```

Their structure is version-controlled as [Frictionless Data](https://specs.frictionlessdata.io/)
Table Schemas (see _Data & schemas_ below), so the columns and types are
documented in the repo alongside the data.

## Preview the site

Render and serve the site locally with live reload (Quarto must run inside the
environment so it can find `pandas`/`plotly`):

```bash
pipenv run quarto preview
```

By default the site is available at <http://localhost:8080>. Changes to `.qmd`
files, `_quarto.yml`, or `styles.css` trigger an automatic rebuild.

To render the site once without serving:

```bash
pipenv run quarto render
```

Output is written to `_site/`.

## Dashboard structure

- **`index.qmd`** — overview across all departments: six KPI callouts plus
  tabbed charts grouped into **Compliance**, **Data handling**, and
  **Workflow**.
- **`dept-<slug>.qmd`** × 9 — one page per department; each is a thin wrapper
  that filters the data and `{{< include >}}`s the shared body.
- **`_dept-content.qmd`** — the shared department dashboard body (DRY).
- **`_helpers.py`** — data loading, cleaning, and all metric functions.

Each chart displays the research question (Q1–Q10) it answers as a blockquote
above the chart.

Departments:

| File                                    | Department                                           |
| --------------------------------------- | ---------------------------------------------------- |
| `dept-industrial-design.qmd`            | Industrial Design (ID)                               |
| `dept-industrial-engineering.qmd`       | Industrial Engineering & Innovation Sciences (IE&IS) |
| `dept-built-environment.qmd`            | Built Environment (BE)                               |
| `dept-mathematics-computer-science.qmd` | Mathematics & Computer Science (M&CS)                |
| `dept-biomedical-engineering.qmd`       | Biomedical Engineering (BmE)                         |
| `dept-mechanical-engineering.qmd`       | Mechanical Engineering (ME)                          |
| `dept-applied-physics.qmd`              | Applied Physics & Science Education (APSE)           |
| `dept-electrical-engineering.qmd`       | Electrical Engineering (EE)                          |
| `dept-chemical-engineering.qmd`         | Chemical Engineering & Chemistry (CE&C)              |

## Data & schemas

The source CSVs are filtered to `issue_creation_time >= '2025-09-01'` and
exported from the Cockpit gold tables (`dmp_gold_fact_dedup`,
`erb_gold_fact_dedup`); the original SQL is in [`queries.md`](queries.md).

The dataset structure is described with [Frictionless Data Table Schemas](https://specs.frictionlessdata.io/table-schema/)
and validated with the `frictionless` package:

- [`data/DMPs.schema.json`](data/DMPs.schema.json) — 32 fields, primary key
  `issue_key`, foreign key `related_erb → ERBs.issue_key`.
- [`data/ERBs.schema.json`](data/ERBs.schema.json) — 20 fields, primary key
  `issue_key`, foreign key `related_dmp → DMPs.issue_key`.
- [`datapackage.json`](datapackage.json) — a Data Package that binds both
  resources so the cross-resource foreign keys can be validated.

> Note: 12 foreign-key references point to records created before the
> 2025-09-01 cutoff and are therefore absent from the export — an expected
> artifact of the reporting-period filter, not a schema error.

## Reference documents

Available under the navbar **Reference** menu:

- [`research-questions.md`](research-questions.md) — the 17 research questions
  (A: Compliance, B: Lifecycle, C: Survey, D: Communication & Training).
- [`metrics.md`](metrics.md) — metrics per question. Q1–Q10 are answerable
  from the DMP/ERB datasets; Q11–Q17 require survey, training, and
  communication data not yet available.
- [`queries.md`](queries.md) — the source SQL queries behind the exports.

## Project structure

```
rdm-dash/
├── _quarto.yml                 # Site config: navbar (Home, Departments, Reference, About), theme, code hidden
├── index.qmd                   # Overview dashboard
├── _dept-content.qmd            # Shared department dashboard body
├── dept-*.qmd                   # 9 per-department dashboards
├── _helpers.py                  # Data loading + metric functions
├── styles.css                   # Custom CSS overrides
├── research-questions.md        # 17 research questions
├── metrics.md                   # Metrics per question
├── queries.md                   # Source SQL queries
├── datapackage.json             # Frictionless Data Package (both resources)
├── data/                        # Source CSVs + Table Schemas (all tracked)
│   ├── DMPs_2025_09_10_onwards.csv
│   ├── ERBs_2025_09_10_onwards.csv
│   ├── DMPs.schema.json
│   └── ERBs.schema.json
├── Pipfile                      # Python deps: pandas, plotly (+ frictionless dev)
├── Pipfile.lock
├── LICENSE
├── _site/                       # Built output (gitignored)
├── .quarto/                     # Quarto cache (gitignored)
└── .venv/                       # Python virtualenv (gitignored)
```

## Troubleshooting

**`BadResource: Bad resource ID`** during preview. This is a recurring Quarto
bug where the Deno Sass KV cache corrupts during live-preview rebuilds. Fix:

```bash
pkill -9 -f "quarto preview"
rm -rf ~/Library/Caches/quarto/sass .quarto
```

Then restart `pipenv run quarto preview`.

## License

This project is licensed under the [MIT License](LICENSE).
© 2026 Eindhoven University of Technology.
