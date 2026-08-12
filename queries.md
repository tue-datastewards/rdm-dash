# Data Queries

SQL queries used to generate the DMP and ERB data files in `data/`.

Source table: `rdi_tst.cockpit` (TU/e Research Cockpit gold fact tables).

The `SELECT` lists below are limited to the columns the dashboard actually
consumes (see `_helpers.py` and the `.qmd` pages).
`reporter_email` and every other unused field are omitted so the exports
stay lean.

## DMPs

```sql
SELECT
  issue_key,
  issue_creation_time,
  is_approved,
  status_history,
  ordered_status_transition_list,
  tue_department,
  data_storage_list,
  storage_solution_count,
  data_repository,
  metadata_standard,
  processing_tools_list,
  has_related_erb,
  is_scientific,
  has_special_category,
  data_sharing,
  archive_location,
  days_to_first_submission,
  days_to_first_response,
  days_to_first_approval
FROM
  rdi_tst.cockpit.dmp_gold_fact_dedup
WHERE
  issue_creation_time >= '2025-09-01'
```

### Columns used by

| Column                           | Metric / function                                                 |
| -------------------------------- | ----------------------------------------------------------------- |
| `issue_key`                      | not currently consumed (primary key)                            |
| `issue_creation_time`            | Reporting-period filter; `kpi_html` date range                   |
| `is_approved`                    | `kpi_table`, `approval_by_department` (Q1)                       |
| `status_history`                 | Q9 fallback only (pre-computed column preferred)                |
| `ordered_status_transition_list` | `process_kpi_html` (revision requested rate)                    |
| `tue_department`                 | `filter_department`                                             |
| `data_storage_list`              | `storage_split` (Q3)                                            |
| `data_repository`                | `kpi_table`, `repository_breakdown` (Q5)                        |
| `metadata_standard`              | `process_kpi_html` (help rate)                                  |
| `processing_tools_list`          | `process_kpi_html` (help rate)                                  |
| `has_related_erb`                | `kpi_table` (Q2 linkage)                                        |
| `is_scientific`                  | `filter_by_purpose`, `dmps_by_department_purpose`               |
| `has_special_category`           | not currently consumed                                          |
| `data_sharing`                   | `kpi_table` (Q4)                                                |
| `archive_location`               | `kpi_table`, `archive_split` (Q6)                               |
| `days_to_first_submission`       | not currently consumed                                          |
| `days_to_first_response`         | `first_response_time` (Q9)                                      |
| `days_to_first_approval`         | reserved; not currently consumed                                |

### Columns excluded

`issue_title`, `latest_status_time`,
`data_volume_list`, `data_volume_tb`, `has_data_volume_info`,
`data_storage_after_list`, `has_data_storage_info`,
`processing_tools_count`, `processing_tools_info`, `related_erb`,
`erb_link_creation_date`, `days_to_erb_link_creation`, `ever_approved`,
`approval_count`, `gold_processed_at`, `reporter_email`.

## ERBs

```sql
SELECT
  issue_key,
  issue_creation_time,
  related_dmp,
  is_approved,
  ordered_status_transition_list
FROM
  rdi_tst.cockpit.erb_gold_fact_dedup
WHERE
  issue_creation_time >= '2025-09-01'
```

### Columns used by

| Column                           | Metric / function                                    |
| -------------------------------- | ---------------------------------------------------- |
| `issue_key`                      | Primary key; ERB ticket identifier                   |
| `issue_creation_time`            | Reporting-period filter (`>= '2025-09-01'`)          |
| `related_dmp`                    | not currently consumed                                        |
| `is_approved`                    | not currently consumed                                        |
| `ordered_status_transition_list` | not currently consumed                                        |

### Columns excluded

`issue_title`, `latest_status_time`,
`status_history`, `days_to_first_approval`, `tue_department`,
`dmp_link_creation_date`, `has_related_dmp`, `days_to_dmp_link_creation`,
`ever_approved`, `approval_count`, `gold_processed_at`, `is_scientific`,
`has_special_category`, `data_sharing`, `archive_location`, `reporter_email`.
