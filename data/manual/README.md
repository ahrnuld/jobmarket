# Manual statistics

Figures from sources we cannot fetch automatically (yet) live here as CSV files, one file per
source: `data/manual/<source_id>.csv`. `jobmarket stats` checks every row and rejects a whole file
if any row is wrong, so a typo never reaches the site. Removing a file removes that source's
figures from the site on the next run.

## Current file: `studiekeuze123.csv`

Labour market outcomes per programme from the Studiekeuzedatabase of the Landelijk Centrum
Studiekeuze (LCSK), copied from the national study pages on Studiekeuze123 on 2026-09-19:

| Programme | Studiekeuze123 page |
| --- | --- |
| Informatica | https://www.studiekeuze123.nl/studies/34479-informatica-hbo-bachelor |
| Technische Informatica | https://www.studiekeuze123.nl/studies/34475-technische-informatica-hbo-bachelor |
| Business IT & Management | https://www.studiekeuze123.nl/studies/39118-business-it-management-hbo-bachelor |

Each series names its underlying source in `data/reference/statistics.yaml` (`origin`): the
estimated starting salary, contracts, working hours and time to a job come from CBS Microdata;
work at level, work in field and occupations from the HBO-Monitor; the outlook from ROA.

Things to know:

- The figures are national, for full-time graduates, and computed per group of related
  programmes: Informatica and Technische Informatica share the same figures. The site says so.
- Studiekeuze123 does not state the measurement year or the number of respondents. `period` is
  the year consulted (the outlook's period is its horizon, 2028), `published_at` the date consulted.
- To update: check the three pages again (Studiekeuze123 publishes new figures during the year),
  change the values, `period` and `published_at`. Once LCSK gives database access, an import can
  replace this file.
- LCSK asks to be named clearly as the source; the site does this under every figure.

## Columns

| Column | Meaning |
| --- | --- |
| `source_id` | The file's source (`studiekeuze123`) |
| `series_id` | A manual series from `statistics.yaml`, e.g. `sk_starting_salary` |
| `period` | `2026` (year), `2026Q3` (quarter) or `2025-2030` (range) |
| `region` | `NL`, a province id or labour market region id from `regions.yaml` |
| `breakdown` | Programme id (`informatica`, `business-it-management`, `technische-informatica`); `hbo-bachelor` for the national average of all hbo bachelors; for `sk_occupation`: `<programme id>/<occupation>` |
| `value` | Number (decimal point or comma); empty for series with unit `label` |
| `value_label` | Text for series with unit `label`, e.g. ROA's "minder goed", copied exactly |
| `unit` | Must equal the series unit in `statistics.yaml` |
| `sample_size` | Number of respondents, when the source gives it (TR-02) |
| `published_at` | Date the source published the figure, or the date consulted (YYYY-MM-DD) |
| `source_url` | Link to the exact page (TR-01) |
| `is_sample` | `0` for real figures. Rows with `1` are placeholders and are never published |
| `note` | Remark shown in the data download |

A row whose `source_id` starts with `#` is ignored.
