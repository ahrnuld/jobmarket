# Manual statistics

HBO-Monitor, ROA and UWV publish their figures as reports and web tables, not through an API.
Their figures are typed over into the CSV files in this folder. `jobmarket stats` checks every
row and rejects a whole file if any row is wrong, so a typo never reaches the site.

The rows in these files now are **examples** (`is_sample=1`, value "voorbeeld" or round numbers).
The site marks them as example data, and production mode refuses to publish them. Replace them
with real figures, set `is_sample` to `0`, and fill in the real `source_url`.

## Columns

| Column | Meaning |
| --- | --- |
| `source_id` | `hbo_monitor`, `roa` or `uwv` (must match the series, see `data/reference/statistics.yaml`) |
| `series_id` | One of the manual series in `statistics.yaml` |
| `period` | `2024` (year), `2024Q3` (quarter) or `2025-2030` (forecast horizon) |
| `region` | `NL`, a province id (`noord-holland`) or labour market region id (`groot-amsterdam`), from `regions.yaml` |
| `breakdown` | Programme id (`informatica`, `business-it-management`, `technische-informatica`) for per-programme series; otherwise free id such as `ict-occupations` |
| `value` | Number, for numeric series. Decimal point or comma |
| `value_label` | Text, for series with unit `label` (e.g. ROA "goed", UWV "zeer krap"), copied exactly as the source writes it |
| `unit` | Must equal the series unit in `statistics.yaml` |
| `sample_size` | Number of respondents behind the figure, when the source gives it (TR-02) |
| `published_at` | Date the source published the figure (YYYY-MM-DD) |
| `source_url` | Link to the exact page or report (TR-01) |
| `is_sample` | `1` for example rows, `0` for real figures |
| `note` | Optional remark, e.g. "CROHO 34479, landelijk gemiddelde" |

A row whose `source_id` starts with `#` is ignored, so you can comment rows out.

## Where to find the figures

Verify these routes before relying on them; publication formats change.

- **HBO-Monitor** (`hbo_starting_salary`, `hbo_job_match`): the HBO-Monitor is published by the
  Vereniging Hogescholen and ROA. Per-programme outcomes (starting salary, work at bachelor level)
  are also shown on Studiekeuze123 per programme. Record the national figure per programme; if
  you use an institution's own figure, say so in `note`.
- **ROA** (`roa_outlook`): ROA's labour market forecasts per education type ("De arbeidsmarkt naar
  opleiding en beroep") on roa.nl. Copy the outlook label for the matching HBO education type and
  the forecast horizon as `period`.
- **UWV** (`uwv_tension`): UWV's labour market tightness indicator per occupation class and region
  on werk.nl (arbeidsmarktinformatie). Copy the label for ICT occupations per quarter.

Aim for at least five years of history per series (DR-09).
