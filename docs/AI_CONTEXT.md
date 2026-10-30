# AI context: CRDC cleaned school data (team file, all years)

How to use this file: copy everything below the line and paste it into your AI
assistant (any chat assistant or coding agent) at the start of a conversation. If you
are working with one specific school year, also paste that year's details file
(see section 2). Then ask your question.

---

You are helping a member of a student data team. The text below gives you the context
you need. Read sections 0 to 2 first.

## 0. Scope: read this first

- The team cleans four school years separately: 2015-16, 2017-18, 2020-21 and
  2021-22. Each year has its own owner, its own raw files and its own quirks.
- This file describes only what is shared by every year: the team's output format and
  rules. It contains no counts or caveats for any specific year; the two places that
  use a 2017-18 example (the seclusion wording and the FIPS rule) say so.
- Year-specific details (counts, missing-data codes, caveats) are in a separate file for
  each year (section 2). Never apply one year's details to another year.
- If you are not sure which year the user is working on, ask before answering.

## 1. Rules for you, the AI assistant

1. A blank cell (NA) means "unknown". Never treat it as zero, and never fill it in unless
   the user explicitly asks for imputation and understands what it means.
2. Always read `combokey`, `leaid` and `schid` as text, never as numbers.
3. Seclusion values count incidents, not students.
4. Results from this data show associations, not causes.
5. Flags mark values for review. A flag does not mean a value was changed or should be
   removed.
6. Do not invent numbers, definitions or column names. If the answer is not in this
   context, say so and point the user to that year's quality report
   (`docs/cleaning/qa_{year}.md`) or column mapping (`docs/cleaning/mapping_{year}.csv`).
7. If you can see or edit the team repository (coding agent): do not change another
   year's files unless the user explicitly asks.
8. When writing code, use Python with pandas and the loading code in section A6.

## 2. Year-specific context files

Each year has its own details: counts, missing-data codes and caveats. When the user is
working with one year, ask them to paste that year's details file too.

| Year | Details file | Status |
|---|---|---|
| 2015-16 | not added yet | - |
| 2017-18 | `docs/cleaning/README_201718.md` (key numbers, codes, caveats); full report in `docs/cleaning/qa_201718.md` | Available |
| 2020-21 | not added yet | - |
| 2021-22 | not added yet | - |

Year owners: when you add your year's details file, update its row in this table. If a
year has no details file yet, rely on that year's quality report instead.

## PART A. Shared team format (all years)


### A1. Project background

- Team project: understand how school resources (staffing, student mix, school type,
  district size) relate to the use of seclusion in U.S. public schools.
- Source: the U.S. Department of Education's Civil Rights Data Collection (CRDC),
  public-use files.
- Seclusion: confining a student alone in a room or area that the student is physically
  prevented from leaving (wording from the 2017-18 CRDC definitions; check each year's
  manual for its exact definition).
- The team's cleaning rules are in `cleaning_feature_playbook.md` (team PR #20). Every
  year produces the same 50 output columns, so the years can be stacked later.

### A2. Files each year produces

`{year}` is one of `201516`, `201718`, `202021`, `202122`.

| File | What it is |
|---|---|
| `schools_{year}.csv` | Main file. One row per school, every school included, 50 columns. |
| `schools_{year}_analysis.csv` | Same columns, only rows where `flag_analysis_ready == True`. |
| `quality_detail_{year}.csv` | Problem log, one row per issue found. Not for analysis. |
| `notebooks/clean_{year}.ipynb` or `scripts/clean_{year}.py` | The cleaning code. |
| `docs/cleaning/qa_{year}.md` | That year's quality report. |
| `docs/cleaning/mapping_{year}.csv` | That year's raw-to-output column mapping. |

The CSVs are kept in the team's shared data folder, not in git. They use an empty cell
for NA and `True`/`False` for flags.

### A3. Keys

- One row = one school. The key is `combokey` (12 characters) = `leaid` (7 characters,
  the district) + `schid` (5 characters, the school within the district).
- In the 2017-18 files, the first 2 characters of `leaid` are the state FIPS code (for
  example `06` = California). Check this for other years.
- The `year` column holds the hyphenated label (for example "2017-18"). When combining
  years, identify each row by the pair (`year`, `combokey`).

### A4. The 50 columns (in file order)

Types: IDs and names are text; Yes/No columns hold the text "Yes" or "No"; counts, FTEs,
rates and percentages are decimal numbers (nullable float, per the playbook); flags are
True/False.

| Column | Meaning |
|---|---|
| `year` | The school year label, the same on every row of a file. |
| `combokey` | School ID (12 characters, text). |
| `leaid` | District ID (7 characters, text). |
| `schid` | School number within the district (5 characters, text). |
| `lea_state` | Two-letter state code. |
| `sch_name` | School name as reported. |
| `lea_name` | District name as reported in the district file. |
| `jj` | "Yes" if the school is in a juvenile justice facility (check that year's manual for the exact definition). |
| `seclusion_instances_wodis` | Seclusion incidents involving students without disabilities. |
| `seclusion_instances_idea` | Seclusion incidents involving students with disabilities served under IDEA (students with an IEP). |
| `seclusion_instances_504` | Seclusion incidents involving students with disabilities served only under Section 504. |
| `seclusion_instances` | Sum of the three groups above. NA if any of the three is NA. |
| `enrollment_total` | Total students: male + female (+ nonbinary in 2021-22 when valid). NA if a required part is missing. |
| `enr_nonbinary` | Nonbinary student count where the year collected it (2021-22); NA otherwise. |
| `enr_idea` | Students served under IDEA. |
| `enr_504` | Students served only under Section 504. |
| `enr_el` | English learners. |
| `seclusion_rate` | 100 * seclusion_instances / enrollment_total: incidents per 100 students. Can exceed 100. NA if the total is NA or enrollment is not above 0. |
| `sch_status_sped` | "Yes" for a special-education school. |
| `sch_status_charter` | "Yes" for a charter school. |
| `sch_status_alt` | "Yes" for an alternative school. |
| `sch_status_magnet` | "Yes" for a magnet school. |
| `sch_virt_ind` | Virtual-school indicator where the year collected it; NA otherwise. |
| `grade_band` | elementary (only grades K-5), middle (only 6-8), high (only 9-12), span (two or three of those groups), other (no K-12 grade, e.g. preschool-only or ungraded-only), NA if a grade flag is unknown. |
| `fte_teachers` | Teacher full-time equivalents (1.0 = one full-time person). |
| `fte_counselors` | School counselor FTE. |
| `fte_nurses` | Nurse FTE. |
| `fte_psych` | Psychologist FTE. |
| `fte_social` | Social worker FTE. |
| `fte_leo` | Sworn law enforcement officer FTE. |
| `fte_guards` | Security guard FTE. |
| `counselors_per_100` | 100 * fte_counselors / enrollment_total. |
| `teachers_per_100` | 100 * fte_teachers / enrollment_total. |
| `support_fte_per_100` | 100 * (fte_nurses + fte_psych + fte_social) / enrollment_total. NA unless all three are valid. Counselors are not included. |
| `pct_idea` | 100 * enr_idea / enrollment_total. NA if the subgroup is larger than the total. |
| `pct_504` | 100 * enr_504 / enrollment_total. NA if the subgroup is larger than the total. |
| `pct_el` | 100 * enr_el / enrollment_total. NA if the subgroup is larger than the total. |
| `lea_enrollment` | District enrollment from the district file. |
| `lea_schools` | Number of schools in the district, as reported. |
| `flag_missing_seclusion` | True if `seclusion_instances` is NA. |
| `flag_missing_enrollment` | True if `enrollment_total` is NA or not above 0. |
| `flag_small_enrollment` | True if enrollment is under 10; False when enrollment is missing. A reminder to check, not an error. |
| `flag_fte_outlier` | True if at least one staffing value was flagged for review. Values are unchanged; the reasons are in the problem log. |
| `flag_partial_enrollment`, `flag_partial_idea`, `flag_partial_504`, `flag_partial_el` | True only in 2021-22, when the nonbinary part of that count is unavailable. Always False in other years. |
| `flag_missing_module` | True if the school is missing from one of the required raw tables. |
| `flag_missing_lea` | True if the school's district is missing from the district file. |
| `flag_analysis_ready` | True if the seclusion total is valid and enrollment is above 0. Other columns may still be NA. |

### A5. The problem log (`quality_detail_{year}.csv`)

Columns: `year, source_file, source_row, combokey, leaid, raw_column, raw_value, issue,
action, cleaned_value, evidence`. Each row is one issue found during cleaning; the
`evidence` column explains it.

### A6. How to load a year's files

```python
import pandas as pd

year = "201718"   # or "201516", "202021", "202122"
ids = {"combokey": str, "leaid": str, "schid": str}
schools = pd.read_csv(f"schools_{year}.csv", dtype=ids, float_precision="round_trip")
```

`float_precision="round_trip"` reads every number exactly as written.

### A7. Guidance for analysis and modeling (from the team playbook)

- Do not use the outcome, or the columns used to build it, as model inputs:
  `seclusion_rate`, `seclusion_instances`, the three `seclusion_instances_*` columns,
  `flag_missing_seclusion` and `flag_analysis_ready`. `enrollment_total` is the rate's
  denominator; whether it may be used as a predictor is a team decision.
- Keep `seclusion_rate` as a number. Any "high seclusion" cutoff is a later team decision.
- Filling missing values, scaling, capping and removing rows are later team decisions;
  the cleaning did none of them.
- Do not add `pct_idea`, `pct_504` and `pct_el` together as if they covered separate
  groups of all students.
- Before comparing years, check that definitions, geography (Puerto Rico), reporting
  periods and enrollment totals match. The playbook suggests starting modeling with 2021-22.
