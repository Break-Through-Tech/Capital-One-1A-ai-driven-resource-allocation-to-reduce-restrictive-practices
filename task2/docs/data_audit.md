# CRDC data audit (Task 2)

Handoff for **data cleaning**. Counts were measured from the local public-use CSVs for the four requested Civil Rights Data Collection (CRDC) years. Large CSVs are **not** in git; download them from [Data.gov — CRDC](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc) and keep each year’s manual next to the files.

| Related doc | What it contains |
|---|---|
| [data_dictionary.md](data_dictionary.md) | Field definitions for the analysis subset |
| [data_inventory.md](../../lia/docs/data_inventory.md) | Full CSV list (rows, columns, size), grouped by year |

## Contents

1. [Start here](#start-here)
2. [Source](#source)
3. [Inventory](#inventory)
4. [Data quality issues](#data-quality-issues)
5. [Join keys](#join-keys)
6. [Relevant variables](#relevant-variables)
7. [Missing values](#missing-values)
8. [Year differences](#year-differences)
9. [Cleaning sequence](#cleaning-sequence)
10. [Method](#method)

---

## Start here

**Main cohort:** 2021–22 school-level CRDC (~98,010 schools).

| Year | Role |
|---|---|
| 2021–22 | Primary analysis / modeling year |
| 2017–18 | Best earlier comparison year |
| 2020–21 | COVID year — seclusion reporting is incomplete; robustness only |
| 2015–16 | Usable only after repairing Excel-corrupted IDs |

**Blockers for cleaning (details below):**

1. Recode **every value &lt; 0** to NA. Missingness is reserved codes, not blanks. Never fill with 0.
2. Join school files on **`COMBOKEY`**, reading IDs as strings and zero-padding.
3. Rebuild 2015–16 `COMBOKEY` from padded `LEAID` + `SCHID`. Do not use the stored column.
4. Ignore `SCHID` on 2017–18 `Restraint and Seclusion.csv` (values are wrong; `COMBOKEY` is fine).
5. Do not pool years until `LEP`/`EL` names, reserved-code sets, and seclusion definitions are harmonized.

---

## Source

| Item | Detail |
|---|---|
| Collection | U.S. Department of Education, Office for Civil Rights (OCR), Civil Rights Data Collection |
| Access | [Data.gov CRDC dataset](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc) → landing page → downloadable public-use files |
| Format | CSV (plus PDF/XLSX manuals in some year packages) |
| Unit | School (`COMBOKEY`) and district / LEA (`LEAID`) |
| Documentation | Year-specific manuals and restraint/seclusion guidance on the [ED CRDC page](https://www.ed.gov/laws-and-policy/civil-rights-laws/civil-rights-data-collection-crdc/civil-rights-data) |

OCR notes that districts certify submissions, but reporting gaps remain (missing modules, skip logic, suppression). Treat this as **observational, school-reported** data.

---

## Inventory

Four collections are present locally (125 CSVs plus manuals). Full file list: [data_inventory.md](../../lia/docs/data_inventory.md).

| School year | Package name (as downloaded) | Structure | School rows | LEA rows | Geography |
|---|---|---|---:|---:|---|
| 2015–16 | `2015-16-crdc-data` (updated Sept 2018) | One wide school file (1,836 cols) + one LEA file | 96,360 | 17,337 | 51 (states + DC; **no PR**) |
| 2017–18 | `2017-18-crdc-data-corrected-publication 2` | Split SCH/LEA CRDC modules + EDFacts extracts | 97,632 | 17,604 | 52 (adds **PR**) |
| 2020–21 | `2020-21-crdc-data` | Split CRDC SCH/LEA + one EDFacts absenteeism file | 97,575 | 17,821 | 52 |
| 2021–22 | `2021-22-crdc-data` | Split SCH/LEA CRDC modules | 98,010 | 17,704 | 52 |

School/LEA counts are from pandas. `wc -l` is often 1 higher (trailing newline).

**2015–16 modules** are columns in `CRDC 2015-16 School Data.csv`. Later years ship the same topics as separate CSVs.

**EDFacts files** (2017–18 ID 22 / ID 74 / ID 814; 2020–21 ID 814) use `NCESLEAID` / `NCESSCH` and a different grain. Optional for the core seclusion analysis.

### Priority files

Start with these. For 2017–18, 2020–21, and 2021–22 they share the same `COMBOKEY` set. School `LEAID`s match LEA Characteristics when IDs are read as strings.

| Year | Restraint & seclusion | Enrollment | School characteristics | School support | LEA characteristics |
|---|---|---|---|---|---|
| 2021–22 | 98,010 × 131 | 98,010 × 233 | 98,010 × 34 | 98,010 × 19 | 17,704 × 40 |
| 2020–21 | 97,575 × 131 | 97,575 × 118 | 97,575 × 32 | 97,575 × 17 | 17,821 × 34 |
| 2017–18 | 97,632 × 131 | 97,632 × 123 | 97,632 × 32 | 97,632 × 22 | 17,604 × 53 |
| 2015–16 | (in wide school file) | same | same | same | 17,337 × 115 |

2021–22 snapshot: justice facility `JJ` = Yes for 882 schools (matches `SCH_JUST_IND`); virtual `SCH_VIRT_IND` = Yes for 2,496; special-education 1,809; charter 7,721; alternative 4,127; magnet 4,027.

---

## Data quality issues

For the cleaning ticket:

1. **Reserved negatives are missingness, not counts.** Recode all `< 0` to NA. Do not impute 0.
2. **2021–22 seclusion instances:** 4,905 / 98,010 schools have a reserved code (`-9` dominant). Exclude from rates or flag as unknown — not zero.
3. **2020–21 seclusion is incomplete.** 14,158 schools coded `-11` on instance fields; only 76,554 usable. Use COVID indicators (`SCH_DIND_INSTRUCTIONTYPE`, `SCH_DIND_VIRTUALTYPE`) if that year is used at all.
4. **Zero inflation is real.** Among usable 2021–22 rows, WODIS instances are 0 for 90,682 schools and positive for 2,423. The elevated-rate class will be small.
5. **Do not sum overlapping student seclusion counts** (race × sex × IDEA/non-IDEA). Use instance totals for the primary rate; keep student counts as a secondary outcome with matching denominators.
6. **2015–16 IDs must be repaired** (string dtype, zfill, rebuild `COMBOKEY`). Otherwise joins and longitudinal matches are wrong.
7. **2017–18 Restraint `SCHID` is unusable**; join that module on `COMBOKEY`.
8. **Impossible FTEs in 2017–18 School Support:** `SCH_FTESECURITY_GUA` max **102,579** (DEL VALLE H S, `481662001424`); nearby campuses 20k–34k guards. `SCH_FTESERVICES_PSY` max **19,048.6** (Northshore Middle School). 2015–16 counselor/nurse/psych maxima of **999** look like a cap.
9. **Small denominators.** Median 2021–22 `TOT_ENR_M` ≈ 210; some schools have 0–few students. Rates per 100 will explode — cap, shrink, or exclude tiny enrollment.
10. **Justice facilities (`JJ` = Yes)** often contain reserved values (security FTE `-9`, seclusion `-5`); these codes must not both be described as skip logic. Decide whether they stay in the analysis set.
11. **Encoding:** 2015–16 CSVs and 2017–18 School Characteristics need `encoding="cp1252"` (or UTF-8 then fall back).
12. **Same-year discipline files** (suspensions, offenses, referrals/arrests, corporal punishment) are likely **leaky** as predictors of seclusion.
13. **Do not pool years** until names (`LEP` vs `EL`), reserved-code sets, and seclusion definitions are harmonized.
14. **Local CSVs are untracked and large.** Document the package names in the inventory so teammates can reproduce.

---

## Join keys

### Use these

| Key | Meaning | How to use |
|---|---|---|
| **`COMBOKEY`** | 12-character `LEAID` (7) + `SCHID` (5) | **Primary school join** within a year, and the intended key across years |
| `LEAID` | 7-digit NCES district ID | Schools → LEA file; split by district |
| `SCHID` | 5-digit school ID **within LEA** | Never join on `SCHID` alone |
| `LEA_STATE` | State / territory abbreviation | Filter / stratify — not unique |
| `JJ` | Juvenile-justice facility (Yes/No) | Flag; 2021–22 also has `SCH_JUST_IND` |

Always read IDs as **strings**. Zero-pad: `LEAID` → 7, `SCHID` → 5, `COMBOKEY` → 12. Then `LEAID + SCHID` equals `COMBOKEY` in 2021–22, 2020–21, and 2017–18 Enrollment / Characteristics / Support.

### Pitfalls

1. **2017–18 `Restraint and Seclusion.csv`:** `SCHID` is wrong on 97,630 / 97,632 rows (e.g. true `01705` stored as `01017`). `LEAID` and `SCH_NAME` match. Join on **`COMBOKEY` only**.
2. **2015–16 stored `COMBOKEY` is Excel-corrupted.** Leading zeros dropped; 78,034 rows use scientific notation such as `1.20039E+11` (only 29,374 distinct stored values). Rebuild `COMBOKEY = LEAID.zfill(7) + SCHID.zfill(5)` → 96,360 unique keys and a perfect school↔LEA match. Do not use unrepaired keys for longitudinal joins.
3. **`SCHID` is reused across districts** (e.g. `99999` hundreds of times). National uniqueness requires `COMBOKEY`.
4. **EDFacts:** `NCESSCH` ↔ padded `COMBOKEY`, `NCESLEAID` ↔ `LEAID`, after a coverage check. 2017–18 Title I has 103,547 rows vs 97,632 CRDC schools.

### Duplicates

| Check | Result |
|---|---|
| Duplicate `COMBOKEY` in 2021–22 / 2020–21 / 2017–18 CRDC school modules | **None** (after dropping trailing blank lines) |
| Duplicate `LEAID` in LEA Characteristics | **None** |
| Duplicate stored `COMBOKEY` in 2015–16 | **Yes** — 9,213 colliding keys, 76,199 rows. **Zero** after rebuild |
| Full-row duplicates on Characteristics / Support / LEA | **None** |
| Duplicate `SCHID` | Expected (within-LEA ID) |

### Cross-year overlap

Unrepaired 2015–16 keys are not comparable. Among later years:

| Pair | Overlap | Only left | Only right |
|---|---:|---:|---:|
| 2021–22 ∩ 2020–21 | 96,061 | 1,949 | 1,514 |
| 2021–22 ∩ 2017–18 | 91,466 | 6,544 | 6,166 |
| 2020–21 ∩ 2017–18 | 92,399 | 5,176 | 5,233 |

Schools open, close, and re-ID. Do not assume a balanced panel.

---

## Relevant variables

Priority for the analysis-ready school table. Definitions: [data_dictionary.md](data_dictionary.md).

**Must have**

- Keys: `COMBOKEY`, `LEAID`, `SCHID` (padded), `LEA_STATE`, `SCH_NAME`, `LEA_NAME`
- Outcome: seclusion **instances** `SCH_RSINSTANCES_SECL_WODIS`, `_IDEA`, `_504` → sum if all valid
- Denominator: `TOT_ENR_M`, `TOT_ENR_F` (optional valid `TOT_ENR_X` in 2021–22)
- School type: `SCH_STATUS_SPED`, `_CHARTER`, `_ALT`, `_MAGNET`, `JJ` / `SCH_JUST_IND`, `SCH_VIRT_IND` (2021–22), grade-span flags
- Staffing: `SCH_FTECOUNSELORS`, `SCH_FTETEACH_TOT`, `SCH_FTETEACH_CERT`, `SCH_FTESERVICES_NUR`, `_PSY`, `_SOC`
- Composition: IDEA, 504, EL/LEP enrollment (shares, not the main denominator)

**Useful**

- Security FTE (`SCH_FTESECURITY_LEO`, `_GUA`) as context, after outlier handling
- LEA size: `LEA_ENR`, `LEA_SCHOOLS`
- 2017–18 (and 2015–16) school expenditures
- Secondary outcome: students subjected to seclusion (`TOT_RS_NONIDEA_SECL_*` + `TOT_RS_IDEA_SECL_*`) — different from incidents
- Mechanical / physical restraint instances — related restrictive practice, not the primary target

**Keep out of core predictors until reviewed**

- Other seclusion/restraint components (leakage if predicting seclusion)
- Suspensions, expulsions, referrals/arrests, offenses, corporal punishment
- Race/sex seclusion cells as features (OK for equity **description**)

---

## Missing values

Pandas-null / blank cells are rare. **Missingness is stored as negative reserved codes.** Any value `< 0` is not a real count or FTE.

Definitions were verified in the bundled **2015–16 manual, Table 2, p. 18** and **2017–18 manual, Table 2, p. 12**. See the [source links and year-by-year code table](data_dictionary.md#reserved-codes-all-numeric-fields).

| Code | Verified meaning | Manual listing |
|---|---|---|
| `-9` | Not Applicable / Skipped | Both years |
| `-5` | Action Plan | Both years |
| `-6` | Force Certified | Both years |
| `-8` | EDFacts Missing Data | Both years |
| `-2` | Small Cell Value | 2015–16 |
| `-7` | System Error | 2015–16 |
| `-3` | Skip Logic Failure | 2017–18 |
| `-11` | Suppressed Data | 2017–18 |

The observed `-12` (2021–22 nonbinary enrollment) and `-13` (2020–21/2021–22 seclusion) are outside these older manuals; their definitions still require the corresponding year’s documentation. Observed frequencies below are not evidence of a code’s meaning in another year.

**Rule for counts/FTEs:** `pd.to_numeric`, then set `value < 0` to NA. Keep zero as a reported zero; never replace a reserved code with zero. The different reasons remain available in the original CSVs.

### Seclusion instances (proposed target)

`SCH_RSINSTANCES_SECL_WODIS` + `SCH_RSINSTANCES_SECL_IDEA` + `SCH_RSINSTANCES_SECL_504`

Intended as a partition (no-disability / IDEA / 504-only). Verify skip logic before summing. Do not add student-count columns (`TOT_RS_*_SECL_*`) into the same total.

| Year | Rows | All three ≥ 0 | `-9` | Other negatives (WODIS) | WODIS &gt; 0 | IDEA &gt; 0 |
|---|---:|---:|---:|---|---:|---:|
| 2021–22 | 98,010 | 93,105 | 4,377 | `-13`: 353; `-5`: 172; `-3`: 3 | 2,423 | 5,697 |
| 2020–21 | 97,575 | 76,554 | 1,875 | **`-11`: 14,158**; `-13`: 4,700; `-5`: 288 | 1,327 | 4,037 |
| 2017–18 | 97,632 | 91,141 | 1,908 | `-6`: 3,089; `-11`: 1,203; `-5`: 291 | 2,062 | 5,504 |
| 2015–16 | 96,360 | 93,966 | 1,806 | `-5`: 588 | 1,876 | 4,489 |

2020–21: only **78%** of schools have a usable instance count.

Student-count seclusion fields are **not** interchangeable with instances. In 2021–22 those totals are `-9` for ~92–95k schools (filled mainly where instances exist). In 2017–18 / 2020–21 they look more like the instance fields (including the same reserved codes).

### Enrollment denominators

Proposed rate: `100 × (valid seclusion instances) / (TOT_ENR_M + TOT_ENR_F [+ TOT_ENR_X if valid])`.

| Year | `TOT_ENR_M` usable (≥ 0) | Notes |
|---|---:|---|
| 2021–22 | 96,138 | `-9` on 1,872 schools; `TOT_ENR_X` is mostly `-9` (92,805) or `-12` (2,850); only 2,354 schools have a positive nonbinary count. **Do not require `_X` for every school.** |
| 2020–21 | ~97k if negatives are not stripped | Strip all `< 0` first (`-11` appears here too) |
| 2017–18 | 97,622 | 10 rows `-5` |
| 2015–16 | 96,359 | 1 row `-5` |

IDEA / 504 / EL-or-LEP enrollment are **composition features**, not the primary denominator, unless building a subgroup rate with a matching numerator.

### Staffing

FTE fields (`SCH_FTECOUNSELORS`, `SCH_FTETEACH_TOT`, nurses / psychologists / social workers, security) are populated for most schools but still contain reserved negatives. Security FTE is `-9` for most justice-facility schools (882 in 2021–22).

---

## Year differences

Do not pool blindly. Variable **meanings** can change even when names match — re-read each year’s restraint/seclusion definitions before summing WODIS+IDEA+504.

| Topic | Difference |
|---|---|
| File layout | 2015–16 = one wide school CSV; later years = one CSV per module |
| Geography | PR from 2017–18 onward |
| COVID | 2020–21 (plus a 2021–22 COVID indicators file). Seclusion often `-11` / `-13` |
| English learners | `*_LEP_*` through 2020–21; `*_EL_*` in 2021–22 |
| Nonbinary | `*_X` and `TOT_ENR_X` in 2021–22 enrollment only |
| Virtual / justice flags | `SCH_VIRT_IND`, `SCH_JUST_IND` in 2021–22; earlier years have `JJ` only |
| School Support extras | 2017–18 first-year / absent teachers; 2021–22 `TOT_TEACHERS_CURR_M/F` |
| School expenditures | **2017–18 only** in these packages (also columns in the 2015–16 wide file) |
| Internet / CS / data science | Internet + CS from 2020–21; Data Science 2021–22 |
| Encoding | Most files UTF-8; **2015–16 data + 2017–18 School Characteristics** need `cp1252` |

---

## Cleaning sequence

1. Read each priority CSV as strings; fix encoding; drop empty trailing rows.
2. Pad IDs; rebuild 2015–16 `COMBOKEY`; ignore 2017–18 restraint `SCHID`.
3. Inner-join 2021–22 Characteristics + Enrollment + Restraint + Support on `COMBOKEY`; left-join LEA on `LEAID`.
4. Recode reserved codes to NA; build instance sum and enrollment total; drop or flag rows missing either.
5. Flag JJ / virtual / special-education / tiny enrollment.
6. Repeat for 2017–18 as a comparison cohort; treat 2020–21 as COVID-sensitivity only; bring 2015–16 in after ID repair if needed.

---

## Method

Profiles used Python/pandas (`dtype=str`), with UTF-8 then `cp1252` fallback. Inventory row counts may include a blank line; tables in [Inventory](#inventory) use pandas. A first pass only treated `-9,-5,-2,-8,-3` as reserved; **additional negatives (`-6,-11,-12,-13`) were found afterward**. Cleaning must treat **all negatives** as reserved.
