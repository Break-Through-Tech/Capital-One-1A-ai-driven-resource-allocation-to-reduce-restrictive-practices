# CRDC data audit (Task 2)

Handoff for **data cleaning**. Counts below were measured from the local public-use CSVs for the four requested Civil Rights Data Collection (CRDC) years. Large CSVs are **not** stored in git; download them from [Data.gov — Civil Rights Data Collection](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc) and keep year-specific manuals next to the files.

**Suggested main cohort:** 2021–22 school-level CRDC. 2020–21 is a COVID collection with heavy reserved-code missingness on seclusion. 2017–18 is the best earlier comparison year. 2015–16 is usable only after repairing Excel-corrupted IDs.

---

## 1. Source

| Item | Detail |
|---|---|
| Collection | U.S. Department of Education, Office for Civil Rights (OCR), Civil Rights Data Collection |
| Access | [Data.gov CRDC dataset](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc) → landing page → downloadable public-use files |
| Format | CSV (plus PDF/XLSX manuals in some year packages) |
| Unit | School (`COMBOKEY`) and district / LEA (`LEAID`) |
| Documentation | Year-specific CRDC public-use file manuals, data definitions, and restraint/seclusion reporting guidance on the [ED CRDC page](https://www.ed.gov/laws-and-policy/civil-rights-laws/civil-rights-data-collection-crdc/civil-rights-data) |

OCR notes that districts certify submissions, but known reporting gaps remain (missing modules, skip logic, suppression). Treat this as **observational, school-reported** data.

---

## 2. What we have

Four collections are present locally (125 CSVs plus manuals):

| School year | Package name (as downloaded) | Structure | Pandas school rows | Pandas LEA rows | Geography |
|---|---|---|---:|---:|---|
| 2015–16 | `2015-16-crdc-data` (updated Sept 2018) | One wide school file (1,836 cols) + one LEA file | 96,360 | 17,337 | 51 (states + DC; **no PR**) |
| 2017–18 | `2017-18-crdc-data-corrected-publication 2` | Split SCH/LEA CRDC modules + EDFacts extracts | 97,632 | 17,604 | 52 (adds **PR**) |
| 2020–21 | `2020-21-crdc-data` | Split CRDC SCH/LEA + one EDFacts absenteeism file | 97,575 | 17,821 | 52 |
| 2021–22 | `2021-22-crdc-data` | Split SCH/LEA CRDC modules | 98,010 | 17,704 | 52 |

`wc -l` on several files is 1 higher than pandas row counts (trailing newline). Use pandas/`csv` reader counts, not line counts.

**2015–16 modules** live as columns in `CRDC 2015-16 School Data.csv`. Later years ship the same topics as separate CSVs (Enrollment, Restraint and Seclusion, School Support, …).

**EDFacts files** (2017–18 ID 22 / ID 74 / ID 814; 2020–21 ID 814) are a different schema (`NCESLEAID`, `NCESSCH`) and often a different grain. They are optional for the core seclusion analysis.

Full file-level inventory is in the [appendix](#appendix-file-inventory).

---

## 3. Priority files (cleaner should start here)

Within-year school modules for 2017–18, 2020–21, and 2021–22 share the **same `COMBOKEY` set** (Enrollment, Restraint and Seclusion, School Characteristics, School Support). School `LEAID`s also match the LEA Characteristics file after reading IDs as strings.

| Year | Restraint & seclusion | Enrollment | School characteristics | School support | LEA characteristics |
|---|---:|---:|---:|---:|---:|
| 2021–22 | 98,010 × 131 | 98,010 × 233 | 98,010 × 34 | 98,010 × 19 | 17,704 × 40 |
| 2020–21 | 97,575 × 131 | 97,575 × 118 | 97,575 × 32 | 97,575 × 17 | 17,821 × 34 |
| 2017–18 | 97,632 × 131 | 97,632 × 123 | 97,632 × 32 | 97,632 × 22 | 17,604 × 53 |
| 2015–16 | (in wide school file) | same | same | same | 17,337 × 115 |

2021–22 justice-facility flag: `JJ` = Yes for 882 schools (matches `SCH_JUST_IND`). Virtual: `SCH_VIRT_IND` = Yes for 2,496 schools. Special-education schools: 1,809; charter: 7,721; alternative: 4,127; magnet: 4,027.

---

## 4. Join keys

### School-level (use this)

| Key | Meaning | How to use |
|---|---|---|
| **`COMBOKEY`** | 12-character `LEAID` (7) + `SCHID` (5) | **Primary school join key** within a year, and the intended key across years |
| `LEAID` | 7-digit NCES district ID | Join schools → LEA file; group / split by district |
| `SCHID` | 5-digit school ID **within LEA** (not unique nationally) | Never join on `SCHID` alone |
| `LEA_STATE` | State / territory abbreviation | Filter, stratification — not a unique key |
| `JJ` | Juvenile-justice facility (Yes/No) | Flag; 2021–22 also has `SCH_JUST_IND` |

**Always read IDs as strings.** Zero-pad: `LEAID` → 7, `SCHID` → 5, `COMBOKEY` → 12. Concatenation `LEAID.zfill(7) + SCHID.zfill(5)` equals `COMBOKEY` in 2021–22, 2020–21, and 2017–18 Enrollment / Characteristics / Support.

### Do not do these

1. **Do not join on `SCHID` from 2017–18 `Restraint and Seclusion.csv`.** `LEAID` and `SCH_NAME` match other modules, but `SCHID` is wrong on 97,630 / 97,632 rows (e.g. true `01705` stored as `01017`). **`COMBOKEY` is still correct** — join that file on `COMBOKEY` only.
2. **Do not trust 2015–16 `COMBOKEY` as stored.** Excel-style corruption: leading zeros dropped, and 78,034 rows have scientific-notation keys such as `1.20039E+11` (only 29,374 distinct stored values). **Rebuild** `COMBOKEY = LEAID.zfill(7) + SCHID.zfill(5)`. After that rebuild: 96,360 unique keys and a perfect school↔LEA `LEAID` match. Raw stored `COMBOKEY` overlap with later years is an artifact (~98 schools); do not use it for longitudinal joins.
3. **`SCHID` is reused across districts** (e.g. `99999` appears hundreds of times). National uniqueness requires `COMBOKEY`.
4. **EDFacts:** join via `NCESSCH` ↔ padded `COMBOKEY` / `NCESLEAID` ↔ `LEAID`, after checking coverage. Title I 2017–18 has 103,547 rows vs 97,632 CRDC schools.

### Cross-year `COMBOKEY` overlap (2017–18 onward; 2015–16 after ID repair still needs a separate check)

Stored (unrepaired) 2015–16 keys are not comparable. Among later years:

| Pair | Overlap | Only left | Only right |
|---|---:|---:|---:|
| 2021–22 ∩ 2020–21 | 96,061 | 1,949 | 1,514 |
| 2021–22 ∩ 2017–18 | 91,466 | 6,544 | 6,166 |
| 2020–21 ∩ 2017–18 | 92,399 | 5,176 | 5,233 |

Schools open, close, and re-ID over time. Do not assume a balanced panel.

---

## 5. Missing values and reserved codes

Pandas-null / blank cells are rare in these public-use files. **Missingness is stored as negative reserved codes.** Any value `< 0` is not a real count or FTE.

Codes observed in this audit (confirm definitions in the year manual before coding):

| Code | Where it showed up | Treat as |
|---|---|---|
| `-9` | Widespread; classic “not reported / missing” | Missing |
| `-5` | Skip / not applicable (e.g. module not asked) | Not applicable |
| `-3` | 2021–22 (small counts) | Reserved / NA |
| `-6` | 2017–18 seclusion and some FTE fields | Reserved / NA |
| `-11` | 2020–21 especially, also 2017–18 | Reserved / NA (COVID-year heavy) |
| `-12` | 2021–22 nonbinary enrollment (`TOT_ENR_X`) | Privacy suppression |
| `-13` | 2020–21 and 2021–22 seclusion instances | Reserved / NA |
| `-2` | 2015–16 IDEA enrollment (small-cell style) | Suppressed — not zero |

**Cleaning rule:** `pd.to_numeric` then set `value < 0` to NA. Do **not** fill reserved codes with 0. Zero means the school reported none.

### Seclusion *instances* (proposed target ingredients)

`SCH_RSINSTANCES_SECL_WODIS` + `SCH_RSINSTANCES_SECL_IDEA` + `SCH_RSINSTANCES_SECL_504`

These three categories are intended as a partition (no-disability / IDEA / 504-only). Verify skip logic before summing. Do not add overlapping student-count columns (`TOT_RS_*_SECL_*`) into the same total.

| Year | Rows | All three codes ≥ 0 | `-9` | Other negatives (WODIS) | Schools with WODIS instances > 0 | IDEA instances > 0 |
|---|---:|---:|---:|---|---:|---:|
| 2021–22 | 98,010 | 93,105 | 4,377 | `-13`: 353; `-5`: 172; `-3`: 3 | 2,423 | 5,697 |
| 2020–21 | 97,575 | 76,554 | 1,875 | **`-11`: 14,158**; `-13`: 4,700; `-5`: 288 | 1,327 | 4,037 |
| 2017–18 | 97,632 | 91,141 | 1,908 | `-6`: 3,089; `-11`: 1,203; `-5`: 291 | 2,062 | 5,504 |
| 2015–16 | 96,360 | 93,966 | 1,806 | `-5`: 588 | 1,876 | 4,489 |

2020–21: only **78%** of schools have a usable non-reserved instance count. That year should not be the primary modeling cohort.

Student-count seclusion fields (`TOT_RS_NONIDEA_SECL_*`, `TOT_RS_IDEA_SECL_*`) are **not** interchangeable with instances. In 2021–22 those student totals are `-9` for ~92–95k schools (filled mainly where instances exist). In 2017–18 / 2020–21 they are populated more like the instance fields (including the same reserved codes).

### Enrollment denominators

Proposed rate: `100 × (valid seclusion instances) / (TOT_ENR_M + TOT_ENR_F [+ TOT_ENR_X if valid])`.

| Year | `TOT_ENR_M` usable (≥ 0) | Notes |
|---|---:|---|
| 2021–22 | 96,138 | `-9` on 1,872 schools; `TOT_ENR_X` is mostly `-9` (92,805) or `-12` (2,850); only 2,354 schools have a positive nonbinary count. **Do not require `_X` in the denominator for every school.** |
| 2020–21 | ~97k with some `-11` mixed into “valid” if negatives are not stripped | Strip all `< 0` first |
| 2017–18 | 97,622 | 10 rows `-5` |
| 2015–16 | 96,359 | 1 row `-5` |

IDEA / 504 / EL-or-LEP enrollment are useful **composition features**, not the primary denominator, unless building a subgroup rate with a matching numerator.

### Staffing (School Support)

FTE fields (`SCH_FTECOUNSELORS`, `SCH_FTETEACH_TOT`, nurses / psychologists / social workers, security) are populated for most schools but still contain reserved negatives (`-3`, `-6`, `-9`, `-11`). Security FTE is `-9` for most justice-facility schools (882 in 2021–22).

---

## 6. Duplicates

| Check | Result |
|---|---|
| Duplicate `COMBOKEY` in 2021–22 / 2020–21 / 2017–18 CRDC school modules | **None** (after dropping trailing blank lines) |
| Duplicate `LEAID` in LEA Characteristics | **None** |
| Duplicate `COMBOKEY` as stored in 2015–16 | **Yes — 9,213 colliding keys, 76,199 rows** because of Excel/scientific notation. Goes to **zero** after rebuilding from padded `LEAID`+`SCHID` |
| Full-row duplicates on Characteristics / Support / LEA (files small enough to test) | **None** |
| `SCHID` duplicates | Expected (within-LEA ID) |

---

## 7. Year / reporting-period differences (do not pool blindly)

| Topic | Difference |
|---|---|
| File layout | 2015–16 = one wide school CSV; later years = one CSV per module |
| Geography | PR appears from 2017–18 onward |
| COVID | 2020–21 (and a 2021–22 COVID indicators file). Instruction often remote; seclusion reporting incomplete (`-11` / `-13`) |
| English learner naming | `*_LEP_*` through 2020–21; `*_EL_*` in 2021–22 |
| Nonbinary | `*_X` and `TOT_ENR_X` in 2021–22 enrollment only |
| Virtual / justice flags | `SCH_VIRT_IND`, `SCH_JUST_IND` in 2021–22 Characteristics; earlier years have `JJ` only |
| School Support extras | 2017–18 has teacher first-year / absent fields and `SCH_TEACHERS_*_TOT`; 2021–22 has `TOT_TEACHERS_CURR_M/F` |
| School expenditures | **2017–18 only** among these packages (`School Expenditures.csv`; also columns in 2015–16 wide file) |
| Internet / computer science / data science | Internet + CS from 2020–21; Data Science 2021–22 |
| Encoding | Most files UTF-8; **2015–16 data + 2017–18 School Characteristics** need `cp1252` / `latin-1` |

Variable **meanings** can still change even when names match. Re-read each year’s restraint/seclusion definitions before summing WODIS+IDEA+504.

---

## 8. Data quality issues for cleaning

Copy this list into the cleaning ticket:

1. **Reserved negatives are missingness, not counts.** Recode all `< 0` to NA. Do not impute 0.
2. **2021–22 seclusion instances:** 4,905 / 98,010 schools have a reserved code on the instance fields (`-9` dominant). Exclude from rates or model them as “unknown,” not zero.
3. **2020–21 seclusion is badly incomplete.** 14,158 schools coded `-11` on instance fields plus other reserved codes → only 76,554 usable. COVID directional indicators exist (`SCH_DIND_INSTRUCTIONTYPE`, `SCH_DIND_VIRTUALTYPE`) if that year is used at all.
4. **Zero inflation is real.** Among usable 2021–22 rows, WODIS instances are 0 for 90,682 schools and positive for 2,423. The elevated-rate class will be small; do not treat zeros as under-reporting without a separate missingness flag.
5. **Do not sum overlapping student seclusion counts** (race × sex × IDEA/non-IDEA). Use instance totals for the primary rate; keep student counts as a **secondary** outcome only with matching denominators.
6. **2015–16 IDs must be repaired** (string dtype, zfill, rebuild `COMBOKEY`). Otherwise joins and longitudinal matches are wrong.
7. **2017–18 Restraint `SCHID` is unusable**; join that module on `COMBOKEY`.
8. **Outliers / impossible FTEs in 2017–18 School Support:** `SCH_FTESECURITY_GUA` max **102,579** (DEL VALLE H S, `481662001424`); other campuses in the same LEA also have 20k–34k guards. `SCH_FTESERVICES_PSY` max **19,048.6** (Northshore Middle School). Winsorize or drop after review. 2015–16 counselor/nurse/psych maxima of **999** look like a cap/sentinel.
9. **Small denominators.** Median 2021–22 `TOT_ENR_M` ≈ 210; some schools have 0–few students. Rates per 100 students will explode; cap, Bayesian shrink, or exclude tiny enrollment.
10. **Justice facilities (JJ = Yes)** may follow different skip logic (security FTE `-9`, seclusion `-5`). Decide explicitly whether they stay in the analysis set.
11. **Encoding:** open 2015–16 CSVs and 2017–18 School Characteristics with `encoding="cp1252"` (or try UTF-8 then fall back).
12. **Same-year discipline files** (suspensions, offenses, referrals/arrests, corporal punishment) are likely **leaky** if used as predictors of seclusion. Audit before including.
13. **Do not pool years** until names (`LEP` vs `EL`), reserved-code sets, and seclusion definitions are harmonized. 2020–21 should stay a robustness year, not the training year.
14. **Local `data/` CSVs are untracked and large.** Cleaning should document the exact download package names above so teammates can reproduce.

---

## 9. Variables relevant to this project

Priority order for the analysis-ready school table:

**Must have**

- Keys: `COMBOKEY`, `LEAID`, `SCHID` (padded), `LEA_STATE`, `SCH_NAME`, `LEA_NAME`
- Outcome: seclusion **instances** `SCH_RSINSTANCES_SECL_WODIS`, `_IDEA`, `_504` → sum if all valid
- Denominator: `TOT_ENR_M`, `TOT_ENR_F` (optional valid `TOT_ENR_X` in 2021–22)
- School type: `SCH_STATUS_SPED`, `_CHARTER`, `_ALT`, `_MAGNET`, `JJ` / `SCH_JUST_IND`, `SCH_VIRT_IND` (2021–22), grade-span flags
- Staffing: `SCH_FTECOUNSELORS`, `SCH_FTETEACH_TOT`, `SCH_FTETEACH_CERT`, `SCH_FTESERVICES_NUR`, `_PSY`, `_SOC`
- Composition: IDEA, 504, EL/LEP enrollment counts (for shares, not for the main denominator)

**Useful**

- Security FTE (`SCH_FTESECURITY_LEO`, `_GUA`) as context, with outlier handling
- LEA size: `LEA_ENR`, `LEA_SCHOOLS`
- 2017–18 (and 2015–16) school expenditures, if comparing resources
- Secondary outcome: students subjected to seclusion (`TOT_RS_NONIDEA_SECL_*` + `TOT_RS_IDEA_SECL_*`) — different construct from incidents
- Mechanical / physical **restraint** instance fields — related restrictive practice, not the primary target

**Keep out of the core predictor set until reviewed**

- Other seclusion/restraint components (leakage if predicting seclusion)
- Suspensions, expulsions, referrals/arrests, offenses, corporal punishment
- Race/sex seclusion cells as features (use for equity **description**, not as model inputs)

See [data_dictionary.md](data_dictionary.md) for field definitions and year-name changes.

---

## 10. Recommended cleaning sequence

1. Read each priority CSV as strings; fix encoding; drop empty trailing rows.
2. Pad IDs; rebuild 2015–16 `COMBOKEY`; ignore 2017–18 restraint `SCHID`.
3. Inner-join 2021–22 Characteristics + Enrollment + Restraint + Support on `COMBOKEY`; left-join LEA on `LEAID`.
4. Recode reserved codes to NA; build instance sum and enrollment total; drop or flag rows missing either.
5. Flag JJ / virtual / special-education / tiny enrollment.
6. Repeat for 2017–18 as a comparison cohort; treat 2020–21 as COVID-sensitivity only; bring 2015–16 in after ID repair if needed.

---

## Method

Profiles used Python/pandas (`dtype=str`), with UTF-8 then `cp1252` fallback. Row counts in the appendix are `line count − 1` and may include a blank line; section 2 uses pandas counts. Numeric summaries treated only the listed reserved integers (`-9,-5,-2,-8,-3`) as codes at first pass; **additional negatives (`-6,-11,-12,-13`) were found afterward** and are documented in section 5. Cleaning must treat **all negatives** as reserved.

---

## Appendix: file inventory

Row counts are `wc`-style (header excluded) and may be 1 higher than pandas. `COMBOKEY` / `LEAID` mark identifier columns.

| Year | File | Rows | Cols | COMBOKEY | LEAID | Size (MB) |
|---|---|---:|---:|---|---|---:|
| 2015-16 | `CRDC 2015-16 LEA Data.csv` | 17,338 | 115 |  | Y | 11.5 |
| 2015-16 | `CRDC 2015-16 School Data.csv` | 96,360 | 1836 | Y | Y | 465.0 |
| 2017-18 | `Distance Education.csv` | 17,605 | 29 |  | Y | 2.8 |
| 2017-18 | `High School Equivalency (GED).csv` | 17,605 | 29 |  | Y | 2.8 |
| 2017-18 | `LEA Characteristics.csv` | 17,615 | 53 |  | Y | 8.6 |
| 2017-18 | `Advanced Mathematics.csv` | 97,632 | 30 | Y | Y | 16.4 |
| 2017-18 | `Advanced Placement.csv` | 97,632 | 134 | Y | Y | 47.1 |
| 2017-18 | `Algebra I.csv` | 97,632 | 136 | Y | Y | 46.0 |
| 2017-18 | `Algebra II.csv` | 97,632 | 30 | Y | Y | 16.4 |
| 2017-18 | `Biology.csv` | 97,632 | 30 | Y | Y | 16.4 |
| 2017-18 | `Calculus.csv` | 97,632 | 30 | Y | Y | 16.5 |
| 2017-18 | `Chemistry.csv` | 97,632 | 30 | Y | Y | 16.4 |
| 2017-18 | `Corporal Punishment.csv` | 97,632 | 71 | Y | Y | 28.8 |
| 2017-18 | `Credit Recovery.csv` | 97,632 | 10 | Y | Y | 11.1 |
| 2017-18 | `Dual Enrollment.csv` | 97,632 | 29 | Y | Y | 16.4 |
| 2017-18 | `Enrollment.csv` | 97,632 | 123 | Y | Y | 35.2 |
| 2017-18 | `Expulsions.csv` | 97,632 | 142 | Y | Y | 38.1 |
| 2017-18 | `Geometry.csv` | 97,632 | 32 | Y | Y | 17.2 |
| 2017-18 | `Gifted and Talented.csv` | 97,632 | 29 | Y | Y | 15.7 |
| 2017-18 | `Harassment and Bullying.csv` | 97,633 | 145 | Y | Y | 37.5 |
| 2017-18 | `International Baccalaureate.csv` | 97,632 | 29 | Y | Y | 16.6 |
| 2017-18 | `Justice Facilities.csv` | 97,633 | 16 | Y | Y | 12.8 |
| 2017-18 | `Offenses.csv` | 97,632 | 22 | Y | Y | 11.7 |
| 2017-18 | `Physics.csv` | 97,632 | 30 | Y | Y | 16.5 |
| 2017-18 | `Referrals and Arrests.csv` | 97,633 | 84 | Y | Y | 25.4 |
| 2017-18 | `Restraint and Seclusion.csv` | 97,633 | 131 | Y | Y | 35.4 |
| 2017-18 | `Retention.csv` | 97,632 | 307 | Y | Y | 97.4 |
| 2017-18 | `SAT and ACT.csv` | 97,632 | 28 | Y | Y | 15.7 |
| 2017-18 | `School Characteristics.csv` | 97,633 | 32 | Y | Y | 22.6 |
| 2017-18 | `School Expenditures.csv` | 97,633 | 27 | Y | Y | 25.3 |
| 2017-18 | `School Support.csv` | 97,633 | 22 | Y | Y | 17.5 |
| 2017-18 | `Single-sex Athletics.csv` | 97,632 | 18 | Y | Y | 13.4 |
| 2017-18 | `Single-sex Classes.csv` | 97,633 | 24 | Y | Y | 15.2 |
| 2017-18 | `Suspensions.csv` | 97,633 | 189 | Y | Y | 49.5 |
| 2017-18 | `Transfers.csv` | 97,632 | 46 | Y | Y | 17.8 |
| 2017-18 | `ID 22 SCH - Title I Status.csv` | 103,548 | 9 |  |  | 11.5 |
| 2017-18 | `ID 74 SCH - Educational Environment by Gender by Disability.csv` | 590,157 | 26 |  |  | 85.6 |
| 2017-18 | `ID 74 SCH - Race by Placement.csv` | 260,628 | 17 |  |  | 33.8 |
| 2017-18 | `ID 74 SCH - Race by Sex by Disability plus LEP_*.csv` (14 files) | 1k–88k | 44 |  |  | — |
| 2017-18 | `ID 814 SCH - Chronic Absenteeism.csv` | 92,437 | 32 |  |  | 15.5 |
| 2020-21 | `Distance Education.csv` | 17,822 | 29 |  | Y | 2.8 |
| 2020-21 | `High School Equivalency.csv` | 17,822 | 29 |  | Y | 2.9 |
| 2020-21 | `LEA Characteristics.csv` | 17,822 | 34 |  | Y | 7.2 |
| 2020-21 | `Advanced Mathematics.csv` | 97,576 | 30 | Y | Y | 16.4 |
| 2020-21 | `Advanced Placement.csv` | 97,576 | 94 | Y | Y | 35.9 |
| 2020-21 | `Algebra I.csv` | 97,576 | 136 | Y | Y | 45.9 |
| 2020-21 | `Algebra II.csv` | 97,576 | 30 | Y | Y | 16.4 |
| 2020-21 | `Biology.csv` | 97,576 | 30 | Y | Y | 16.4 |
| 2020-21 | `COVID Directional Indicators.csv` | 97,576 | 10 | Y | Y | 11.1 |
| 2020-21 | `Calculus.csv` | 97,576 | 30 | Y | Y | 16.5 |
| 2020-21 | `Chemistry.csv` | 97,576 | 30 | Y | Y | 16.4 |
| 2020-21 | `Computer Science.csv` | 97,576 | 30 | Y | Y | 16.5 |
| 2020-21 | `Corporal Punishment.csv` | 97,576 | 71 | Y | Y | 29.7 |
| 2020-21 | `Dual Enrollment.csv` | 97,576 | 29 | Y | Y | 16.4 |
| 2020-21 | `Enrollment.csv` | 97,576 | 118 | Y | Y | 35.5 |
| 2020-21 | `Expulsions.csv` | 97,576 | 142 | Y | Y | 40.7 |
| 2020-21 | `Geometry.csv` | 97,576 | 32 | Y | Y | 17.2 |
| 2020-21 | `Gifted and Talented.csv` | 97,576 | 29 | Y | Y | 15.8 |
| 2020-21 | `Harassment and Bullying.csv` | 97,576 | 145 | Y | Y | 40.9 |
| 2020-21 | `International Baccalaureate.csv` | 97,576 | 29 | Y | Y | 16.6 |
| 2020-21 | `Internet Access and Devices.csv` | 97,576 | 13 | Y | Y | 13.0 |
| 2020-21 | `Justice Facilities.csv` | 97,576 | 16 | Y | Y | 12.8 |
| 2020-21 | `Offenses.csv` | 97,576 | 19 | Y | Y | 13.2 |
| 2020-21 | `Physics.csv` | 97,576 | 30 | Y | Y | 16.5 |
| 2020-21 | `Referrals and Arrests.csv` | 97,576 | 84 | Y | Y | 27.4 |
| 2020-21 | `Restraint and Seclusion.csv` | 97,576 | 131 | Y | Y | 39.2 |
| 2020-21 | `Retention.csv` | 97,576 | 307 | Y | Y | 97.7 |
| 2020-21 | `SAT and ACT.csv` | 97,576 | 28 | Y | Y | 15.8 |
| 2020-21 | `School Characteristics.csv` | 97,576 | 32 | Y | Y | 22.6 |
| 2020-21 | `School Support.csv` | 97,576 | 17 | Y | Y | 12.8 |
| 2020-21 | `Single sex Athletics.csv` | 97,576 | 18 | Y | Y | 13.4 |
| 2020-21 | `Single sex Classes.csv` | 97,576 | 24 | Y | Y | 15.2 |
| 2020-21 | `Suspensions.csv` | 97,576 | 169 | Y | Y | 46.9 |
| 2020-21 | `Transfers.csv` | 97,576 | 46 | Y | Y | 18.6 |
| 2020-21 | `ID 814 SCH - Chronic Absenteeism.csv` | 92,375 | 30 |  | Y | 14.9 |
| 2021-22 | `Distance Education.csv` | 17,704 | 29 |  | Y | 2.8 |
| 2021-22 | `High School Equivalency Exam.csv` | 17,704 | 29 |  | Y | 2.9 |
| 2021-22 | `LEA Characteristics.csv` | 17,704 | 40 |  | Y | 6.5 |
| 2021-22 | `Advanced Mathematics.csv` | 98,010 | 29 | Y | Y | 16.1 |
| 2021-22 | `Advanced Placement.csv` | 98,010 | 98 | Y | Y | 37.1 |
| 2021-22 | `Algebra I.csv` | 98,010 | 132 | Y | Y | 45.0 |
| 2021-22 | `Algebra II.csv` | 98,010 | 29 | Y | Y | 16.1 |
| 2021-22 | `Biology.csv` | 98,010 | 29 | Y | Y | 16.1 |
| 2021-22 | `COVID Directional Indicators.csv` | 98,010 | 12 | Y | Y | 12.2 |
| 2021-22 | `Calculus.csv` | 98,010 | 29 | Y | Y | 16.2 |
| 2021-22 | `Chemistry.csv` | 98,010 | 29 | Y | Y | 16.1 |
| 2021-22 | `Computer Science.csv` | 98,010 | 29 | Y | Y | 16.2 |
| 2021-22 | `Corporal Punishment.csv` | 98,010 | 72 | Y | Y | 29.4 |
| 2021-22 | `Data Science.csv` | 98,010 | 10 | Y | Y | 10.8 |
| 2021-22 | `Dual Enrollment.csv` | 98,010 | 29 | Y | Y | 16.4 |
| 2021-22 | `Enrollment.csv` | 98,010 | 233 | Y | Y | 69.5 |
| 2021-22 | `Expulsions.csv` | 98,010 | 142 | Y | Y | 38.1 |
| 2021-22 | `Geometry.csv` | 98,010 | 31 | Y | Y | 16.9 |
| 2021-22 | `Gifted and Talented.csv` | 98,010 | 29 | Y | Y | 15.7 |
| 2021-22 | `Harassment and Bullying.csv` | 98,010 | 159 | Y | Y | 40.3 |
| 2021-22 | `International Baccalaureate.csv` | 98,010 | 31 | Y | Y | 17.2 |
| 2021-22 | `Internet Access and Devices.csv` | 98,010 | 13 | Y | Y | 13.0 |
| 2021-22 | `Interscholastic Athletics.csv` | 98,010 | 18 | Y | Y | 13.4 |
| 2021-22 | `Justice Facilities.csv` | 98,010 | 16 | Y | Y | 12.9 |
| 2021-22 | `Offenses.csv` | 98,010 | 33 | Y | Y | 16.3 |
| 2021-22 | `Physics.csv` | 98,010 | 29 | Y | Y | 16.1 |
| 2021-22 | `Referrals and Arrests.csv` | 98,010 | 84 | Y | Y | 25.4 |
| 2021-22 | `Restraint and Seclusion.csv` | 98,010 | 131 | Y | Y | 45.0 |
| 2021-22 | `Retention.csv` | 98,010 | 307 | Y | Y | 98.0 |
| 2021-22 | `SAT and ACT.csv` | 98,010 | 28 | Y | Y | 15.7 |
| 2021-22 | `School Characteristics.csv` | 98,010 | 34 | Y | Y | 23.7 |
| 2021-22 | `School Support.csv` | 98,010 | 19 | Y | Y | 13.7 |
| 2021-22 | `Single Sex Classes.csv` | 98,010 | 21 | Y | Y | 14.4 |
| 2021-22 | `Suspensions.csv` | 98,010 | 189 | Y | Y | 49.6 |
| 2021-22 | `Transfers.csv` | 98,010 | 46 | Y | Y | 17.8 |
