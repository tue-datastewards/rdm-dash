# Metrics

Concrete metrics for each answerable research question, computed from the
DMP dataset (`data/DMPs_2025_09_10_onwards.csv`) and ERB dataset
(`data/ERBs_2025_09_10_onwards.csv`).

## Key Performance Indicators (KPIs)

1. Total Submitted Data Management Plans (DMPs)
2. Proportion of approved DMPs
3. Proportion of DMPs that require an ERB
4. Percentage of DMPs that needed data sharing agreement
5. Percentage of DMPs with safe, TU/e storage solutions
6. Percentage of DMPs with FAIR data practices - indicating that data will be deposited in a trusted data repository (e.g., Zenodo or 4TU.ResearchData)
7. Percentage of DMPs where the researcher archives data at RAPS (TU/e archive)

## Questions

### Q1 — Approved DMP per department

**Status:** Fully answerable

**Sources:** DMP (`is_approved`, `tue_department`, `is_scientific`)

- **Overall approval rate** — # approved DMPs / total DMPs
- **Approval rate per department** — grouped by `tue_department`
- **Approval rate by purpose** — scientific vs. educational (`is_scientific`)

### Q2 — ERB approval

**Status:** Fully answerable

**Sources:** DMP (`has_related_erb`, `related_erb`, `erb_link_creation_date`, `days_to_erb_link_creation`, `has_special_category`) + ERB (`is_approved`, `related_dmp`, `status_history`)

- **ERB linkage rate** — % of DMPs with a linked ERB (`has_related_erb = true`)
- **ERB approval rate** — % of linked ERBs that are approved (ERB `is_approved = true`)
- **ERB decision breakdown** — Approved / Conditional approval / Rejected (from ERB `status_history`)
- **ERB approval rate per department** (join ERB → DMP → department)
- **Integration timing** — `days_to_erb_link_creation` / `days_to_dmp_link_creation`

### Q3 — TU/e secured storage + sensitive data outside TU/e

**Status:** Partially answerable

**Sources:** DMP (`data_storage_list`, `data_storage_after_list`, `has_special_category`)

- **TU/e-supported storage rate** — % using TU/e Network Drive / SharePoint-Teams / SURF Research Drive
- **External storage rate** — % "Other..."
- **Sensitive-data-outside-TU/e rate** — `has_special_category = true` × external storage solution

### Q4 — Data sharing agreement / DA request / DPIA

**Status:** Partially answerable

**Sources:** DMP (`data_sharing`, `has_special_category`)

- **Data-sharing rate** — % with `data_sharing` ≠ "no" (inside_eea / outside_eea)
- **Outside-EEA sharing rate** — proxy for agreement necessity
- **Special-category rate** — `has_special_category = true` (proxy for DPIA relevance)
- **Cross-metric** — special-category × outside-EEA sharing (proxy for DA-request likelihood)

### Q5 — FAIR data publication in trusted repository

**Status:** Fully answerable

**Sources:** DMP (`data_repository`)

- **Repository selection rate** — % of DMPs with a non-empty `data_repository`
- **Trusted-repository rate** — % selecting a trusted repo (4TU.ResearchData, Zenodo) vs. "Other..." vs. "I need advice"
- **Repository choice breakdown** — counts per repository
- **"I need advice" rate** — indicates need for FAIR support
- Per purpose and per department

### Q6 — Archive at TU/e archive (RAPS)

**Status:** Fully answerable

**Sources:** DMP (`archive_location`)

- **RAPS archival rate** — % with `archive_location = tue_archive`
- **Other-archive rate** — `other` / `other_archive`
- **No-archive rate** — `null`
- Per purpose and per department

### Q7 — Revision frequency

**Status:** Fully answerable

**Sources:** DMP (`ordered_status_transition_list`, `status_history`)

- **% of DMPs with ≥1 "Revision requested" transition**
- **Average revision rounds per DMP** — count of "Revision requested" occurrences
- **Revision count distribution** (0, 1, 2, 3+)
- Per department and per purpose

### Q8 — Time DRAFT → SUBMITTED

**Status:** Partially answerable

**Sources:** DMP (`status_history`, `issue_creation_time`)

- **days_to_first_submission** — computed from first "Submitted" timestamp − `issue_creation_time`
- **Distribution** — median, mean, quartiles
- Per department
- ⚠️ _Caveat:_ not pre-computed; must derive from `status_history` timestamps

### Q9 — First response time after submission

**Status:** Partially answerable

**Sources:** DMP (`status_history`)

- **days_to_first_response** — first status transition after "Submitted" − "Submitted" timestamp
- **Distribution** — median, mean, quartiles
- Per department
- ⚠️ _Caveat:_ not pre-computed; must define which transition counts as the Data Steward's response ("Revision requested"? "Revised (Positive advise)"?)

### Q10 — "I need help" during first submission

**Status:** Partially answerable

**Sources:** DMP (`data_repository`, `metadata_standard`, `processing_tools_list`)

- **"I need advice" rate per field** — % of DMPs containing "I need advice" in each of the three fields
- **Combined help-needed rate** — % of DMPs with "I need advice" in any field
- ⚠️ _Caveat:_ field-specific proxy; no dedicated help-request flag, and not tied specifically to "first submission"

---

## Cross-cutting dimensions

Most metrics can be sliced by:

- **Purpose** — `is_scientific` (scientific / educational / null)
- **Department** — `tue_department`
- **Time** — `issue_creation_time`, `latest_status_time`
