# Data cleaning notes (Task 3)

Reproducible cleaning for the CRDC school files, following [data_audit.md](data_audit.md). Field meanings: [data_dictionary.md](data_dictionary.md).

**Script:** `task2/scripts/clean_crdc.py`  
**Notebook:** `lia/notebooks/03_clean_crdc.ipynb`  
**Outputs:** `lia/data/processed/`  
**Conda env:** `capital-one-1a` (`lia/environment.yml`)  
Cleaning code and documentation live under `task2/`; datasets, processed outputs, and the notebook remain local under `lia/`.

Rerun from the notebook (recommended) or:

```bash
conda activate capital-one-1a
python3 task2/scripts/clean_crdc.py
```

Local API (after the processed CSV exists):

```bash
conda activate capital-one-1a
uvicorn backend.main:app --reload --app-dir lia
```

When reading the CSVs, always pass ID columns as strings (`dtype={"combokey": str, "leaid": str, "schid": str}`). Pandas will otherwise drop leading zeros.

---

## What was cleaned

Priority modules were merged into **one school-level row per `combokey` per year**:

- School Characteristics
- Enrollment
- Restraint and Seclusion
- School Support
- LEA Characteristics (left-joined)
- COVID directional indicators (2020–21 and 2021–22 only)

2015–16 uses the wide school file plus the LEA file. Years are **not pooled as a modeling dataset**; `schools_all_years.csv` is stacked only for convenience and includes a `year` column.

---

## Preprocessing decisions

| Topic | Decision |
|---|---|
| Missing values | For count/FTE fields, every numeric value **&lt; 0** (CRDC reserved codes: `-9`, `-5`, `-11`, `-13`, etc.) → `NA`. **Not** filled with 0. True zeros are kept. |
| Duplicates | No duplicate `combokey` after ID repair. Trailing blank source rows were dropped by the CSV reader. |
| Types | IDs as 0-padded strings; counts/FTEs as nullable floats; Yes/No flags standardized to `Yes`/`No`. |
| Column names | snake_case analysis names (`seclusion_instances`, `enrollment_total`, …). |
| Categorical values | `Yes`/`No` only; blanks and reserved codes on flags → `NA`. English-learner counts from `EL` (2021–22) or `LEP` (earlier years) into `enr_el`. |
| Identifiers | `leaid` width 7, `schid` width 5, `combokey` width 12. 2015–16 `combokey` **rebuilt** from padded LEA+SCH (Excel/scientific-notation source column discarded). 2017–18 restraint `schid` **ignored**; school id taken from Characteristics (`01705`, not `01017`). |
| Joins | Inner join of school modules on `combokey`; left join LEA on `leaid`. Within-year school modules matched 1:1. |
| Outliers | Staff FTE above a cap set to `NA` and `flag_fte_outlier=True` (teachers &gt; 2000; counselors/nurses/psych/social/LEO/guards &gt; 200). This catches the 2017–18 102,579-guard and 19,048-psych errors. |
| Seclusion total | `wodis + idea + 504` **only if all three are non-missing**. Otherwise `seclusion_instances` is `NA` (`flag_missing_seclusion`). Student-count seclusion fields kept separately and **not** added into the instance total. |
| Rate | `100 * seclusion_instances / enrollment_total` when enrollment &gt; 0 and instances are non-missing. Nonbinary `enr_nonbinary` is added to the denominator **only when reported** (≥ 0); it is not required. |
| Rows kept | Full files keep every school plus flags. `*_analysis.csv` keeps `flag_analysis_ready` rows (valid seclusion **and** valid enrollment &gt; 0). Justice-facility and tiny schools are **not** dropped; use `jj` and `flag_small_enrollment` (`enrollment_total` &lt; 10). |
| Discipline leak | Suspensions, offenses, referrals, etc. were **not** merged. |

Reserved-code definitions were checked against the source manuals: [2015–16 and 2017–18 code table](data_dictionary.md#reserved-codes-all-numeric-fields). `-9` means **Not Applicable / Skipped**, and `-5` means **Action Plan**. The numeric cleaner already masked every negative code; correcting the labels does not change numeric outputs. Yes/No normalization accepts only recognized Yes/No strings, so all reserved codes become `NA` there too. Later-year code meanings require their own manuals.

---

## Outputs

| File | Contents |
|---|---|
| `schools_202122.csv` | All 2021–22 schools (main cohort), with flags |
| `schools_202122_analysis.csv` | 2021–22 rows ready for rates/EDA |
| `schools_202021.csv` / `_analysis.csv` | COVID year (many missing seclusion) |
| `schools_201718.csv` / `_analysis.csv` | Comparison year |
| `schools_201516.csv` / `_analysis.csv` | After ID repair |
| `schools_all_years.csv` | Stacked (harmonized names; still year-specific missingness) |
| `cleaning_validation.json` | Row counts and QA checks |

---

## Validation (pandas counts)

| Year | Rows in = rows out | Unique `combokey` | Analysis-ready | Missing seclusion | Missing enrollment | FTE outliers | Schools with seclusion &gt; 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021–22 | 98,010 | 98,010 | 93,094 | 4,905 | 1,886 | 1 | 6,600 |
| 2020–21 | 97,575 | 97,575 | 76,082 | 21,029 | 592 | 2 | 4,557 |
| 2017–18 | 97,632 | 97,632 | 91,013 | 6,619 | 11 | 10 | 5,975 |
| 2015–16 | 96,360 | 96,360 | 93,966 | 2,394 | 1 | 7 | 5,165 |

ID lengths passed for all years (12 / 7 / 5). Duplicate `combokey` = 0 after cleaning, including 2015–16 (was 9,213 colliding stored keys in the audit).

Median seclusion rate among analysis-ready schools is **0** every year (zero inflation). The max 2021–22 rate is huge because a few schools have large instance counts relative to enrollment — use `flag_small_enrollment` or cap rates in feature engineering.

---

## Recommended use for Task 4

1. Start with `schools_202122_analysis.csv`.
2. Filter or weight with `flag_small_enrollment` and `jj` as needed.
3. Do **not** train on `seclusion_instances_*` as features if the target is derived from them.
4. Treat 2020–21 as a robustness year only (`flag_missing_seclusion` is ~22% of schools).
5. If stacking years, keep `year` and remember `enr_el` is EL in 2021–22 and LEP in earlier years.

---

## Not done here (by design)

- Imputing missing seclusion or enrollment
- Dropping justice-facility or virtual schools
- Winsorizing seclusion rates (Task 4)
- Merging discipline, expenditures, or EDFacts files
- Building the elevated-rate label (90th-percentile cutoff is still a proposal)
