# CRDC data audit (Task 2)

This audit covers the 2015–16, 2017–18, 2020–21, and 2021–22 Civil Rights Data Collection (CRDC) files. It records the available datasets, relevant fields, and data quality issues found in the CSVs. The datasets are too large to include in git. The CRDC data and manuals will be uploaded to the team Google Drive; the original source is [Data.gov — CRDC](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc).

| Related doc | What it contains |
|---|---|
| [data_dictionary.md](data_dictionary.md) | Field definitions for the analysis subset |
| [data_inventory.md](data_inventory.md) | Full CSV list (rows, columns, size), grouped by year |

Abbreviations used throughout: LEA = local education agency (district); JJ = juvenile justice facility; FTE = full-time equivalent staff; IDEA = students served under the Individuals with Disabilities Education Act; WODIS = students without disabilities; 504 = students served only under Section 504; EL / LEP = English learner / limited English proficient; DQ = data quality; DIND = COVID-related directional indicators.

## Contents

1. [Recommended dataset](#recommended-dataset)
2. [Source](#source)
3. [Inventory](#inventory)
4. [Data quality issues](#data-quality-issues)
5. [Join keys](#join-keys)
6. [Relevant variables](#relevant-variables)
7. [Missing values](#missing-values)
8. [Year differences](#year-differences)
9. [Cleaning sequence](#cleaning-sequence)
10. [Method](#method)

## Recommended dataset

Recommended starting year: 2021–22 school-level CRDC (98,010 schools).

| Year | Role |
|---|---|
| 2021–22 | Primary analysis / modeling year |
| 2017–18 | Earlier comparison year |
| 2020–21 | COVID year — seclusion reporting is incomplete; robustness only |
| 2015–16 | Usable only after repairing Excel-corrupted IDs |

Issues to address before analysis:

1. Recode every value &lt; 0 to NA and keep the original code in a companion column. Missingness is stored as reserved codes, not blanks. Never fill with 0.
2. Join school files on `COMBOKEY`, reading IDs as strings and zero-padding.
3. Rebuild 2015–16 `COMBOKEY` from padded `LEAID` + `SCHID`. Do not use the stored column.
4. Ignore `SCHID` on 2017–18 `Restraint and Seclusion.csv` (values are wrong; `COMBOKEY` is fine).
5. Do not pool years until `LEP`/`EL` names, reserved-code sets, and seclusion definitions are harmonized (see [Year differences](#year-differences)).

## Source

| Item | Detail |
|---|---|
| Collection | U.S. Department of Education, Office for Civil Rights (OCR), Civil Rights Data Collection |
| Access | Team Google Drive (upload pending); original: [Data.gov CRDC dataset](https://catalog.data.gov/dataset/civil-rights-data-collection-crdc) → landing page → downloadable public-use files |
| Format | CSV (plus PDF/XLSX manuals in the 2015–16 and 2017–18 packages) |
| Unit | School (`COMBOKEY`) and district / LEA (`LEAID`) |
| Documentation | Year-specific manuals and restraint/seclusion guidance on the [ED CRDC page](https://www.ed.gov/laws-and-policy/civil-rights-laws/civil-rights-data-collection-crdc/civil-rights-data); manual links in [data_dictionary.md](data_dictionary.md#reserved-codes-all-numeric-fields) |

Districts certify their submissions, but reporting gaps remain (missing modules, skip logic, suppression). Treat this as observational, school-reported data. Two manual notes matter for analysis:

- Public-use student counts are perturbed (small random adjustments) to protect privacy (2017–18 manual §1.4; 2020–21 and 2021–22 manuals §5.2.1). Very small counts at a single school are noisy by design.
- In 2017–18, OCR told LEAs that did not collect restraint and seclusion data to report nulls instead of all zeros (2017–18 manual §3.4). A zero is therefore meant to be a reported zero.

## Inventory

Four collections are available (125 CSVs plus manuals). Full file list: [data_inventory.md](data_inventory.md).

| School year | Package name (as downloaded) | Structure | School rows | LEA rows | Geography |
|---|---|---|---:|---:|---|
| 2015–16 | `2015-16-crdc-data` (updated Sept 2018) | One wide school file (1,836 cols) + one LEA file | 96,360 | 17,337 | 51 (states + DC; no PR) |
| 2017–18 | `2017-18-crdc-data-corrected-publication 2` | Split SCH/LEA CRDC modules + EDFacts extracts | 97,632 | 17,604 | 52 (adds PR) |
| 2020–21 | `2020-21-crdc-data` | Split CRDC SCH/LEA + one EDFacts absenteeism file | 97,575 | 17,821 | 52 |
| 2021–22 | `2021-22-crdc-data` | Split SCH/LEA CRDC modules | 98,010 | 17,704 | 52 |

School and LEA counts are parsed CSV rows. Raw line counts can be higher because of trailing blank lines and line breaks inside quoted fields.

2015–16 modules are columns in `CRDC 2015-16 School Data.csv`. Later years ship the same topics as separate CSVs.

EDFacts files (2017–18 ID 22 / ID 74 / ID 814; 2020–21 ID 814) use `NCESLEAID` / `NCESSCH` and a different record structure. They are optional for the core seclusion analysis.

### Priority files

These files contain the outcome, enrollment, and staffing fields needed for the project. For 2017–18, 2020–21, and 2021–22 they share the same `COMBOKEY` set. Every school `LEAID` matches LEA Characteristics when IDs are read as strings.

| Year | Restraint & seclusion | Enrollment | School characteristics | School support | LEA characteristics |
|---|---|---|---|---|---|
| 2021–22 | 98,010 × 131 | 98,010 × 233 | 98,010 × 34 | 98,010 × 19 | 17,704 × 40 |
| 2020–21 | 97,575 × 131 | 97,575 × 118 | 97,575 × 32 | 97,575 × 17 | 17,821 × 34 |
| 2017–18 | 97,632 × 131 | 97,632 × 123 | 97,632 × 32 | 97,632 × 22 | 17,604 × 53 |
| 2015–16 | (in wide school file) | same | same | same | 17,337 × 115 |

2021–22 snapshot: `JJ` = Yes for 882 schools (identical to `SCH_JUST_IND`); virtual `SCH_VIRT_IND` = Yes for 2,496; special-education 1,809; charter 7,721; alternative 4,127; magnet 4,027.

## Data quality issues

1. **Reserved codes are not counts.** Negative values mark missing, skipped, or suppressed data. Recode all `< 0` to NA, keep the code, and never impute 0 ([Missing values](#missing-values)).
2. **2021–22 seclusion gaps.** 4,905 of 98,010 schools have a reserved code on the seclusion instance fields (mostly `-9`). Exclude them from rates or flag them as unknown, not zero.
3. **2020–21 seclusion is incomplete.** Only 76,546 schools (78%) have all three instance fields usable; 14,158 are DQ-suppressed (`-11`) and 4,700 virtual-only schools are skipped (`-13`). If that year is used, use the COVID indicator fields listed in [Year differences](#year-differences).
4. **Most schools report zero.** Among usable 2021–22 rows, WODIS instances are 0 for 90,682 schools and positive for 2,423. Expect a zero-inflated outcome.
5. **Student counts overlap.** Do not sum student seclusion counts across race × sex × IDEA/non-IDEA. Use instance totals for the primary rate and keep student counts as a secondary outcome.
6. **2015–16 IDs are corrupted.** Read as strings, zero-pad, and rebuild `COMBOKEY`; otherwise joins and longitudinal matches are wrong.
7. **2017–18 Restraint `SCHID` is wrong.** Join that module on `COMBOKEY` only.
8. **Implausible FTE values in every year.** Examples: 2017–18 `SCH_FTESECURITY_GUA` = 102,579 at DEL VALLE H S (`481662001424`) with nearby campuses at 32k–34k, and `SCH_FTESERVICES_PSY` = 19,048.6 at Northshore Middle School. 2021–22: Central Academy (`260016301004`) reports exactly 100.0 in five FTE fields and Pacific Grove High reports 280 counselors. 2020–21: Southside Elementary (`160000200616`) reports 833 nurses. 2015–16: counselor, nurse, psychologist, and social-worker maxima are 999 at a single school each, which looks like a placeholder. Check FTE per student before using staffing features.
9. **Small or zero denominators.** Median 2021–22 `TOT_ENR_M` is about 210. 247 schools have `TOT_ENR_M` = 0, and 11 have a valid male and female enrollment that sums to 0. Rates per 100 students are unstable at small schools and undefined at zero.
10. **Justice facilities differ by year.** Security FTE is `-9` for all 882 JJ schools in 2021–22 and 573 of 579 in 2020–21, but for none of the 602 in 2017–18. Most JJ schools still report seclusion (839 of 882 in 2021–22). Decide whether they stay in the analysis set.
11. **Mixed file encodings.** 26 of the 33 CRDC CSVs in the 2017–18 package, including School Characteristics, School Support, and LEA Characteristics, are `cp1252`, as are the 2015–16 files. Read every file as UTF-8 and fall back to `cp1252` on a decode error.
12. **Leakage risk.** Same-year discipline files (suspensions, offenses, referrals/arrests, corporal punishment) need a leakage review before they are used to predict seclusion.
13. **Data is not in git.** Use the package names in the inventory and the team Google Drive copy so teammates work from the same files.

## Join keys

### Key definitions

| Key | Meaning | How to use |
|---|---|---|
| `COMBOKEY` | 12-character `LEAID` (7) + `SCHID` (5) | Primary school join within a year, and the intended key across years |
| `LEAID` | 7-digit NCES district ID | Schools → LEA file; split by district |
| `SCHID` | 5-digit school ID within LEA | Never join on `SCHID` alone |
| `LEA_STATE` | State / territory abbreviation | Filter / stratify — not unique |
| `JJ` | Juvenile justice facility (Yes/No) | Flag; 2021–22 also has `SCH_JUST_IND` |

Always read IDs as strings. Zero-pad: `LEAID` → 7, `SCHID` → 5, `COMBOKEY` → 12. Then `LEAID + SCHID` equals `COMBOKEY` in every 2017–18, 2020–21, and 2021–22 priority module except 2017–18 Restraint and Seclusion.

### Identifier issues

1. 2017–18 `Restraint and Seclusion.csv`: `SCHID` is wrong on 97,630 of 97,632 rows (e.g. true `01705` stored as `01017`). `LEAID` and `SCH_NAME` match. Join on `COMBOKEY` only.
2. 2015–16 stored `COMBOKEY` is Excel-corrupted. Leading zeros are dropped (raw `LEAID` has 6–7 digits, `SCHID` 1–5), and 78,034 rows use scientific notation such as `1.20039E+11` (only 29,374 distinct stored values). Rebuilding `COMBOKEY = LEAID.zfill(7) + SCHID.zfill(5)` gives 96,360 unique keys and a school-to-LEA match for every school.
3. `SCHID` is reused across districts (e.g. `99999` hundreds of times). National uniqueness requires `COMBOKEY`.
4. EDFacts: `NCESSCH` ↔ padded `COMBOKEY`, `NCESLEAID` ↔ `LEAID`. Coverage is incomplete: of the 103,547 rows in 2017–18 Title I, 94,048 match a CRDC school, and 3,584 of the 97,632 CRDC schools have no Title I row.

### Duplicates

| Check | Result |
|---|---|
| Duplicate `COMBOKEY` in 2021–22 / 2020–21 / 2017–18 CRDC school modules | None (after dropping trailing blank lines) |
| Duplicate `LEAID` in LEA Characteristics | None |
| Duplicate stored `COMBOKEY` in 2015–16 | Yes — 9,213 colliding keys, 76,199 rows. Zero after rebuild |
| Full-row duplicates on Characteristics / Support / LEA | None |
| Duplicate `SCHID` | Expected (within-LEA ID) |

### Cross-year overlap

Counts use padded `COMBOKEY`; 2015–16 uses the rebuilt key.

| Pair | Overlap | Only left | Only right |
|---|---:|---:|---:|
| 2021–22 ∩ 2020–21 | 96,061 | 1,949 | 1,514 |
| 2021–22 ∩ 2017–18 | 91,466 | 6,544 | 6,166 |
| 2020–21 ∩ 2017–18 | 92,399 | 5,176 | 5,233 |
| 2021–22 ∩ 2015–16 | 88,242 | 9,768 | 8,118 |
| 2017–18 ∩ 2015–16 | 92,866 | 4,766 | 3,494 |

87,762 schools appear in all four years. The school lists differ across years, so check openings, closures, and ID changes before comparing the same schools over time.

## Relevant variables

Priority for the analysis-ready school table. Definitions: [data_dictionary.md](data_dictionary.md).

Required fields

- Keys: `COMBOKEY`, `LEAID`, `SCHID` (padded), `LEA_STATE`, `SCH_NAME`, `LEA_NAME`
- Outcome: seclusion instances `SCH_RSINSTANCES_SECL_WODIS`, `_IDEA`, `_504` → sum only if all three are valid
- Denominator: `TOT_ENR_M`, `TOT_ENR_F` (plus `TOT_ENR_X` in 2021–22 when valid)
- School type: `SCH_STATUS_SPED`, `_CHARTER`, `_ALT`, `_MAGNET`, `JJ` / `SCH_JUST_IND`, `SCH_VIRT_IND` (2021–22), grade-span flags
- Staffing: `SCH_FTECOUNSELORS`, `SCH_FTETEACH_TOT`, `SCH_FTETEACH_CERT`, `SCH_FTESERVICES_NUR`, `_PSY`, `_SOC`
- Composition: IDEA, 504, EL/LEP enrollment (shares, not the main denominator)

Additional fields to consider

- Security FTE (`SCH_FTESECURITY_LEO`, `_GUA`) as context, after outlier handling
- LEA size: `LEA_ENR`, `LEA_SCHOOLS`
- 2017–18 (and 2015–16) school expenditures
- Secondary outcome: students subjected to seclusion (`TOT_RS_NONIDEA_SECL_*` + `TOT_RS_IDEA_SECL_*`) — different from incidents
- Mechanical / physical restraint instances — related restrictive practice, not the primary target

Fields requiring review before use as predictors

- Other seclusion/restraint components (leakage if predicting seclusion)
- Suspensions, expulsions, referrals/arrests, offenses, corporal punishment
- Race/sex seclusion cells as features (fine for equity description)
- `TOT_TEACHERS_CURR_M` / `_F` (2021–22): `-4` for about 58k schools, so not usable as a general feature

## Missing values

Blank cells are rare. Missingness is stored as negative reserved codes, so any value `< 0` is not a real count or FTE.

### Reserved code definitions

Definitions are taken from each year's manual: 2015–16 Table 2 (p. 18), 2017–18 Table 2 (p. 12), 2020–21 §5.4 (p. 12), and 2021–22 Table 1 (p. 12). Links are in [data_dictionary.md](data_dictionary.md#reserved-codes-all-numeric-fields). "—" means the code is not listed for that year.

| Code | Definition | Group | 2015–16 | 2017–18 | 2020–21 | 2021–22 |
|---|---|---|---|---|---|---|
| `-9` | Not Applicable / Skipped | Structural skip | Listed | Listed | Listed | Listed |
| `-13` | Missing DIND skip logic (virtual-only schools skipped the module) | Structural skip | — | — | Listed | Listed |
| `-5` | Action Plan (2020–21 on: Action Plan / Quick Plans) | Missing | Listed | Listed | Listed | Listed |
| `-6` | Force Certified | Missing | Listed | Listed | Listed | Listed |
| `-3` | Skip Logic Failure (2021–22: Skip Logic or Processing Failure) | Missing | — | Listed | Listed | Listed |
| `-4` | Missing Optional Data | Missing | — | — | Listed | Listed |
| `-7` | System Error | Missing | Listed | — | — | — |
| `-8` | EDFacts Missing Data | Missing | Listed | Listed | Listed | — |
| `-2` | Small Cell Value | Suppressed | Listed | — | — | — |
| `-11` | Suppressed Data (DQ suppression) | Suppressed | — | Listed | Listed | — |
| `-12` | Suppressed for Privacy Protections | Suppressed | — | — | — | Listed |

The 2020–21 and 2021–22 manuals say `-4` appears only in the restricted-use file. The 2021–22 public-use School Support file nevertheless contains it (see below).

### Observed codes in the priority files

| Year | Codes found | Where the less common codes appear |
|---|---|---|
| 2021–22 | `-9`, `-13`, `-5`, `-6`, `-3`, `-4`, `-12` | `-4`: `TOT_TEACHERS_CURR_M` (57,947) and `_F` (57,799) only. `-12`: nonbinary `_X` enrollment columns (`TOT_ENR_X` 2,850). `-13`: 353 schools on every restraint/seclusion instance field. `-3`: enrollment race/sex cells (439 cells), counselor and teacher FTE (about 80–96 schools per field), `TOT_ENR_F` (14), a few restraint cells |
| 2020–21 | `-9`, `-13`, `-5`, `-11` | `-13`: 4,700 schools across the restraint and seclusion module. `-11`: restraint/seclusion, enrollment, support, and LEA files |
| 2017–18 | `-9`, `-5`, `-6`, `-11` | `-11` only in restraint and seclusion among priority files |
| 2015–16 | `-9`, `-5`, `-2` | `-2`: IDEA enrollment (`SCH_ENR_IDEA_M/F`) and LEA GED counts. The wide file also has `-7` (juvenile-justice program fields, 394 schools) and `-6` (retention, Algebra passing, absence), outside the priority fields |

`-8` does not occur in any priority file; it applies to EDFacts tables.

### Recoding rule

For counts and FTEs: `pd.to_numeric`, then set `value < 0` to NA, and keep the original code in a companion column (for example `seclusion_reason`). Group the codes so analysis can tell them apart:

- Structural skip (`-9`, `-13`): the question did not apply, e.g. a detail table skipped after a "no" answer or a virtual-only school.
- Missing (`-5`, `-6`, `-3`, `-4`, `-7`, `-8`): the value should exist but was not reported.
- Suppressed (`-11`, `-12`, `-2`): the value was reported but withheld from the public file.

Keep zero as a reported zero; never replace a reserved code with zero.

Calculated totals (`TOT_*` columns, including `TOT_ENR_M/F`) were built by OCR by summing the components and treating reserved codes as zero. A total gets a reserved code only when all its components are reserved (or, in 2020–21, when any component is `-11`) (2020–21 and 2021–22 manuals §5.5.2). A valid total can therefore hide missing components.

### Seclusion instances (proposed target)

`SCH_RSINSTANCES_SECL_WODIS` + `SCH_RSINSTANCES_SECL_IDEA` + `SCH_RSINSTANCES_SECL_504`

Intended as a partition (no disability / IDEA / 504 only). Verify skip logic before summing. Do not add student-count columns (`TOT_RS_*_SECL_*`) into the same total.

| Year | Rows | All three ≥ 0 | WODIS `-9` | Other WODIS negatives | WODIS &gt; 0 | IDEA &gt; 0 |
|---|---:|---:|---:|---|---:|---:|
| 2021–22 | 98,010 | 93,105 | 4,377 | `-13`: 353; `-5`: 172; `-3`: 3 | 2,423 | 5,697 |
| 2020–21 | 97,575 | 76,546 | 1,875 | `-11`: 14,158; `-13`: 4,700; `-5`: 288 | 1,327 | 4,037 |
| 2017–18 | 97,632 | 91,013 | 1,908 | `-6`: 3,089; `-11`: 1,203; `-5`: 291 | 2,062 | 5,504 |
| 2015–16 | 96,360 | 93,966 | 1,806 | `-5`: 588 | 1,876 | 4,489 |

The code columns describe WODIS only. In 2020–21 and 2017–18, 8 and 128 schools have a valid WODIS value but `-11` or `-6` on IDEA or 504, which is why "All three ≥ 0" is lower than rows minus WODIS negatives. In 2021–22 the three fields always share the same code; in 2015–16 every school with a valid WODIS value also has valid IDEA and 504 values.

Student-count seclusion fields are not interchangeable with instances. In 2021–22 the student totals are `-9` for 92k–95k schools (filled mainly where instances exist). In 2017–18 and 2020–21 they carry roughly the same reserved codes as the instance fields. In 2020–21, a submission-check error let 1,315 LEAs report more students secluded than instances (2020–21 manual §5.4.1.2).

### Enrollment denominators

Proposed rate: `100 × (valid seclusion instances) / (TOT_ENR_M + TOT_ENR_F [+ TOT_ENR_X if valid])`. Require both `TOT_ENR_M` and `TOT_ENR_F` to be valid, and set the rate to NA when the total is 0.

| Year | `TOT_ENR_M` usable | `TOT_ENR_F` usable | Reserved codes | `TOT_ENR_M` = 0 | M + F = 0 |
|---|---:|---:|---|---:|---:|
| 2021–22 | 96,138 | 96,124 | `-9`: 1,872 (both); `-3`: 14 (F only) | 247 | 11 |
| 2020–21 | 97,014 | 97,015 | `-11`: 561 (M), 560 (F) | 247 | 0 |
| 2017–18 | 97,621 | 97,621 | `-5`: 10 (Peabody, MA, action plan); `-6`: 1 (Preble County ESC, force certified) | 253 | 0 |
| 2015–16 | 96,359 | 96,359 | `-5`: 1 | 259 | 0 |

In 2021–22, `TOT_ENR_X` is mostly `-9` (92,805) or `-12` (2,850); only 2,354 schools have a positive nonbinary count, so do not require `_X` for every school.

IDEA / 504 / EL-or-LEP enrollment are composition features, not the primary denominator, unless you build a subgroup rate with a matching numerator.

### Staffing

FTE fields (`SCH_FTECOUNSELORS`, `SCH_FTETEACH_TOT`, nurses / psychologists / social workers, security) are populated for most schools but still contain reserved codes. Security FTE is `-9` for JJ schools in 2021–22 (882 of 882) and 2020–21 (573 of 579), but not in 2017–18. See data quality issue 8 for outliers.

## Year differences

Check each year's restraint and seclusion definitions before combining years or summing WODIS, IDEA, and 504 counts. Matching field names do not establish that definitions stayed the same.

| Topic | Difference |
|---|---|
| File layout | 2015–16 = one wide school CSV; later years = one CSV per module |
| Geography | PR from 2017–18 onward |
| COVID | 2020–21 seclusion often `-11` / `-13`. COVID indicator fields: 2020–21 `SCH_DIND_INSTRUCTIONTYPE`, `SCH_DIND_VIRTUALTYPE`; 2021–22 `SCH_DIND_INSTRUCTIONTYPE`, `SCH_DIND_REMOTETYPE`, `SCH_DIND_REMOTEAMOUNT`, `SCH_DIND_REMOTEPERCT` |
| Reserved codes | Code sets change every year; see [Reserved code definitions](#reserved-code-definitions) |
| Suppression | 2015–16 `-2` small cells; 2017–18 and 2020–21 `-11` DQ suppression; 2021–22 no DQ suppression, `-12` privacy suppression on nonbinary counts |
| English learners | `*_LEP_*` through 2020–21; `*_EL_*` in 2021–22 |
| Nonbinary | `*_X` and `TOT_ENR_X` in 2021–22 enrollment only |
| Virtual / justice flags | `SCH_VIRT_IND`, `SCH_JUST_IND` in 2021–22; earlier years have `JJ` only |
| JJ schools | 608 (2015–16), 602 (2017–18), 579 (2020–21), 882 (2021–22) |
| School Support extras | 2017–18 first-year / absent teachers; 2021–22 `TOT_TEACHERS_CURR_M/F` |
| School expenditures | 2017–18 only in these packages (also columns in the 2015–16 wide file) |
| Internet / CS / data science | Internet + CS from 2020–21; Data Science 2021–22 |
| Encoding | 2020–21 and 2021–22 are UTF-8; 26 of the 33 CRDC CSVs in the 2017–18 package and all 2015–16 files are `cp1252` |

## Cleaning sequence

1. Read each priority CSV as strings (UTF-8, falling back to `cp1252`); drop empty trailing rows.
2. Pad IDs; rebuild 2015–16 `COMBOKEY`; ignore 2017–18 restraint `SCHID`.
3. Inner-join 2021–22 Characteristics + Enrollment + Restraint + Support on `COMBOKEY`; left-join LEA on `LEAID`.
4. Recode reserved codes to NA and keep a reason column; build the instance sum (all three valid) and the enrollment total (M and F valid); set the rate to NA when enrollment is 0; flag rows missing either.
5. Check FTE plausibility (FTE per student) and flag or cap outliers.
6. Flag JJ / virtual / special-education / small-enrollment schools.
7. Repeat for 2017–18 as a comparison cohort; treat 2020–21 as COVID sensitivity only; bring 2015–16 in after ID repair if needed.

## Method

Profiles used Python with every value read as a string, UTF-8 with a `cp1252` fallback, and blank rows dropped. Counts in this document are parsed CSV rows. Reserved codes found in the priority files were `-2, -3, -4, -5, -6, -9, -11, -12, -13`; `-6` and `-7` also appear in non-priority 2015–16 columns. Code definitions were checked against each year's manual, and an independent second pass reproduced the code counts. All negative count and FTE values must be excluded from numeric calculations.
