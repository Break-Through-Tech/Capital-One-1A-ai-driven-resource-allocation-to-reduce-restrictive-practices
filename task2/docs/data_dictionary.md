# CRDC data dictionary (project subset)

This dictionary lists fields relevant to seclusion, enrollment, school characteristics, and staffing. For the complete codebook, refer to each year’s public-use file manual and data-element documentation.

Related documents: [data_audit.md](data_audit.md) (quality issues, join keys, missingness) and [data_inventory.md](data_inventory.md) (full file list). Abbreviations (LEA, JJ, FTE, IDEA, WODIS, EL/LEP, DIND) are defined at the top of the audit.

Types in the raw CSVs: identifiers and Yes/No flags are read as strings. Count and FTE fields contain numeric values and negative reserved codes. After cleaning, counts/FTEs should be nullable floats; flags can stay categorical Yes/No.

## Reserved codes (all numeric fields)

Public-use files almost never use blank cells for “missing.” Recode every value &lt; 0 to NA before analysis and keep the original code in a companion column so the reason stays available. Do not interpret reserved codes as counts.

The definitions below come from each year's manual. The 2015–16 and 2017–18 manuals are included in their dataset packages; the 2020–21 and 2021–22 downloads do not include a manual, so use the online versions.

- 2015–16 CRDC Public-Use Data File Manual, Table 2, p. 18 (section 6.1.2; included in the 2015–16 package).
- 2017–18 CRDC Public Data File Manual, Table 2, p. 12 (section 5.1.1); [ED-hosted manual](https://eddataexpress.ed.gov/sites/default/files/resource_data_files/2017-18_CRDC_Public-Use_Data_File_Manual.pdf).
- [2020–21 CRDC Data File User's Manual](https://ocrdata.ed.gov/assets/downloads/2020-21%20User%27s%20Manual.pdf), section 5.4, p. 12.
- [2021–22 CRDC Data File User's Manual](https://civilrightsdata.ed.gov/assets/downloads/2021-22%20User%27s%20Manual.pdf), Table 1, p. 12.

| Code | Definition | Group | 2015–16 | 2017–18 | 2020–21 | 2021–22 |
|---:|---|---|---|---|---|---|
| `-9` | Not Applicable / Skipped | Structural skip | Listed | Listed | Listed | Listed |
| `-13` | Missing DIND (COVID directional indicator) skip logic | Structural skip | — | — | Listed | Listed |
| `-5` | Action Plan (Action Plan / Quick Plans from 2020–21) | Missing | Listed | Listed | Listed | Listed |
| `-6` | Force Certified | Missing | Listed | Listed | Listed | Listed |
| `-3` | Skip Logic Failure (Skip Logic or Processing Failure in 2021–22) | Missing | — | Listed | Listed | Listed |
| `-4` | Missing Optional Data | Missing | — | — | Listed | Listed |
| `-7` | System Error | Missing | Listed | — | — | — |
| `-8` | EDFacts Missing Data | Missing | Listed | Listed | Listed | — |
| `-2` | Small Cell Value | Suppressed | Listed | — | — | — |
| `-11` | Suppressed Data (data quality suppression) | Suppressed | — | Listed | Listed | — |
| `-12` | Suppressed for Privacy Protections | Suppressed | — | — | — | Listed |

"—" means the code is not listed in that year's manual. Where each code actually occurs is summarized in the audit's [observed codes table](data_audit.md#observed-codes-in-the-priority-files).

`0` after this recode means the school reported zero, not “unknown.”

## Join keys and identification

These fields identify schools and districts across the CRDC school files.

| Field | Type | Years | Description | Cleaning notes |
|---|---|---|---|---|
| `COMBOKEY` | string, 12 chars | all | `LEAID` (7) + `SCHID` (5). Primary school key. | Read as string. Rebuild for 2015–16 from padded LEA+SCH. Do not parse scientific notation. |
| `LEAID` | string, 7 chars | all | NCES local education agency (district) ID | `zfill(7)`. Join to LEA file. Not unique on school files (many schools per LEA). |
| `SCHID` | string, 5 chars | all school files | School ID within the LEA | `zfill(5)`. Not nationally unique. Ignore this column on 2017–18 Restraint and Seclusion (wrong values); that file’s `COMBOKEY` is fine. |
| `LEA_STATE` | string | all | State/territory abbreviation | 2015–16: 51 (no PR). Later years: 52 including `PR`. |
| `LEA_STATE_NAME` | string | all | State/territory name | |
| `LEA_NAME` | string | all | District name | |
| `SCH_NAME` | string | school files | School name | |
| `JJ` | Yes/No | school files | Long-term juvenile justice facility | Yes count: 608 (2015–16), 602 (2017–18), 579 (2020–21), 882 (2021–22). Security FTE is `-9` for JJ schools in 2020–21 and 2021–22. |
| `CJJ` | Yes/No | LEA files | LEA contains at least one JJ facility | |

EDFacts extracts use `NCESLEAID`, `NCESSCH`, `SCHOOL_NAME` instead. Map `NCESSCH` → `COMBOKEY` only after padding and a coverage check.

## Outcome: restraint and seclusion

File: `Restraint and Seclusion.csv` (wide 2015–16 school file for that year). 131 columns in 2017–18 through 2021–22.

### Incident counts

These are numbers of incidents, not unique students. Incidents can exceed enrollment.

| Field | Type | Years | Description | Relevance |
|---|---|---|---|---|
| `SCH_RSINSTANCES_SECL_WODIS` | count | all four | Seclusion instances, students without disabilities | Component of total seclusion instances |
| `SCH_RSINSTANCES_SECL_IDEA` | count | all four | Seclusion instances, students with disabilities (IDEA) | Component of total seclusion instances |
| `SCH_RSINSTANCES_SECL_504` | count | all four | Seclusion instances, students with Section 504 only | Component of total seclusion instances |
| `SCH_RSINSTANCES_MECH_WODIS` / `_IDEA` / `_504` | count | all four | Mechanical restraint instances | Related restrictive practice; not the stated primary target |
| `SCH_RSINSTANCES_PHYS_WODIS` / `_IDEA` / `_504` | count | all four | Physical restraint instances | Same |

Proposed derived outcome (cleaning): if all three seclusion instance fields are non-reserved,
`seclusion_instances = WODIS + IDEA + 504`.
If any is reserved, set the sum to NA (do not treat missing parts as 0).
Rate: `100 * seclusion_instances / enrollment_total`.
Do not assume WODIS+IDEA+504 is a valid partition until the year manual is checked.

### Student counts subjected to seclusion (secondary)

Pattern: race (`HI, AM, AS, HP, BL, WH, TR`) × sex (`M, F`) plus calculated totals.

| Field pattern | Description | Notes |
|---|---|---|
| `SCH_RS_NONIDEA_SECL_*` | Students without IDEA subjected to seclusion | Subgroup counts; not additive with IDEA rows into a “total students” without care |
| `TOT_RS_NONIDEA_SECL_M` / `_F` | Calculated non-IDEA seclusion student totals | 2021–22: `-9` for ~95k schools (mostly filled only where instances exist) |
| `SCH_RS_IDEA_SECL_*` | Students with IDEA subjected to seclusion | |
| `TOT_RS_IDEA_SECL_M` / `_F` | Calculated IDEA seclusion student totals | |
| `SCH_RS_*_SECL_LEP_*` | LEP students subjected to seclusion | 2015–16 through 2020–21 |
| `SCH_RS_*_SECL_EL_*` | English learner students subjected to seclusion | 2021–22 name change (replaces LEP) |
| `SCH_RS_NONIDEA_SECL_504_*` | Section 504-only, among non-IDEA seclusion students | Counts students, whereas `SCH_RSINSTANCES_SECL_504` counts incidents |

Same patterns exist for mechanical (`_MECH_`) and physical (`_PHYS_`) restraint.

Do not add race cells together if a total column already exists. Do not add IDEA + non-IDEA student counts into the incident-based target.

## Enrollment (denominators and composition)

File: `Enrollment.csv` (2015–16: columns in the wide school file).

| Field | Type | Years | Description | Relevance |
|---|---|---|---|---|
| `TOT_ENR_M` | count | all | Calculated male enrollment | Component of total enrollment |
| `TOT_ENR_F` | count | all | Calculated female enrollment | Component of total enrollment |
| `TOT_ENR_X` | count | 2021–22 only | Nonbinary enrollment | Usually `-9` or `-12`; include in the denominator only when ≥ 0 |
| `SCH_ENR_{race}_{sex}` | count | all | Enrollment by race and sex | Composition / equity description |
| `SCH_ENR_*_X` | count | 2021–22 only | Nonbinary by race and disability | Same suppression pattern as `TOT_ENR_X` |
| `SCH_ENR_IDEA_M` / `_F` / `_X` | count | all (`_X` 2021–22) | IDEA enrollment | Share of students with IEPs |
| `SCH_ENR_504_M` / `_F` / `_X` | count | all | Section 504-only enrollment | |
| `SCH_ENR_LEP_M` / `_F` | count | 2015–16–2020–21 | Limited English proficient | Use EL fields in 2021–22 |
| `SCH_ENR_EL_M` / `_F` / `_X` | count | 2021–22 | English learners | Replaces LEP |
| Preschool `SCH_PSENR_*` | count | all | Preschool enrollment | Usually exclude from K–12 seclusion rates unless the target includes PS |

Derived: `enrollment_total = TOT_ENR_M + TOT_ENR_F` plus `TOT_ENR_X` when valid. Recode reserved codes first, require both `TOT_ENR_M` and `TOT_ENR_F` to be valid, and treat a total of 0 as an undefined rate. 2015–16 IDEA counts use `-2` suppression (never recode `-2` to 0).

`TOT_*` columns are totals calculated by OCR, which treated reserved codes in the components as zero. A valid `TOT_ENR_M` can therefore hide missing race cells (2020–21 and 2021–22 manuals §5.5.2).

Race codes: `HI` Hispanic, `AM` American Indian/Alaska Native, `AS` Asian, `HP` Native Hawaiian/Pacific Islander, `BL` Black, `WH` White, `TR` two or more races.

## School characteristics

File: `School Characteristics.csv`.

| Field | Type | Years | Description | Relevance |
|---|---|---|---|---|
| `SCH_GRADE_PS` … `SCH_GRADE_G12`, `SCH_GRADE_UG` | Yes/No | all | Grades offered | Build elementary / middle / high / span |
| `SCH_UGDETAIL_ES` / `_MS` / `_HS` | Yes/No | all | Ungraded age bands | |
| `SCH_STATUS_SPED` | Yes/No | all | Special education school | Strong confounder for seclusion |
| `SCH_STATUS_MAGNET` | Yes/No | all | Magnet / magnet program | |
| `SCH_STATUS_CHARTER` | Yes/No | all | Charter | |
| `SCH_STATUS_ALT` | Yes/No | all | Alternative school | |
| `SCH_MAGNETDETAIL` | category | all | Magnet detail | |
| `SCH_ALTFOCUS` | category | all | Alternative-school focus | |
| `SCH_VIRT_IND` | Yes/No | 2021–22 | Virtual school | 2,496 Yes; expected low seclusion |
| `SCH_JUST_IND` | Yes/No | 2021–22 | Justice facility (duplicates `JJ`) | |

## School support / staffing (resources)

File: `School Support.csv`.

| Field | Type | Years | Description | Relevance |
|---|---|---|---|---|
| `SCH_FTETEACH_TOT` | FTE | all | Total teacher FTE | Resource / class-size proxy with enrollment |
| `SCH_FTETEACH_CERT` | FTE | all | Certified teachers | |
| `SCH_FTETEACH_NOTCERT` | FTE | all | Not certified | |
| `SCH_FTECOUNSELORS` | FTE | all | School counselors | Core resource feature |
| `SCH_FTESERVICES_NUR` | FTE | all | Nurses | Student-support resource |
| `SCH_FTESERVICES_PSY` | FTE | all | Psychologists | Student-support resource; 2017–18 max 19,048.6 |
| `SCH_FTESERVICES_SOC` | FTE | all | Social workers | Student-support resource |
| `SCH_FTESECURITY_LEO` | FTE | all | Law-enforcement officers | Context; often `-9` for JJ schools |
| `SCH_FTESECURITY_GUA` | FTE | all | Security guards | 2017–18 outliers > 20,000 FTE — treat as errors |
| `SCH_FTETEACH_FY` / `_SY` / `SCH_FTETEACH_ABSENT` | FTE | 2017–18 (and 2015–16 wide) | First-year, second-year, absent teachers | Teacher experience and absence measures |
| `SCH_TEACHERS_CURR_TOT` / `_PREV_TOT` | count | 2017–18 | Headcount current / previous year | |
| `TOT_TEACHERS_CURR_M` / `_F` | count | 2021–22 | Current teachers by sex | `-4` (missing optional data) for about 58k of 98,010 schools; not usable as a general feature |

Every FTE field has implausible values in every year (for example 280 counselors or exactly 100.0 FTE in several fields at one school). Check FTE per student before use; see the audit's data quality issue 8.

Derived (after NA recode): counselors per 100 students, teachers per 100 students, student-support FTE (nurse+psych+social worker) per 100 students. Use enrollment as the denominator, not LEA enrollment.

## LEA (district) characteristics

File: `LEA Characteristics.csv`.

| Field | Type | Years | Description | Relevance |
|---|---|---|---|---|
| `LEA_ENR` | count | all | District enrollment | District size |
| `LEA_SCHOOLS` | count | all | Number of public schools in the LEA | |
| `LEA_ENR_NONLEAFAC` | count | all | Students served in non-LEA facilities | |
| `LEA_PS_IND` | Yes/No | later years | Preschool indicator | |
| `LEA_DESEGPLAN` | Yes/No | all | Desegregation order/plan | Context only |
| `LEA_HBPOLICY_IND` | Yes/No | all | Harassment/bullying policy | Weak / administrative |
| Civil-rights coordinator fields | mixed | all | Names/emails in some years | Do not model; 2021–22 has `XLEA_*` companion suppression columns |

## Optional / year-specific resource and context files

| File | Years | Why it might matter | Caution |
|---|---|---|---|
| `School Expenditures.csv` | 2017–18 (columns also in 2015–16 wide file) | Reported school expenditures | Not in 2020–21 / 2021–22 packages |
| `COVID Directional Indicators.csv` | 2020–21, 2021–22 | Instruction/virtual mode | Needed if 2020–21 is used at all. Columns differ: 2020–21 `SCH_DIND_INSTRUCTIONTYPE`, `SCH_DIND_VIRTUALTYPE`; 2021–22 `SCH_DIND_INSTRUCTIONTYPE`, `SCH_DIND_REMOTETYPE`, `SCH_DIND_REMOTEAMOUNT`, `SCH_DIND_REMOTEPERCT` |
| `Internet Access and Devices.csv` | 2020–21, 2021–22 | Digital access | Peripheral to seclusion |
| `Justice Facilities.csv` | 2017–18+ | Extra JJ detail | Overlaps `JJ` |
| `Suspensions.csv`, `Expulsions.csv`, `Offenses.csv`, `Referrals and Arrests.csv`, `Corporal Punishment.csv` | all | Other discipline climate | Leakage risk as predictors of seclusion; OK for descriptive comparison |
| EDFacts ID 814 chronic absenteeism | 2017–18, 2020–21 | Attendance / engagement | Different key (`NCESSCH`); incomplete overlap |
| EDFacts ID 22 Title I | 2017–18 | Poverty proxy | Different record structure (103k rows) |
| EDFacts ID 74 disability environment | 2017–18 | Placement of students with disabilities | Multiple files with repeated school IDs; optional |

Course-taking, AP, gifted, SAT/ACT, athletics, and dual-enrollment modules are out of scope for the core seclusion–resource question unless a later research question needs them.

## Field-name changes across years

| Concept | 2015–16 / 2017–18 / 2020–21 | 2021–22 |
|---|---|---|
| English learners | `LEP` in field names | `EL` |
| Nonbinary enrollment / outcomes | (absent) | suffix `_X`, `TOT_ENR_X` |
| Virtual school | (absent as `SCH_VIRT_IND`) | `SCH_VIRT_IND` |
| Justice flag on characteristics | `JJ` only | `JJ` and `SCH_JUST_IND` |
| Teacher sex headcount | 2017–18 `SCH_TEACHERS_CURR_TOT` | `TOT_TEACHERS_CURR_M/F` |

When stacking years, rename `*_LEP_*` → a common `*_EL_*` (or the reverse) after confirming the definitions match.

## Proposed columns for analysis

Proposed school-level fields for 2021–22 and the 2017–18 comparison:

```text
year, COMBOKEY, LEAID, SCHID, LEA_STATE, SCH_NAME, LEA_NAME, JJ,
enrollment_total, enr_idea, enr_504, enr_el,
seclusion_instances, seclusion_instances_wodis, seclusion_instances_idea, seclusion_instances_504,
seclusion_rate_per_100,
sch_status_sped, sch_status_charter, sch_status_alt, sch_status_magnet, sch_virt_ind,
fte_teachers, fte_counselors, fte_nurses, fte_psych, fte_social, fte_leo, fte_guards,
counselors_per_100, support_fte_per_100,
lea_enrollment, lea_schools,
flag_missing_seclusion, flag_missing_enrollment, flag_small_enrollment,
seclusion_reason, enrollment_reason
```

The `*_reason` columns keep the original reserved code and its group (structural skip, missing, or suppressed) so the reason a value is missing stays available.
