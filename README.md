# rdm-dash

A dashboard about Research Data Management (RDM), built with [Quarto](https://quarto.org).
Authored by Nami Sunami and Liz Guzman-Ramirez, TU/e Data Stewards.

## Prerequisites

- [Quarto](https://quarto.org/docs/get-started/) ≥ 1.9
- [Pipenv](https://pipenv.pyp.org/) for managing the Python environment
- Python 3.14 (declared in the `Pipfile`)

## Setup

Clone the repository and install the Python environment:

```bash
git clone <repo-url> rdm-dash
cd rdm-dash
pipenv install --dev
```

This creates a `.venv/` with the dependencies pinned in `Pipfile.lock`.

## Preview the site

Render and serve the site locally with live reload:

```bash
quarto preview
```

By default the site is available at <http://localhost:8080>. Changes to `.qmd`
files, `_quarto.yml`, or `styles.css` trigger an automatic rebuild.

To render the site once without serving:

```bash
quarto render
```

Output is written to `_site/`.

## Project structure

```
rdm-dash/
├── _quarto.yml     # Site config: type, navbar, theme (cosmo + brand), TOC
├── index.qmd       # Home page
├── about.qmd       # About page
├── styles.css      # Custom CSS overrides
├── Pipfile         # Python dependencies (currently empty)
├── Pipfile.lock    # Locked dependency versions
├── LICENSE
├── _site/          # Built output (gitignored)
├── .quarto/        # Quarto cache (gitignored)
└── .venv/          # Python virtualenv (gitignored)
```

## Configuration

Site-wide options live in `_quarto.yml`. The navbar currently exposes two
pages — **Home** (`index.qmd`) and **About** (`about.qmd`). To add a new page,
create a `.qmd` file and reference it under `website.navbar.left`.

## License

This project is licensed under the [MIT License](LICENSE). © 2026 Eindhoven University of Technology.
