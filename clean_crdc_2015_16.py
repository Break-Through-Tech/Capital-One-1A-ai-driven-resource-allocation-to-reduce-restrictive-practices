"""Clean 2015-16 CRDC school and LEA files for seclusion analysis.

Follows the cleaning sequence in data_audit.md:
read as strings -> pad IDs / rebuild COMBOKEY -> join LEA -> recode reserved
codes to NA -> instance sum and enrollment rate -> FTE and school-type flags.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path("2015-16-crdc-data") / "Data Files and Layouts"
SCH_PATH = DATA_DIR / "CRDC 2015-16 School Data.csv"
LEA_PATH = DATA_DIR / "CRDC 2015-16 LEA Data.csv"
OUT_DIR = Path("cleaned")

RESERVED_GROUPS = {
    -9: "structural_skip",
    -13: "structural_skip",
    -5: "missing",
    -6: "missing",
    -3: "missing",
    -4: "missing",
    -7: "missing",
    -8: "missing",
    -2: "suppressed",
    -11: "suppressed",
    -12: "suppressed",
}

SCH_COLS = [
    "LEA_STATE",
    "LEA_STATE_NAME",
    "LEAID",
    "LEA_NAME",
    "SCHID",
    "SCH_NAME",
    "COMBOKEY",
    "JJ",
    "SCH_GRADE_PS",
    "SCH_GRADE_KG",
    "SCH_GRADE_G01",
    "SCH_GRADE_G02",
    "SCH_GRADE_G03",
    "SCH_GRADE_G04",
    "SCH_GRADE_G05",
    "SCH_GRADE_G06",
    "SCH_GRADE_G07",
    "SCH_GRADE_G08",
    "SCH_GRADE_G09",
    "SCH_GRADE_G10",
    "SCH_GRADE_G11",
    "SCH_GRADE_G12",
    "SCH_GRADE_UG",
    "SCH_STATUS_SPED",
    "SCH_STATUS_MAGNET",
    "SCH_STATUS_CHARTER",
    "SCH_STATUS_ALT",
    "TOT_ENR_M",
    "TOT_ENR_F",
    "SCH_ENR_LEP_M",
    "SCH_ENR_LEP_F",
    "SCH_ENR_504_M",
    "SCH_ENR_504_F",
    "SCH_ENR_IDEA_M",
    "SCH_ENR_IDEA_F",
    "SCH_RSINSTANCES_SECL_WODIS",
    "SCH_RSINSTANCES_SECL_IDEA",
    "SCH_RSINSTANCES_SECL_504",
    "SCH_RSINSTANCES_MECH_WODIS",
    "SCH_RSINSTANCES_MECH_IDEA",
    "SCH_RSINSTANCES_MECH_504",
    "SCH_RSINSTANCES_PHYS_WODIS",
    "SCH_RSINSTANCES_PHYS_IDEA",
    "SCH_RSINSTANCES_PHYS_504",
    "TOT_RS_NONIDEA_SECL_M",
    "TOT_RS_NONIDEA_SECL_F",
    "TOT_RS_IDEA_SECL_M",
    "TOT_RS_IDEA_SECL_F",
    "SCH_FTETEACH_TOT",
    "SCH_FTETEACH_CERT",
    "SCH_FTECOUNSELORS",
    "SCH_FTESECURITY_LEO",
    "SCH_FTESECURITY_GUA",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
]

LEA_COLS = ["LEAID", "LEA_ENR", "LEA_SCHOOLS", "CJJ"]

COUNT_FTE_COLS = [
    "TOT_ENR_M",
    "TOT_ENR_F",
    "SCH_ENR_LEP_M",
    "SCH_ENR_LEP_F",
    "SCH_ENR_504_M",
    "SCH_ENR_504_F",
    "SCH_ENR_IDEA_M",
    "SCH_ENR_IDEA_F",
    "SCH_RSINSTANCES_SECL_WODIS",
    "SCH_RSINSTANCES_SECL_IDEA",
    "SCH_RSINSTANCES_SECL_504",
    "SCH_RSINSTANCES_MECH_WODIS",
    "SCH_RSINSTANCES_MECH_IDEA",
    "SCH_RSINSTANCES_MECH_504",
    "SCH_RSINSTANCES_PHYS_WODIS",
    "SCH_RSINSTANCES_PHYS_IDEA",
    "SCH_RSINSTANCES_PHYS_504",
    "TOT_RS_NONIDEA_SECL_M",
    "TOT_RS_NONIDEA_SECL_F",
    "TOT_RS_IDEA_SECL_M",
    "TOT_RS_IDEA_SECL_F",
    "SCH_FTETEACH_TOT",
    "SCH_FTETEACH_CERT",
    "SCH_FTECOUNSELORS",
    "SCH_FTESECURITY_LEO",
    "SCH_FTESECURITY_GUA",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
    "LEA_ENR",
    "LEA_SCHOOLS",
]

SECL_INSTANCE_COLS = [
    "SCH_RSINSTANCES_SECL_WODIS",
    "SCH_RSINSTANCES_SECL_IDEA",
    "SCH_RSINSTANCES_SECL_504",
]

FTE_PLACEHOLDER_COLS = [
    "SCH_FTECOUNSELORS",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
]

FTE_ALL_COLS = [
    "SCH_FTETEACH_TOT",
    "SCH_FTETEACH_CERT",
    "SCH_FTECOUNSELORS",
    "SCH_FTESECURITY_LEO",
    "SCH_FTESECURITY_GUA",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
]

YES_NO_COLS = [
    "JJ",
    "SCH_STATUS_SPED",
    "SCH_STATUS_MAGNET",
    "SCH_STATUS_CHARTER",
    "SCH_STATUS_ALT",
    "SCH_GRADE_PS",
    "SCH_GRADE_KG",
    "SCH_GRADE_G01",
    "SCH_GRADE_G02",
    "SCH_GRADE_G03",
    "SCH_GRADE_G04",
    "SCH_GRADE_G05",
    "SCH_GRADE_G06",
    "SCH_GRADE_G07",
    "SCH_GRADE_G08",
    "SCH_GRADE_G09",
    "SCH_GRADE_G10",
    "SCH_GRADE_G11",
    "SCH_GRADE_G12",
    "SCH_GRADE_UG",
]


def read_crdc_csv(path: Path, usecols: list[str]) -> pd.DataFrame:
    """Read a CRDC CSV as strings; UTF-8 first, then cp1252."""
    kwargs = dict(
        dtype=str,
        keep_default_na=False,
        usecols=usecols,
        skip_blank_lines=True,
    )
    try:
        df = pd.read_csv(path, encoding="utf-8", **kwargs)
        encoding_used = "utf-8"
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp1252", **kwargs)
        encoding_used = "cp1252"
    print(f"Read {path.name}: {len(df):,} rows, encoding={encoding_used}")
    df.columns = df.columns.str.strip()
    df = df.apply(lambda s: s.str.strip() if s.dtype == object else s)
    empty = df.eq("").all(axis=1)
    if empty.any():
        print(f"  Dropped {int(empty.sum()):,} empty trailing rows")
        df = df.loc[~empty].copy()
    return df


def pad_id(series: pd.Series, width: int) -> pd.Series:
    digits = series.str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True)
    return digits.str.zfill(width)


def recode_reserved(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """pd.to_numeric, set value < 0 to NA, keep original code and reason group."""
    recoded = {}
    extras = {}
    for col in cols:
        num = pd.to_numeric(df[col], errors="coerce")
        reserved = num.where(num < 0)
        recoded[col] = num.where(num >= 0)
        extras[f"{col}_code"] = reserved
        extras[f"{col}_reason"] = reserved.map(RESERVED_GROUPS)
    df = df.copy()
    df[list(recoded)] = pd.DataFrame(recoded, index=df.index)
    return pd.concat([df, pd.DataFrame(extras, index=df.index)], axis=1)


def yes_no_flag(series: pd.Series) -> pd.Series:
    return series.str.upper().eq("YES")


def clean() -> tuple[pd.DataFrame, dict]:
    sch = read_crdc_csv(SCH_PATH, SCH_COLS)
    lea = read_crdc_csv(LEA_PATH, LEA_COLS)

    sch["COMBOKEY_stored"] = sch["COMBOKEY"]
    sch["LEAID"] = pad_id(sch["LEAID"], 7)
    sch["SCHID"] = pad_id(sch["SCHID"], 5)
    sch["COMBOKEY"] = sch["LEAID"] + sch["SCHID"]
    lea["LEAID"] = pad_id(lea["LEAID"], 7)

    n_schools = len(sch)
    n_unique = sch["COMBOKEY"].nunique()
    n_stored_unique = sch["COMBOKEY_stored"].nunique()
    print(f"Rebuilt COMBOKEY: {n_unique:,} unique keys from {n_schools:,} rows")
    print(f"Stored COMBOKEY unique values: {n_stored_unique:,}")
    if n_unique != n_schools:
        raise ValueError("Rebuilt COMBOKEY is not unique")

    lea_dup = lea["LEAID"].duplicated().sum()
    if lea_dup:
        raise ValueError(f"Duplicate LEAID in LEA file: {lea_dup}")

    unmatched = ~sch["LEAID"].isin(lea["LEAID"])
    print(f"Schools with no LEA match: {int(unmatched.sum()):,}")

    df = sch.merge(lea, on="LEAID", how="left", suffixes=("", "_lea"))

    df = recode_reserved(df, COUNT_FTE_COLS)
    extra = {}

    secl_valid = df[SECL_INSTANCE_COLS].notna().all(axis=1)
    extra["seclusion_instances"] = np.where(
        secl_valid, df[SECL_INSTANCE_COLS].sum(axis=1), np.nan
    )
    wodis_code = df["SCH_RSINSTANCES_SECL_WODIS_code"]
    idea_code = df["SCH_RSINSTANCES_SECL_IDEA_code"]
    s504_code = df["SCH_RSINSTANCES_SECL_504_code"]
    extra["seclusion_reason_code"] = wodis_code.fillna(idea_code).fillna(s504_code)
    extra["seclusion_reason"] = extra["seclusion_reason_code"].map(RESERVED_GROUPS)

    enr_valid = df["TOT_ENR_M"].notna() & df["TOT_ENR_F"].notna()
    extra["enrollment"] = np.where(enr_valid, df["TOT_ENR_M"] + df["TOT_ENR_F"], np.nan)
    extra["seclusion_rate_per_100"] = np.where(
        (extra["enrollment"] > 0) & secl_valid,
        100.0 * extra["seclusion_instances"] / extra["enrollment"],
        np.nan,
    )
    extra["flag_missing_seclusion"] = ~secl_valid
    extra["flag_missing_enrollment"] = ~enr_valid
    extra["flag_zero_enrollment"] = extra["enrollment"] == 0
    extra["flag_rate_undefined"] = (
        extra["flag_missing_seclusion"]
        | extra["flag_missing_enrollment"]
        | extra["flag_zero_enrollment"]
    )

    enrollment = extra["enrollment"]
    for prefix, m_col, f_col in [
        ("idea", "SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F"),
        ("sec504", "SCH_ENR_504_M", "SCH_ENR_504_F"),
        ("lep", "SCH_ENR_LEP_M", "SCH_ENR_LEP_F"),
        ("secl_students_nonidea", "TOT_RS_NONIDEA_SECL_M", "TOT_RS_NONIDEA_SECL_F"),
        ("secl_students_idea", "TOT_RS_IDEA_SECL_M", "TOT_RS_IDEA_SECL_F"),
    ]:
        both = df[m_col].notna() & df[f_col].notna()
        extra[f"{prefix}_n"] = np.where(both, df[m_col] + df[f_col], np.nan)
        if prefix in {"idea", "sec504", "lep"}:
            extra[f"{prefix}_share"] = np.where(
                enrollment > 0, extra[f"{prefix}_n"] / enrollment, np.nan
            )

    extra["flag_fte_placeholder_999"] = False
    fte_updates = {}
    for col in FTE_PLACEHOLDER_COLS:
        is_999 = df[col].eq(999)
        extra[f"{col}_placeholder_999"] = is_999
        extra["flag_fte_placeholder_999"] = extra["flag_fte_placeholder_999"] | is_999
        updated = df[col].copy()
        updated.loc[is_999] = np.nan
        fte_updates[col] = updated
    df[list(fte_updates)] = pd.DataFrame(fte_updates, index=df.index)

    extra["flag_fte_outlier"] = False
    teacher_cols = {"SCH_FTETEACH_TOT", "SCH_FTETEACH_CERT"}
    for col in FTE_ALL_COLS:
        per_100 = np.where(enrollment > 0, 100.0 * df[col] / enrollment, np.nan)
        extra[f"{col}_per_100"] = per_100
        exceeds_enrollment = (
            df[col].notna() & pd.notna(enrollment) & (df[col] > enrollment)
        )
        cap = 50 if col in teacher_cols else 20
        high_per_student = df[col].notna() & (per_100 > cap)
        outlier = exceeds_enrollment | high_per_student
        extra[f"{col}_outlier"] = outlier
        extra["flag_fte_outlier"] = extra["flag_fte_outlier"] | outlier.fillna(False)

    extra["flag_jj"] = yes_no_flag(df["JJ"])
    extra["flag_sped"] = yes_no_flag(df["SCH_STATUS_SPED"])
    extra["flag_charter"] = yes_no_flag(df["SCH_STATUS_CHARTER"])
    extra["flag_alt"] = yes_no_flag(df["SCH_STATUS_ALT"])
    extra["flag_magnet"] = yes_no_flag(df["SCH_STATUS_MAGNET"])
    extra["flag_small_enrollment"] = pd.notna(enrollment) & (enrollment < 50)
    extra["year"] = "2015-16"
    df = pd.concat([df, pd.DataFrame(extra, index=df.index)], axis=1)

    report = {
        "n_schools": n_schools,
        "unique_combokey": n_unique,
        "stored_combokey_unique": n_stored_unique,
        "unmatched_lea": int(unmatched.sum()),
        "jj_yes": int(df["flag_jj"].sum()),
        "seclusion_all_three_valid": int(secl_valid.sum()),
        "wodis_neg9": int((df["SCH_RSINSTANCES_SECL_WODIS_code"] == -9).sum()),
        "wodis_neg5": int((df["SCH_RSINSTANCES_SECL_WODIS_code"] == -5).sum()),
        "wodis_positive": int((df["SCH_RSINSTANCES_SECL_WODIS"] > 0).sum()),
        "idea_positive": int((df["SCH_RSINSTANCES_SECL_IDEA"] > 0).sum()),
        "enr_m_usable": int(df["TOT_ENR_M"].notna().sum()),
        "enr_f_usable": int(df["TOT_ENR_F"].notna().sum()),
        "enr_m_zero": int((df["TOT_ENR_M"] == 0).sum()),
        "enr_sum_zero": int((df["enrollment"] == 0).sum()),
        "fte_placeholder_rows": int(df["flag_fte_placeholder_999"].sum()),
        "fte_outlier_rows": int(df["flag_fte_outlier"].sum()),
    }
    return df, report


def print_audit_checks(report: dict) -> None:
    expected = {
        "n_schools": 96360,
        "unique_combokey": 96360,
        "jj_yes": 608,
        "seclusion_all_three_valid": 93966,
        "wodis_neg9": 1806,
        "wodis_neg5": 588,
        "wodis_positive": 1876,
        "idea_positive": 4489,
        "enr_m_usable": 96359,
        "enr_f_usable": 96359,
        "enr_m_zero": 259,
        "enr_sum_zero": 0,
    }
    print("\nAudit checks (expected vs observed)")
    for key, exp in expected.items():
        obs = report[key]
        status = "OK" if obs == exp else "DIFF"
        print(f"  {status:4} {key}: expected {exp:,}  observed {obs:,}")
    print(
        f"  info stored_combokey_unique: {report['stored_combokey_unique']:,} "
        "(audit: 29,374 distinct stored values)"
    )
    print(f"  info unmatched_lea: {report['unmatched_lea']:,} (audit: 0)")
    print(f"  info fte_placeholder_999 rows: {report['fte_placeholder_rows']:,}")
    print(f"  info fte_outlier rows: {report['fte_outlier_rows']:,}")


def main() -> None:
    df, report = clean()
    print_audit_checks(report)
    OUT_DIR.mkdir(exist_ok=True)
    out_csv = OUT_DIR / "crdc_2015_16_analysis_ready.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv} ({len(df):,} rows, {df.shape[1]} columns)")


if __name__ == "__main__":
    main()
