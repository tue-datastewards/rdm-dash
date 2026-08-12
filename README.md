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

The feedback survey data is also in `data/`:

```
data/feedback-survey-responses.csv         # 74 responses, Apr–May 2026
data/feedback-survey-schema.json           # DDI-CDI survey schema (concepts, code lists, variables)
data/feedback-survey-dataset.jsonld        # Combined dataset: schema + coded responses
```

To regenerate the JSON-LD dataset from the CSV:

```bash
pipenv run python scripts/convert-feedback-to-cdi.py
```

The converter maps Likert labels, Yes/No, and star ratings to the schema's
code-list values, and attaches per-response start/completion timestamps.

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

- **`index.qmd`** — overview across all departments: KPI card grids with a
  department dropdown and per-purpose toggle.
- **`data-storage.qmd`** — storage, FAIR data adoption, repositories and
  archival, with a department dropdown.
- **`process-eval.qmd`** — process quality metrics (Q12–Q15).
- **`communication-training.qmd`** — outreach activities (Q16–Q17).
- **`about.qmd`** — credits.
- **`_helpers.py`** — data loading, cleaning, and all metric functions.

Each chart displays the research question (Q1–Q17) it answers as a blockquote
above the chart.

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

### Feedback survey data

The DMP feedback form responses are documented as a
[DDI-CDI](https://github.com/ddi-cdi/ddi-cdi) JSON-LD dataset. The conversion
preserves the survey schema (concepts, code lists, represented variables,
skip logic) and populates it with coded responses:

- [`data/feedback-survey-responses.csv`](data/feedback-survey-responses.csv) —
  raw responses (74 rows × 9 columns, collected Apr–May 2026)
- [`data/feedback-survey-schema.json`](data/feedback-survey-schema.json) —
  DDI-CDI survey schema with 6 concepts, 3 code lists, 6 represented
  variables, 7 instance variables, and conditional skip logic
- [`data/feedback-survey-dataset.jsonld`](data/feedback-survey-dataset.jsonld) —
  combined dataset: schema + 74 coded data points with timestamps

To regenerate after updating the CSV:

```bash
pipenv run python scripts/convert-feedback-to-cdi.py
```

The converter maps Likert labels, Yes/No, and star ratings to code-list
values, and attaches per-response `startTime` and `completionTime`.

To validate the generated dataset (types, predicates, referential integrity,
skip logic, timestamps, and cross-checks against the CSV):

```bash
pipenv run python scripts/validate-feedback-dataset.py
```

## Reference documents

Available under the navbar **More Info** menu:

- [`queries.md`](queries.md) — the source SQL queries behind the exports.

## Project structure

```
rdm-dash/
├── _quarto.yml                 # Site config: navbar, theme, code hidden
├── index.qmd                   # Overview dashboard
├── data-storage.qmd            # Storage, repositories & archival
├── process-eval.qmd            # Process quality metrics
├── communication-training.qmd  # Outreach activities
├── about.qmd                   # Credits
├── _helpers.py                 # Data loading + metric functions
├── styles.css                  # Custom CSS overrides
├── queries.md                  # Source SQL queries
├── datapackage.json            # Frictionless Data Package (both resources)
├── scripts/
│   ├── convert-feedback-to-cdi.py    # CSV + DDI-CDI schema → JSON-LD dataset
│   └── validate-feedback-dataset.py  # JSON-LD + CSV validator
├── data/                       # Source data (all tracked)
│   ├── DMPs_2025_09_10_onwards.csv
│   ├── ERBs_2025_09_10_onwards.csv
│   ├── DMPs.schema.json
│   ├── ERBs.schema.json
│   ├── feedback-survey-responses.csv
│   ├── feedback-survey-schema.json
│   └── feedback-survey-dataset.jsonld
├── Pipfile                     # Python deps: pandas, plotly (+ frictionless dev)
├── Pipfile.lock
├── LICENSE
├── _site/                      # Built output (gitignored)
├── .quarto/                    # Quarto cache (gitignored)
└── .venv/                      # Python virtualenv (gitignored)
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
