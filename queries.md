# Data Queries

SQL queries used to generate the DMP and ERB data files in `data/`.

Source table: `rdi_tst.cockpit` (TU/e Research Cockpit gold fact tables).

## DMPs

```sql
SELECT * EXCEPT(reporter_email)
FROM
  rdi_tst.cockpit.dmp_gold_fact_dedup
WHERE
  issue_creation_time >= '2025-09-01'
```

## ERBs

```sql
SELECT * EXCEPT(reporter_email)
FROM
  rdi_tst.cockpit.erb_gold_fact_dedup
WHERE
  issue_creation_time >= '2025-09-01'
```
