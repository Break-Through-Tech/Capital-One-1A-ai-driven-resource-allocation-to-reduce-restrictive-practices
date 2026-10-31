"""Clean 2020-21 CRDC school and LEA files for seclusion analysis.

Follows the cleaning sequence in data_audit.md:
read as strings -> pad IDs / check COMBOKEY -> inner-join school modules on
COMBOKEY -> left-join LEA -> recode reserved codes to NA -> instance sum and
enrollment rate -> FTE and school-type flags.

2020-21 is the COVID year: seclusion reporting is incomplete (-11 DQ
suppression, -13 virtual-only skip). Use as a robustness / sensitivity
cohort, not as the primary modeling year.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

# Folder holding the 2020-21 CSVs (override with CRDC_2020_21_DIR).
DATA_DIR = Path(os.environ.get("CRDC_2020_21_DIR", "2020-21-crdc-data"))
CHAR_PATH = DATA_DIR / "School_Characteristics.csv"
ENR_PATH = DATA_DIR / "Enrollment.csv"
RS_PATH = DATA_DIR / "Restraint_and_Seclusion.csv"
SUP_PATH = DATA_DIR / "School_Support.csv"
DIND_PATH = DATA_DIR / "COVID_Directional_Indicators.csv"
LEA_PATH = DATA_DIR / "LEA_Characteristics.csv"
OUT_DIR = Path("cleaned")

# Reserved codes (2020-21 manual s5.4; audit "Reserved code definitions").
# Listed for 2020-21: -9, -13, -5, -6, -3, -4, -8, -11. Observed in the
# priority files: -9, -13, -5, -11. Any other negative value is still set to
# NA but reported as an unexpected code.
RESERVED_GROUPS = {
    -9: "structural_skip",
    -13: "structural_skip",
    -5: "missing",
    -6: "missing",
    -3: "missing",
    -4: "missing",
    -8: "missing",
    -11: "suppressed",
}

KEY_COLS = [
    "LEA_STATE",
    "LEA_STATE_NAME",
    "LEAID",
    "LEA_NAME",
    "SCHID",
    "SCH_NAME",
    "COMBOKEY",
    "JJ",
]

GRADE_COLS = [
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

STATUS_COLS = [
    "SCH_STATUS_SPED",
    "SCH_STATUS_MAGNET",
    "SCH_STATUS_CHARTER",
    "SCH_STATUS_ALT",
]

# Per-module columns. Key columns come from School Characteristics only; the
# other modules contribute COMBOKEY plus their own fields.
CHAR_COLS = KEY_COLS + GRADE_COLS + STATUS_COLS
ENR_COLS = [
    "TOT_ENR_M",
    "TOT_ENR_F",
    "SCH_ENR_LEP_M",
    "SCH_ENR_LEP_F",
    "SCH_ENR_504_M",
    "SCH_ENR_504_F",
    "SCH_ENR_IDEA_M",
    "SCH_ENR_IDEA_F",
]
SECL_INSTANCE_COLS = [
    "SCH_RSINSTANCES_SECL_WODIS",
    "SCH_RSINSTANCES_SECL_IDEA",
    "SCH_RSINSTANCES_SECL_504",
]
RS_COLS = SECL_INSTANCE_COLS + [
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
SUP_COLS = FTE_ALL_COLS
# COVID directional indicators are letter categories (A-D, B/C...) with reserved
# numeric codes mixed in, so they are recoded as categories, not numbers.
DIND_COLS = ["SCH_DIND_INSTRUCTIONTYPE", "SCH_DIND_VIRTUALTYPE"]

# Category labels from the 2020-21 Appendix Workbook, sheet "B. CRDC Data Dictionary".
INSTRUCTION_TYPE_LABELS = {
    "A": "in_person_only_with_safety_precautions",
    "B": "virtual_only",
    "C": "hybrid",
    "D": "no_effect_from_pandemic",
}
VIRTUAL_TYPE_LABELS = {
    "A": "students_in_school_teachers_remote",
    "B": "students_remote",
    "C": "both_a_and_b",
}
LEA_COLS = ["LEAID", "LEA_ENR", "LEA_SCHOOLS", "CJJ"]
LEA_NUM_COLS = ["LEA_ENR", "LEA_SCHOOLS"]

COUNT_FTE_COLS = ENR_COLS + RS_COLS + FTE_ALL_COLS + LEA_NUM_COLS

YES_NO_COLS = ["JJ"] + STATUS_COLS + GRADE_COLS


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


def recode_categorical(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Keep letter categories; move reserved codes (< 0) to *_code / *_reason.

    The original column is set to NA where the value is a reserved code or blank.
    """
    df = df.copy()
    extras = {}
    for col in cols:
        raw = df[col].astype(str).str.strip()
        num = pd.to_numeric(raw, errors="coerce")
        reserved = num.where(num < 0)
        extras[f"{col}_code"] = reserved
        extras[f"{col}_reason"] = reserved.map(RESERVED_GROUPS)
        df[col] = raw.where(num.isna() & raw.ne(""), np.nan)
    return pd.concat([df, pd.DataFrame(extras, index=df.index)], axis=1)


def unexpected_codes(df: pd.DataFrame, cols: list[str]) -> dict[int, int]:
    """Negative codes present in `cols` that are not in RESERVED_GROUPS."""
    found: dict[int, int] = {}
    for col in cols:
        codes = df[f"{col}_code"].dropna().astype(int)
        for code, n in codes[~codes.isin(RESERVED_GROUPS)].value_counts().items():
            found[int(code)] = found.get(int(code), 0) + int(n)
    return found


def yes_no_flag(series: pd.Series) -> pd.Series:
    return series.str.upper().eq("YES")


def prep_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Pad LEAID / SCHID; verify COMBOKEY = LEAID + SCHID (read as strings)."""
    df["LEAID"] = pad_id(df["LEAID"], 7)
    df["SCHID"] = pad_id(df["SCHID"], 5)
    df["COMBOKEY_stored"] = df["COMBOKEY"]
    df["COMBOKEY"] = pad_id(df["COMBOKEY"], 12)
    return df


def read_school_modules() -> tuple[pd.DataFrame, dict]:
    """Inner-join Characteristics + Enrollment + Restraint/Seclusion + Support."""
    char = prep_ids(read_crdc_csv(CHAR_PATH, CHAR_COLS))
    mods = {
        "Enrollment": read_crdc_csv(ENR_PATH, ["COMBOKEY"] + ENR_COLS),
        "Restraint_and_Seclusion": read_crdc_csv(RS_PATH, ["COMBOKEY"] + RS_COLS),
        "School_Support": read_crdc_csv(SUP_PATH, ["COMBOKEY"] + SUP_COLS),
        "COVID_Directional_Indicators": read_crdc_csv(DIND_PATH, ["COMBOKEY"] + DIND_COLS),
    }
    info = {"n_char": len(char), "key_mismatch": int((char["LEAID"] + char["SCHID"] != char["COMBOKEY"]).sum())}
    if char["COMBOKEY"].duplicated().any():
        raise ValueError("Duplicate COMBOKEY in School Characteristics")
    df = char
    for name, mod in mods.items():
        mod["COMBOKEY"] = pad_id(mod["COMBOKEY"], 12)
        if mod["COMBOKEY"].duplicated().any():
            raise ValueError(f"Duplicate COMBOKEY in {name}")
        info[f"{name}_not_in_char"] = int((~mod["COMBOKEY"].isin(char["COMBOKEY"])).sum())
        df = df.merge(mod, on="COMBOKEY", how="inner")
    info["n_joined"] = len(df)
    print(f"Inner join on COMBOKEY: {len(df):,} of {len(char):,} schools kept")
    return df, info


def clean() -> tuple[pd.DataFrame, dict]:
    sch, join_info = read_school_modules()
    lea = read_crdc_csv(LEA_PATH, LEA_COLS)
    lea["LEAID"] = pad_id(lea["LEAID"], 7)

    n_schools = len(sch)
    n_unique = sch["COMBOKEY"].nunique()
    print(f"COMBOKEY: {n_unique:,} unique keys from {n_schools:,} rows")
    if n_unique != n_schools:
        raise ValueError("COMBOKEY is not unique")

    lea_dup = lea["LEAID"].duplicated().sum()
    if lea_dup:
        raise ValueError(f"Duplicate LEAID in LEA file: {lea_dup}")

    unmatched = ~sch["LEAID"].isin(lea["LEAID"])
    print(f"Schools with no LEA match: {int(unmatched.sum()):,}")

    df = sch.merge(lea, on="LEAID", how="left", suffixes=("", "_lea"))

    df = recode_reserved(df, COUNT_FTE_COLS)
    df = recode_categorical(df, DIND_COLS)
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

    # FTE plausibility. Reserved codes are already NA. 2020-21 has no 999
    # placeholder pattern (that is 2015-16); implausible values such as 833
    # nurses at one school are caught by the per-student checks.
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
    # Virtual-only schools were skipped (-13) on the restraint/seclusion module.
    extra["flag_virtual_only_skip"] = df["SCH_RSINSTANCES_SECL_WODIS_code"].eq(-13)
    # COVID instruction indicators: keep the letters as reported and add labels.
    # SCH_DIND_VIRTUALTYPE is -13 (structural skip) for every school whose
    # instruction type is A or D, i.e. schools with no virtual instruction.
    extra["covid_instruction_type"] = df["SCH_DIND_INSTRUCTIONTYPE"].map(INSTRUCTION_TYPE_LABELS)
    extra["covid_virtual_type"] = df["SCH_DIND_VIRTUALTYPE"].map(VIRTUAL_TYPE_LABELS)
    extra["flag_covid_virtual_only"] = df["SCH_DIND_INSTRUCTIONTYPE"].eq("B")
    extra["flag_covid_hybrid"] = df["SCH_DIND_INSTRUCTIONTYPE"].eq("C")
    extra["flag_dind_virtual_skip"] = df["SCH_DIND_VIRTUALTYPE_code"].eq(-13)
    extra["flag_dind_missing"] = (
        df["SCH_DIND_INSTRUCTIONTYPE"].isna() | df["SCH_DIND_VIRTUALTYPE"].isna()
    )
    extra["year"] = "2020-21"
    df = pd.concat([df, pd.DataFrame(extra, index=df.index)], axis=1)

    jj = df["flag_jj"]
    report = {
        "n_schools": n_schools,
        "unique_combokey": n_unique,
        "unmatched_lea": int(unmatched.sum()),
        "key_mismatch": join_info["key_mismatch"],
        "rows_lost_in_join": join_info["n_char"] - join_info["n_joined"],
        "jj_yes": int(jj.sum()),
        "seclusion_all_three_valid": int(secl_valid.sum()),
        "wodis_neg9": int((df["SCH_RSINSTANCES_SECL_WODIS_code"] == -9).sum()),
        "wodis_neg11": int((df["SCH_RSINSTANCES_SECL_WODIS_code"] == -11).sum()),
        "wodis_neg13": int((df["SCH_RSINSTANCES_SECL_WODIS_code"] == -13).sum()),
        "wodis_neg5": int((df["SCH_RSINSTANCES_SECL_WODIS_code"] == -5).sum()),
        "wodis_positive": int((df["SCH_RSINSTANCES_SECL_WODIS"] > 0).sum()),
        "idea_positive": int((df["SCH_RSINSTANCES_SECL_IDEA"] > 0).sum()),
        "enr_m_usable": int(df["TOT_ENR_M"].notna().sum()),
        "enr_f_usable": int(df["TOT_ENR_F"].notna().sum()),
        "enr_m_neg11": int((df["TOT_ENR_M_code"] == -11).sum()),
        "enr_f_neg11": int((df["TOT_ENR_F_code"] == -11).sum()),
        "enr_m_zero": int((df["TOT_ENR_M"] == 0).sum()),
        "enr_sum_zero": int((df["enrollment"] == 0).sum()),
        "jj_security_gua_neg9": int((df.loc[jj, "SCH_FTESECURITY_GUA_code"] == -9).sum()),
        "fte_outlier_rows": int(df["flag_fte_outlier"].sum()),
        "dind_instruction_neg3": int((df["SCH_DIND_INSTRUCTIONTYPE_code"] == -3).sum()),
        "dind_virtual_neg13": int((df["SCH_DIND_VIRTUALTYPE_code"] == -13).sum()),
        "dind_virtual_neg3": int((df["SCH_DIND_VIRTUALTYPE_code"] == -3).sum()),
        "dind_neg13_not_AD": int(
            (df["flag_dind_virtual_skip"] & ~df["SCH_DIND_INSTRUCTIONTYPE"].isin(["A", "D"])).sum()
        ),
        "secl_neg13_not_virtual_only": int(
            (df["flag_virtual_only_skip"] & ~df["flag_covid_virtual_only"]).sum()
        ),
        "unexpected_codes": unexpected_codes(df, COUNT_FTE_COLS + DIND_COLS),
    }
    return df, report


def print_audit_checks(report: dict) -> None:
    expected = {
        "n_schools": 97575,
        "unique_combokey": 97575,
        "jj_yes": 579,
        "seclusion_all_three_valid": 76546,
        "wodis_neg9": 1875,
        "wodis_neg11": 14158,
        "wodis_neg13": 4700,
        "wodis_neg5": 288,
        "wodis_positive": 1327,
        "idea_positive": 4037,
        "enr_m_usable": 97014,
        "enr_f_usable": 97015,
        "enr_m_neg11": 561,
        "enr_f_neg11": 560,
        "enr_m_zero": 247,
        "enr_sum_zero": 0,
        "unmatched_lea": 0,
        "key_mismatch": 0,
        "rows_lost_in_join": 0,
    }
    print("\nAudit checks (expected vs observed)")
    for key, exp in expected.items():
        obs = report[key]
        status = "OK" if obs == exp else "DIFF"
        print(f"  {status:4} {key}: expected {exp:,}  observed {obs:,}")
    print(
        f"  info JJ schools with security guard FTE = -9: "
        f"{report['jj_security_gua_neg9']:,} (audit: 573 of 579)"
    )
    print(
        f"  info DIND instruction -3: {report['dind_instruction_neg3']:,}; "
        f"virtual -13: {report['dind_virtual_neg13']:,}; "
        f"virtual -3: {report['dind_virtual_neg3']:,}"
    )
    print(
        f"  info DIND virtual -13 where instruction type is not A/D: "
        f"{report['dind_neg13_not_AD']:,} (expect 0)"
    )
    print(
        f"  info seclusion -13 where instruction type is not B (virtual only): "
        f"{report['secl_neg13_not_virtual_only']:,} (expect 0)"
    )
    print(f"  info fte_outlier rows: {report['fte_outlier_rows']:,}")
    print(f"  info negative codes outside the 2020-21 set: {report['unexpected_codes'] or 'none'}")


def main() -> None:
    df, report = clean()
    print_audit_checks(report)
    OUT_DIR.mkdir(exist_ok=True)
    out_csv = OUT_DIR / "crdc_2020_21_analysis_ready.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv} ({len(df):,} rows, {df.shape[1]} columns)")


if __name__ == "__main__":
    main()
