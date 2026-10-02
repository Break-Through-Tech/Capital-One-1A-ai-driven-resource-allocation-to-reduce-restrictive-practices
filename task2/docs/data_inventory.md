# CRDC file inventory

This inventory lists the CSV files in the four downloaded CRDC packages, with their sizes and column counts. The CRDC data and manuals will be uploaded to the team Google Drive under the package names below. The [data audit](data_audit.md) describes the quality checks and relevant variables.

The row estimates use `line count − 1`. Blank lines and line breaks within quoted fields can make these differ from parsed CSV row counts. For example, 2017–18 `LEA Characteristics.csv` shows 17,615 here but parses to 17,604 rows (1 trailing blank line plus 10 line breaks inside quoted fields). Use a CSV reader for analysis counts. `COMBOKEY` and `LEAID` indicate whether the file includes those identifier columns.

Encoding: all 2020–21 and 2021–22 files are UTF-8. The 2015–16 files and 26 of the 33 CRDC CSVs in the 2017–18 package are `cp1252`; read with UTF-8 and fall back to `cp1252`.

## 2015–16

Package: `2015-16-crdc-data` (updated Sept 2018). One wide school file plus one LEA file.

| File | Rows | Cols | COMBOKEY | LEAID | Size (MB) |
|---|---:|---:|---|---|---:|
| `CRDC 2015-16 School Data.csv` | 96,360 | 1,836 | Y | Y | 465.0 |
| `CRDC 2015-16 LEA Data.csv` | 17,338 | 115 |  | Y | 11.5 |

Also includes record-layout CSVs and PDF manuals.

## 2017–18

Package: `2017-18-crdc-data-corrected-publication 2`. Split CRDC modules plus EDFacts extracts.

### LEA (CRDC)

| File | Rows | Cols | LEAID | Size (MB) |
|---|---:|---:|---|---:|
| `LEA Characteristics.csv` | 17,615 | 53 | Y | 8.6 |
| `Distance Education.csv` | 17,605 | 29 | Y | 2.8 |
| `High School Equivalency (GED).csv` | 17,605 | 29 | Y | 2.8 |

### School files used in the audit

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `Restraint and Seclusion.csv` | 97,633 | 131 | 35.4 |
| `Enrollment.csv` | 97,632 | 123 | 35.2 |
| `School Characteristics.csv` | 97,633 | 32 | 22.6 |
| `School Support.csv` | 97,633 | 22 | 17.5 |
| `School Expenditures.csv` | 97,633 | 27 | 25.3 |

### Other school files

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `Advanced Mathematics.csv` | 97,632 | 30 | 16.4 |
| `Advanced Placement.csv` | 97,632 | 134 | 47.1 |
| `Algebra I.csv` | 97,632 | 136 | 46.0 |
| `Algebra II.csv` | 97,632 | 30 | 16.4 |
| `Biology.csv` | 97,632 | 30 | 16.4 |
| `Calculus.csv` | 97,632 | 30 | 16.5 |
| `Chemistry.csv` | 97,632 | 30 | 16.4 |
| `Corporal Punishment.csv` | 97,632 | 71 | 28.8 |
| `Credit Recovery.csv` | 97,632 | 10 | 11.1 |
| `Dual Enrollment.csv` | 97,632 | 29 | 16.4 |
| `Expulsions.csv` | 97,632 | 142 | 38.1 |
| `Geometry.csv` | 97,632 | 32 | 17.2 |
| `Gifted and Talented.csv` | 97,632 | 29 | 15.7 |
| `Harassment and Bullying.csv` | 97,633 | 145 | 37.5 |
| `International Baccalaureate.csv` | 97,632 | 29 | 16.6 |
| `Justice Facilities.csv` | 97,633 | 16 | 12.8 |
| `Offenses.csv` | 97,632 | 22 | 11.7 |
| `Physics.csv` | 97,632 | 30 | 16.5 |
| `Referrals and Arrests.csv` | 97,633 | 84 | 25.4 |
| `Retention.csv` | 97,632 | 307 | 97.4 |
| `SAT and ACT.csv` | 97,632 | 28 | 15.7 |
| `Single-sex Athletics.csv` | 97,632 | 18 | 13.4 |
| `Single-sex Classes.csv` | 97,633 | 24 | 15.2 |
| `Suspensions.csv` | 97,633 | 189 | 49.5 |
| `Transfers.csv` | 97,632 | 46 | 17.8 |

### EDFacts (optional)

Different keys (`NCESLEAID`, `NCESSCH`). Incomplete overlap with CRDC schools.

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `ID 22 SCH - Title I Status.csv` | 103,548 | 9 | 11.5 |
| `ID 74 SCH - Educational Environment by Gender by Disability.csv` | 590,157 | 26 | 85.6 |
| `ID 74 SCH - Race by Placement.csv` | 260,628 | 17 | 33.8 |
| `ID 74 SCH - Race by Sex by Disability plus LEP_*.csv` (14 files) | 1k–88k | 44 | — |
| `ID 814 SCH - Chronic Absenteeism.csv` | 92,437 | 32 | 15.5 |

## 2020–21

Package: `2020-21-crdc-data`.

### LEA (CRDC)

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `LEA Characteristics.csv` | 17,822 | 34 | 7.2 |
| `Distance Education.csv` | 17,822 | 29 | 2.8 |
| `High School Equivalency.csv` | 17,822 | 29 | 2.9 |

### School files used in the audit

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `Restraint and Seclusion.csv` | 97,576 | 131 | 39.2 |
| `Enrollment.csv` | 97,576 | 118 | 35.5 |
| `School Characteristics.csv` | 97,576 | 32 | 22.6 |
| `School Support.csv` | 97,576 | 17 | 12.8 |
| `COVID Directional Indicators.csv` | 97,576 | 10 | 11.1 |

### Other school files

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `Advanced Mathematics.csv` | 97,576 | 30 | 16.4 |
| `Advanced Placement.csv` | 97,576 | 94 | 35.9 |
| `Algebra I.csv` | 97,576 | 136 | 45.9 |
| `Algebra II.csv` | 97,576 | 30 | 16.4 |
| `Biology.csv` | 97,576 | 30 | 16.4 |
| `Calculus.csv` | 97,576 | 30 | 16.5 |
| `Chemistry.csv` | 97,576 | 30 | 16.4 |
| `Computer Science.csv` | 97,576 | 30 | 16.5 |
| `Corporal Punishment.csv` | 97,576 | 71 | 29.7 |
| `Dual Enrollment.csv` | 97,576 | 29 | 16.4 |
| `Expulsions.csv` | 97,576 | 142 | 40.7 |
| `Geometry.csv` | 97,576 | 32 | 17.2 |
| `Gifted and Talented.csv` | 97,576 | 29 | 15.8 |
| `Harassment and Bullying.csv` | 97,576 | 145 | 40.9 |
| `International Baccalaureate.csv` | 97,576 | 29 | 16.6 |
| `Internet Access and Devices.csv` | 97,576 | 13 | 13.0 |
| `Justice Facilities.csv` | 97,576 | 16 | 12.8 |
| `Offenses.csv` | 97,576 | 19 | 13.2 |
| `Physics.csv` | 97,576 | 30 | 16.5 |
| `Referrals and Arrests.csv` | 97,576 | 84 | 27.4 |
| `Retention.csv` | 97,576 | 307 | 97.7 |
| `SAT and ACT.csv` | 97,576 | 28 | 15.8 |
| `Single sex Athletics.csv` | 97,576 | 18 | 13.4 |
| `Single sex Classes.csv` | 97,576 | 24 | 15.2 |
| `Suspensions.csv` | 97,576 | 169 | 46.9 |
| `Transfers.csv` | 97,576 | 46 | 18.6 |

### EDFacts (optional)

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `ID 814 SCH - Chronic Absenteeism.csv` | 92,375 | 30 | 14.9 |

## 2021–22

Package: `2021-22-crdc-data`. Recommended starting year for analysis.

### LEA (CRDC)

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `LEA Characteristics.csv` | 17,704 | 40 | 6.5 |
| `Distance Education.csv` | 17,704 | 29 | 2.8 |
| `High School Equivalency Exam.csv` | 17,704 | 29 | 2.9 |

### School files used in the audit

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `Restraint and Seclusion.csv` | 98,010 | 131 | 45.0 |
| `Enrollment.csv` | 98,010 | 233 | 69.5 |
| `School Characteristics.csv` | 98,010 | 34 | 23.7 |
| `School Support.csv` | 98,010 | 19 | 13.7 |
| `COVID Directional Indicators.csv` | 98,010 | 12 | 12.2 |

### Other school files

| File | Rows | Cols | Size (MB) |
|---|---:|---:|---:|
| `Advanced Mathematics.csv` | 98,010 | 29 | 16.1 |
| `Advanced Placement.csv` | 98,010 | 98 | 37.1 |
| `Algebra I.csv` | 98,010 | 132 | 45.0 |
| `Algebra II.csv` | 98,010 | 29 | 16.1 |
| `Biology.csv` | 98,010 | 29 | 16.1 |
| `Calculus.csv` | 98,010 | 29 | 16.2 |
| `Chemistry.csv` | 98,010 | 29 | 16.1 |
| `Computer Science.csv` | 98,010 | 29 | 16.2 |
| `Corporal Punishment.csv` | 98,010 | 72 | 29.4 |
| `Data Science.csv` | 98,010 | 10 | 10.8 |
| `Dual Enrollment.csv` | 98,010 | 29 | 16.4 |
| `Expulsions.csv` | 98,010 | 142 | 38.1 |
| `Geometry.csv` | 98,010 | 31 | 16.9 |
| `Gifted and Talented.csv` | 98,010 | 29 | 15.7 |
| `Harassment and Bullying.csv` | 98,010 | 159 | 40.3 |
| `International Baccalaureate.csv` | 98,010 | 31 | 17.2 |
| `Internet Access and Devices.csv` | 98,010 | 13 | 13.0 |
| `Interscholastic Athletics.csv` | 98,010 | 18 | 13.4 |
| `Justice Facilities.csv` | 98,010 | 16 | 12.9 |
| `Offenses.csv` | 98,010 | 33 | 16.3 |
| `Physics.csv` | 98,010 | 29 | 16.1 |
| `Referrals and Arrests.csv` | 98,010 | 84 | 25.4 |
| `Retention.csv` | 98,010 | 307 | 98.0 |
| `SAT and ACT.csv` | 98,010 | 28 | 15.7 |
| `Single Sex Classes.csv` | 98,010 | 21 | 14.4 |
| `Suspensions.csv` | 98,010 | 189 | 49.6 |
| `Transfers.csv` | 98,010 | 46 | 17.8 |
