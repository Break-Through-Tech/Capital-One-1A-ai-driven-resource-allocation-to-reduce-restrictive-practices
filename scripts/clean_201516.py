"""Clean 2015-16 CRDC school and LEA files into the shared 50-column format.

Usage (from the repository root):

    python scripts/clean_201516.py \
        --raw-dir data/raw/2015-16 --out-dir data/processed/201516 \
        --docs-dir docs/cleaning

Cleaning sequence (see data_audit.md):
read as strings -> pad IDs / rebuild COMBOKEY -> join LEA -> recode reserved
codes to NA -> build shared columns -> flags -> write outputs.

Outputs (all untracked by git except the docs):
    schools_201516.csv            every school, shared 50 columns
    schools_201516_analysis.csv   rows where flag_analysis_ready is True
    quality_detail_201516.csv     one row per changed / flagged value
    docs/cleaning/qa_201516.md
    docs/cleaning/mapping_201516.csv

Contents
    Part A: cleaning (constants, readers, recode, build_features, outputs)
    Part B: documentation writers (mapping file and QA report)
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "2015-16"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "processed" / "201516"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "cleaning"
SCH_FILE = "CRDC 2015-16 School Data.csv"
LEA_FILE = "CRDC 2015-16 LEA Data.csv"
YEAR = "2015-16"

# ---------------------------------------------------------------------------
# Part A: cleaning
# ---------------------------------------------------------------------------

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

GRADE_COLS = [
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
]
# Preschool and ungraded flags are read but left out of grade_band.
GRADE_EXTRA_COLS = ["SCH_GRADE_PS", "SCH_GRADE_UG"]

# Restraint columns (MECH / PHYS) are intentionally NOT read: the EDA found
# they leak the outcome (AUC 0.84 on their own in 2015-16).
SCH_COLS = (
    [
        "LEA_STATE",
        "LEAID",
        "LEA_NAME",
        "SCHID",
        "SCH_NAME",
        "COMBOKEY",
        "JJ",
        "SCH_STATUS_SPED",
        "SCH_STATUS_MAGNET",
        "SCH_STATUS_CHARTER",
        "SCH_STATUS_ALT",
    ]
    + GRADE_EXTRA_COLS
    + GRADE_COLS
    + [
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
        "SCH_FTETEACH_TOT",
        "SCH_FTECOUNSELORS",
        "SCH_FTESECURITY_LEO",
        "SCH_FTESECURITY_GUA",
        "SCH_FTESERVICES_NUR",
        "SCH_FTESERVICES_PSY",
        "SCH_FTESERVICES_SOC",
    ]
)
LEA_COLS = ["LEAID", "LEA_ENR", "LEA_SCHOOLS"]

SECL_COLS = {
    "SCH_RSINSTANCES_SECL_WODIS": "seclusion_instances_wodis",
    "SCH_RSINSTANCES_SECL_IDEA": "seclusion_instances_idea",
    "SCH_RSINSTANCES_SECL_504": "seclusion_instances_504",
}
FTE_COLS = {
    "SCH_FTETEACH_TOT": "fte_teachers",
    "SCH_FTECOUNSELORS": "fte_counselors",
    "SCH_FTESERVICES_NUR": "fte_nurses",
    "SCH_FTESERVICES_PSY": "fte_psych",
    "SCH_FTESERVICES_SOC": "fte_social",
    "SCH_FTESECURITY_LEO": "fte_leo",
    "SCH_FTESECURITY_GUA": "fte_guards",
}
# 999 in these four columns is a placeholder, not a real FTE.
FTE_PLACEHOLDER_COLS = [
    "SCH_FTECOUNSELORS",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
]
SUPPORT_FTE_COLS = ["fte_nurses", "fte_psych", "fte_social"]  # counselors not included
TEACHER_RAW_COLS = {"SCH_FTETEACH_TOT"}

ENROLLMENT_PARTS = {
    "enr_idea": ("SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F"),
    "enr_504": ("SCH_ENR_504_M", "SCH_ENR_504_F"),
    "enr_el": ("SCH_ENR_LEP_M", "SCH_ENR_LEP_F"),
}

COUNT_COLS = (
    ["TOT_ENR_M", "TOT_ENR_F"]
    + [c for pair in ENROLLMENT_PARTS.values() for c in pair]
    + list(SECL_COLS)
    + list(FTE_COLS)
    + ["LEA_ENR", "LEA_SCHOOLS"]
)

SMALL_ENROLLMENT_CUTOFF = 10  # shared playbook: under 10 students
FTE_CAP_PER_100_TEACHERS = 50
FTE_CAP_PER_100_OTHER = 20

# Shared 50-column output, in the order of AI_CONTEXT.md section A4.
OUTPUT_COLUMNS = [
    "year", "combokey", "leaid", "schid", "lea_state", "sch_name", "lea_name", "jj",
    "seclusion_instances_wodis", "seclusion_instances_idea", "seclusion_instances_504",
    "seclusion_instances",
    "enrollment_total", "enr_nonbinary", "enr_idea", "enr_504", "enr_el",
    "seclusion_rate",
    "sch_status_sped", "sch_status_charter", "sch_status_alt", "sch_status_magnet",
    "sch_virt_ind", "grade_band",
    "fte_teachers", "fte_counselors", "fte_nurses", "fte_psych", "fte_social",
    "fte_leo", "fte_guards",
    "counselors_per_100", "teachers_per_100", "support_fte_per_100",
    "pct_idea", "pct_504", "pct_el",
    "lea_enrollment", "lea_schools",
    "flag_missing_seclusion", "flag_missing_enrollment", "flag_small_enrollment",
    "flag_fte_outlier",
    "flag_partial_enrollment", "flag_partial_idea", "flag_partial_504", "flag_partial_el",
    "flag_missing_module", "flag_missing_lea", "flag_analysis_ready",
]

# Problem log columns, per AI_CONTEXT.md section A5.
QUALITY_COLUMNS = [
    "year", "source_file", "source_row", "combokey", "leaid", "raw_column",
    "raw_value", "issue", "action", "cleaned_value", "evidence",
]
LEA_RAW_COLS = {"LEA_ENR", "LEA_SCHOOLS"}


def read_crdc_csv(path: Path, usecols: list[str]) -> tuple[pd.DataFrame, dict]:
    """Read a CRDC CSV as strings; UTF-8 first, then cp1252."""
    kwargs = dict(dtype=str, keep_default_na=False, usecols=usecols, skip_blank_lines=True)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", **kwargs)
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp1252", **kwargs)
        encoding = "cp1252"
    df.columns = df.columns.str.strip()
    df = df.apply(lambda s: s.str.strip())
    parsed = len(df)
    df["_source_row"] = np.arange(len(df)) + 2  # file row, header = row 1
    empty = df.drop(columns="_source_row").eq("").all(axis=1)
    if empty.any():
        df = df.loc[~empty].copy()
    info = {
        "file": path.name,
        "encoding": encoding,
        "rows_parsed": parsed,
        "rows_kept": len(df),
        "sha256": sha256_of(path),
    }
    print(f"Read {path.name}: {parsed:,} rows, kept {len(df):,}, encoding={encoding}")
    return df, info


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pad_id(series: pd.Series, width: int) -> pd.Series:
    digits = series.str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True)
    return digits.str.zfill(width)


def build_keys_and_join(sch: pd.DataFrame, lea: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Pad IDs, rebuild COMBOKEY, left-join LEA on LEAID."""
    sch = sch.copy()
    lea = lea.copy().rename(columns={"_source_row": "_lea_row"})
    sch["COMBOKEY_stored"] = sch["COMBOKEY"]
    sch["LEAID"] = pad_id(sch["LEAID"], 7)
    sch["SCHID"] = pad_id(sch["SCHID"], 5)
    sch["COMBOKEY"] = sch["LEAID"] + sch["SCHID"]
    lea["LEAID"] = pad_id(lea["LEAID"], 7)

    n_schools = len(sch)
    n_unique = sch["COMBOKEY"].nunique()
    if n_unique != n_schools:
        raise ValueError("Rebuilt COMBOKEY is not unique")
    lea_dup = int(lea["LEAID"].duplicated().sum())
    if lea_dup:
        raise ValueError(f"Duplicate LEAID in LEA file: {lea_dup}")

    missing_lea = ~sch["LEAID"].isin(lea["LEAID"])
    df = sch.merge(lea, on="LEAID", how="left", validate="many_to_one")
    if len(df) != n_schools:
        raise ValueError("LEA join changed the school row count")
    df["_missing_lea"] = missing_lea.to_numpy()
    info = {
        "n_schools": n_schools,
        "unique_combokey": n_unique,
        "stored_combokey_unique": int(sch["COMBOKEY_stored"].nunique()),
        "lea_rows": len(lea),
        "unmatched_lea": int(missing_lea.sum()),
    }
    print(f"Rebuilt COMBOKEY: {n_unique:,} unique keys from {n_schools:,} rows")
    print(f"Schools with no LEA match: {info['unmatched_lea']:,}")
    return df, info


def recode_reserved(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Numeric parse; values < 0 become NA. Each change goes to the problem log."""
    df = df.copy()
    logs: list[pd.DataFrame] = []
    for col in cols:
        raw = df[col]
        num = pd.to_numeric(raw, errors="coerce")
        neg = num < 0
        if neg.any():
            codes = num.where(neg).astype("Int64")
            ev = "reserved code " + codes.astype(str) + " (" + codes.map(RESERVED_GROUPS).fillna("unknown_code") + ")"
            logs.append(_log(df, neg, col, "reserved_code", "set_to_NA", codes.astype(str), "", ev))
        bad = num.isna() & raw.ne("")
        if bad.any():
            logs.append(_log(df, bad, col, "non_numeric", "set_to_NA", raw, "", "value is not a number"))
        df[col] = num.where(num >= 0)
    return df, logs


def strict_sum(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Sum across columns; NA if any column is NA. Never fills with zero."""
    return df[cols].sum(axis=1, min_count=len(cols))


def pct_of_total(n: pd.Series, total: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (percent on a 0-100 scale, mask where subgroup > total)."""
    defined = n.notna() & total.notna() & (total > 0)
    exceeds = defined & (n > total)
    pct = (100.0 * n / total).where(defined & ~exceeds)
    return pct, exceeds


def yes_no(series: pd.Series) -> pd.Series:
    return series.str.upper().map({"YES": "Yes", "NO": "No"})


def grade_band(df: pd.DataFrame) -> pd.Series:
    """Combine KG-12 flags (AI_CONTEXT.md A4). Preschool / ungraded are ignored.

    elementary: only grades K-5      middle: only 6-8      high: only 9-12
    span:       two or three of those groups
    other:      no K-12 grade (preschool-only or ungraded-only)
    NA:         any KG-12 flag is not a clear Yes/No
    """
    flags = df[GRADE_COLS].apply(lambda c: c.str.upper())
    known = flags.isin(["YES", "NO"]).all(axis=1)
    yes = flags.eq("YES")
    elem = yes[GRADE_COLS[:6]].any(axis=1)    # KG, 1-5
    mid = yes[GRADE_COLS[6:9]].any(axis=1)    # 6-8
    high = yes[GRADE_COLS[9:]].any(axis=1)    # 9-12
    n_groups = elem.astype(int) + mid.astype(int) + high.astype(int)
    band = pd.Series("span", index=df.index, dtype="object")
    band[n_groups == 0] = "other"
    band[(n_groups == 1) & elem] = "elementary"
    band[(n_groups == 1) & mid] = "middle"
    band[(n_groups == 1) & high] = "high"
    band[~known] = pd.NA
    return band


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Build the shared 50-column table from the recoded working frame."""
    logs: list[pd.DataFrame] = []
    out = pd.DataFrame(index=df.index)

    out["year"] = YEAR
    out["combokey"] = df["COMBOKEY"]
    out["leaid"] = df["LEAID"]
    out["schid"] = df["SCHID"]
    out["lea_state"] = df["LEA_STATE"].str.upper()
    out["sch_name"] = df["SCH_NAME"]
    out["lea_name"] = df["LEA_NAME"]
    out["jj"] = yes_no(df["JJ"])
    out["sch_virt_ind"] = pd.NA  # no virtual-school indicator in 2015-16
    out["sch_status_sped"] = yes_no(df["SCH_STATUS_SPED"])
    out["sch_status_magnet"] = yes_no(df["SCH_STATUS_MAGNET"])
    out["sch_status_charter"] = yes_no(df["SCH_STATUS_CHARTER"])
    out["sch_status_alt"] = yes_no(df["SCH_STATUS_ALT"])
    out["grade_band"] = grade_band(df)

    # Enrollment (2015-16 has M and F only, so there is no nonbinary count).
    out["enrollment_total"] = strict_sum(df, ["TOT_ENR_M", "TOT_ENR_F"])
    out["enr_nonbinary"] = np.nan
    enr = out["enrollment_total"]
    for name, (m_col, f_col) in ENROLLMENT_PARTS.items():
        out[name] = strict_sum(df, [m_col, f_col])

    # Seclusion.
    for raw, name in SECL_COLS.items():
        out[name] = df[raw]
    out["seclusion_instances"] = strict_sum(df, list(SECL_COLS))
    rate_ok = out["seclusion_instances"].notna() & enr.notna() & (enr > 0)
    out["seclusion_rate"] = (100.0 * out["seclusion_instances"] / enr).where(rate_ok)

    # FTE: 999 placeholders -> NA (logged), then names and ratios.
    fte = {}
    for raw, name in FTE_COLS.items():
        s = df[raw].copy()
        if raw in FTE_PLACEHOLDER_COLS:
            is_999 = s.eq(999)
            if is_999.any():
                logs.append(_log(df, is_999, raw, "fte_placeholder_999", "set_to_NA", s, "", "999 is a placeholder, not a real FTE"))
            s = s.mask(is_999)
        fte[raw] = s
        out[name] = s
    out["counselors_per_100"] = (100.0 * out["fte_counselors"] / enr).where(enr > 0)
    out["teachers_per_100"] = (100.0 * out["fte_teachers"] / enr).where(enr > 0)
    support_total = strict_sum(out, SUPPORT_FTE_COLS)
    out["support_fte_per_100"] = (100.0 * support_total / enr).where(enr > 0)

    out["lea_enrollment"] = df["LEA_ENR"]
    out["lea_schools"] = df["LEA_SCHOOLS"]

    # Subgroup shares: 0-100 scale, NA when the subgroup is larger than the total.
    for share, count in [("pct_idea", "enr_idea"), ("pct_504", "enr_504"), ("pct_el", "enr_el")]:
        out[share], exceeds = pct_of_total(out[count], enr)
        if exceeds.any():
            logs.append(
                _log(
                    df, exceeds, count, "subgroup_exceeds_total", "pct_set_to_NA", out[count], "",
                    "subgroup count is larger than enrollment_total",
                )
            )

    # FTE outliers: flag only, never change values.
    outlier_any = pd.Series(False, index=df.index)
    for raw, name in FTE_COLS.items():
        cap = FTE_CAP_PER_100_TEACHERS if raw in TEACHER_RAW_COLS else FTE_CAP_PER_100_OTHER
        s = fte[raw]
        per_100 = (100.0 * s / enr).where(enr > 0)
        over_enr = s.notna() & enr.notna() & (s > enr)
        over_cap = s.notna() & (per_100 > cap)
        for mask, why in [(over_enr, "FTE is larger than enrollment"), (over_cap & ~over_enr, f"more than {cap} FTE per 100 students")]:
            if mask.any():
                logs.append(_log(df, mask, raw, "fte_outlier", "retained", s, s, why))
        outlier_any |= over_enr | over_cap
    out["flag_fte_outlier"] = outlier_any

    # Flags.
    out["flag_small_enrollment"] = enr.notna() & (enr < SMALL_ENROLLMENT_CUTOFF)
    # 2015-16 has no nonbinary (X) counts, so totals are never partial.
    for col in ["flag_partial_enrollment", "flag_partial_idea", "flag_partial_504", "flag_partial_el"]:
        out[col] = False
    out["flag_missing_seclusion"] = out["seclusion_instances"].isna()
    out["flag_missing_enrollment"] = ~(enr > 0)  # NA or not above 0
    out["flag_missing_module"] = False  # one wide school file, no module joins
    out["flag_missing_lea"] = df["_missing_lea"].to_numpy()
    if out["flag_missing_lea"].any():
        logs.append(
            _log(df, out["flag_missing_lea"], "LEAID", "lea_unmatched", "kept", df["LEAID"], df["LEAID"], "district not found in the LEA file")
        )
    out["flag_analysis_ready"] = ~out["flag_missing_seclusion"] & enr.notna() & (enr > 0)

    return out[OUTPUT_COLUMNS], logs


def _log(df, mask, column, issue, action, values, cleaned, evidence) -> pd.DataFrame:
    """Build problem-log rows (AI_CONTEXT.md A5) for the rows where mask is True."""
    is_lea = column in LEA_RAW_COLS
    n = int(mask.sum())
    rows = df.loc[mask]
    return pd.DataFrame(
        {
            "year": YEAR,
            "source_file": LEA_FILE if is_lea else SCH_FILE,
            "source_row": rows["_lea_row" if is_lea else "_source_row"].to_numpy(),
            "combokey": rows["COMBOKEY"].to_numpy(),
            "leaid": rows["LEAID"].to_numpy(),
            "raw_column": column,
            "raw_value": np.asarray(values[mask].astype(str)) if hasattr(values, "loc") else [str(values)] * n,
            "issue": issue,
            "action": action,
            "cleaned_value": cleaned if isinstance(cleaned, str) else np.asarray(cleaned[mask].astype(str)),
            "evidence": evidence if isinstance(evidence, str) else np.asarray(evidence[mask]),
        }
    )


def clean(raw_dir: Path) -> dict:
    sch, sch_info = read_crdc_csv(raw_dir / SCH_FILE, SCH_COLS)
    lea, lea_info = read_crdc_csv(raw_dir / LEA_FILE, LEA_COLS)
    df, join_info = build_keys_and_join(sch, lea)
    df, recode_logs = recode_reserved(df, COUNT_COLS)
    out, feature_logs = build_features(df)

    logs = recode_logs + feature_logs
    quality = pd.concat(logs, ignore_index=True) if logs else pd.DataFrame(columns=QUALITY_COLUMNS)
    quality = quality[QUALITY_COLUMNS]
    return {
        "work": df,
        "out": out,
        "quality": quality,
        "sources": [sch_info, lea_info],
        "join": join_info,
    }


def audit_report(result: dict) -> dict:
    df, out, q = result["work"], result["out"], result["quality"]

    def code_count(col: str, code: int) -> int:
        m = (q["raw_column"] == col) & (q["issue"] == "reserved_code") & (q["raw_value"] == str(code))
        return int(m.sum())

    return {
        "n_schools": result["join"]["n_schools"],
        "unique_combokey": result["join"]["unique_combokey"],
        "jj_yes": int((out["jj"] == "Yes").sum()),
        "seclusion_all_three_valid": int(out["seclusion_instances"].notna().sum()),
        "wodis_neg9": code_count("SCH_RSINSTANCES_SECL_WODIS", -9),
        "wodis_neg5": code_count("SCH_RSINSTANCES_SECL_WODIS", -5),
        "wodis_positive": int((df["SCH_RSINSTANCES_SECL_WODIS"] > 0).sum()),
        "idea_positive": int((df["SCH_RSINSTANCES_SECL_IDEA"] > 0).sum()),
        "enr_m_usable": int(df["TOT_ENR_M"].notna().sum()),
        "enr_f_usable": int(df["TOT_ENR_F"].notna().sum()),
        "enr_m_zero": int((df["TOT_ENR_M"] == 0).sum()),
        "enr_sum_zero": int((out["enrollment_total"] == 0).sum()),
    }


AUDIT_EXPECTED = {
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


def print_audit_checks(report: dict) -> None:
    print("\nAudit checks (expected vs observed)")
    for key, exp in AUDIT_EXPECTED.items():
        obs = report[key]
        status = "OK" if obs == exp else "DIFF"
        print(f"  {status:4} {key}: expected {exp:,}  observed {obs:,}")


def write_outputs(result: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = result["out"]
    paths = {
        "full": out_dir / "schools_201516.csv",
        "analysis": out_dir / "schools_201516_analysis.csv",
        "quality": out_dir / "quality_detail_201516.csv",
    }
    out.to_csv(paths["full"], index=False)
    out.loc[out["flag_analysis_ready"]].to_csv(paths["analysis"], index=False)
    result["quality"].to_csv(paths["quality"], index=False)
    for key, p in paths.items():
        print(f"Wrote {p}")
    return paths


# ---------------------------------------------------------------------------
# Part B: documentation (mapping file and QA report)
# ---------------------------------------------------------------------------

MAPPING_HEADER = [
    "source_file", "source_column", "shared_output_column", "transformation",
    "units_population_period", "manual_reference", "verification_status",
]
_REF = "2015-16 CRDC data layout; not re-checked against the manual"


def mapping_rows() -> list[list[str]]:
    s, l = SCH_FILE, LEA_FILE
    rows = [
        [s, "LEAID", "leaid", "Validate, zero-pad to 7", "District ID, 2015-16", _REF, "unverified"],
        [s, "SCHID", "schid", "Validate, zero-pad to 5", "School ID, 2015-16", _REF, "unverified"],
        [s, "COMBOKEY", "combokey", "Rebuilt as LEAID + SCHID; stored value lost leading zeros", "School ID, 2015-16", _REF, "verified"],
        [l, "LEAID", "leaid", "Validate, zero-pad to 7, join key", "District ID, 2015-16", _REF, "unverified"],
        [s, "LEA_STATE", "lea_state", "Trim, uppercase", "State code, 2015-16", "Descriptive field", "unresolved"],
        [s, "SCH_NAME", "sch_name", "Trim", "School name, 2015-16", "Descriptive field", "unresolved"],
        [s, "LEA_NAME", "lea_name", "Trim", "District name, 2015-16", "Descriptive field", "unresolved"],
        [s, "JJ", "jj", "Yes/No/NA", "School, justice facility, 2015-16", _REF, "unresolved"],
        [s, "(none)", "sch_virt_ind", "Always NA: no virtual-school indicator in 2015-16", "School, 2015-16", "Not collected", "verified"],
        [s, "SCH_STATUS_SPED", "sch_status_sped", "Yes/No/NA", "School, 2015-16", _REF, "unverified"],
        [s, "SCH_STATUS_MAGNET", "sch_status_magnet", "Yes/No/NA", "School, 2015-16", _REF, "unverified"],
        [s, "SCH_STATUS_CHARTER", "sch_status_charter", "Yes/No/NA", "School, 2015-16", _REF, "unverified"],
        [s, "SCH_STATUS_ALT", "sch_status_alt", "Yes/No/NA", "School, 2015-16", _REF, "unverified"],
        [s, "SCH_GRADE_PS", "", "Read, left out of grade_band", "Preschool flag, 2015-16", _REF, "unverified"],
        [s, "SCH_GRADE_UG", "", "Read, left out of grade_band", "Ungraded flag, 2015-16", _REF, "unverified"],
    ]
    for c in GRADE_COLS:
        rows.append([s, c, "grade_band", "Yes/No; combined by the grade-band rule (elementary, middle, high, span, other)", "Grade offered, 2015-16", _REF, "unverified"])
    for c in ["TOT_ENR_M", "TOT_ENR_F"]:
        rows.append([s, c, "enrollment_total", "Calculated total M+F; NA if either is NA", "Students, overall, 2015-16", _REF, "unresolved"])
    rows.append([s, "(none)", "enr_nonbinary", "Always NA: 2015-16 has no nonbinary counts", "Students, 2015-16", "Not collected", "verified"])
    for name, (m, f) in ENROLLMENT_PARTS.items():
        label = {"enr_idea": "IDEA", "enr_504": "Section 504 only", "enr_el": "EL (LEP in 2015-16)"}[name]
        for c in (m, f):
            rows.append([s, c, name, "Count; M+F strict", f"Students, {label}, 2015-16", _REF, "unverified"])
    for raw, name in SECL_COLS.items():
        rows.append([s, raw, name, "Count; summed with the other two groups, NA if any is NA", "Instances of seclusion (not students), 2015-16", _REF, "unverified"])
    for raw, name in FTE_COLS.items():
        t = "Numeric FTE, fractions kept"
        if raw in FTE_PLACEHOLDER_COLS:
            t += "; 999 placeholder set to NA"
        rows.append([s, raw, name, t, "FTE (decimal), 2015-16", _REF, "unverified"])
    rows.append([l, "LEA_ENR", "lea_enrollment", "Count", "Students in district, 2015-16", _REF, "unverified"])
    rows.append([l, "LEA_SCHOOLS", "lea_schools", "Count", "Public schools in district, 2015-16", _REF, "unverified"])
    for c in ["SCH_RSINSTANCES_MECH_*", "SCH_RSINSTANCES_PHYS_*"]:
        rows.append([s, c, "", "Not read: restraint leaks the outcome (AUC 0.84 on its own in 2015-16)", "Instances of restraint, 2015-16", "Team EDA", "verified"])
    return rows


def write_mapping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(mapping_rows(), columns=MAPPING_HEADER).to_csv(path, index=False)
    print(f"Wrote {path}")


def _md_table(df: pd.DataFrame) -> list[str]:
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return lines


def write_qa(result: dict, report: dict, path: Path) -> None:
    """QA report with no timestamps, so reruns give identical text."""
    out, q = result["out"], result["quality"]
    join = result["join"]
    L: list[str] = []
    L += ["# QA report for 2015-16 CRDC cleaning", "",
          "This file is written by `scripts/clean_201516.py`. Do not edit it by hand.", ""]
    L += ["## How to rerun", "", "```text",
          "python scripts/clean_201516.py --raw-dir data/raw/2015-16 "
          "--out-dir data/processed/201516 --docs-dir docs/cleaning", "```", ""]
    L += ["## Sources", ""]
    src = pd.DataFrame(result["sources"])[["file", "encoding", "rows_parsed", "rows_kept", "sha256"]]
    src["rows_parsed"] = src["rows_parsed"].map("{:,}".format)
    src["rows_kept"] = src["rows_kept"].map("{:,}".format)
    L += _md_table(src) + [""]

    L += ["## Row counts", ""]
    rows = pd.DataFrame(
        [
            ["Schools (full table)", f"{len(out):,}", f"{AUDIT_EXPECTED['n_schools']:,}"],
            ["Analysis-ready schools", f"{int(out['flag_analysis_ready'].sum()):,}", "Recomputed, not matched"],
            ["Schools with all three seclusion fields valid", f"{report['seclusion_all_three_valid']:,}", f"{AUDIT_EXPECTED['seclusion_all_three_valid']:,}"],
        ],
        columns=["Item", "Count", "Audit comparison"],
    )
    L += _md_table(rows) + [""]

    L += ["## IDs and joins", "",
          "The stored COMBOKEY lost leading zeros and used scientific notation "
          f"({join['stored_combokey_unique']:,} distinct stored values). It was rebuilt as padded "
          f"LEAID (7) + SCHID (5): {join['unique_combokey']:,} unique keys from {join['n_schools']:,} rows.", "",
          f"LEA join: {join['lea_rows']:,} LEA rows, {join['unmatched_lea']:,} schools with no LEA match. "
          "The join kept the school row count.", ""]

    L += ["## Audit checks", ""]
    chk = pd.DataFrame(
        [[k, f"{v:,}", f"{report[k]:,}", "OK" if report[k] == v else "DIFF"] for k, v in AUDIT_EXPECTED.items()],
        columns=["Check", "Expected", "Observed", "Status"],
    )
    L += _md_table(chk) + [""]

    L += ["## Missing values by output column", ""]
    miss = out.drop(columns=["year"]).isna().sum()
    miss = miss[miss > 0]
    mt = pd.DataFrame({"Column": miss.index, "Missing rows": [f"{v:,}" for v in miss.values],
                       "Share": [f"{100 * v / len(out):.1f}%" for v in miss.values]})
    L += _md_table(mt) + [""]
    L += ["`sch_virt_ind` and `enr_nonbinary` are always NA because 2015-16 does not collect them.", ""]

    L += ["Reserved codes by raw column (counts of values set to NA):", ""]
    rc = q[q["issue"] == "reserved_code"]
    if len(rc):
        piv = rc.pivot_table(index="raw_column", columns="raw_value", values="combokey", aggfunc="count", fill_value=0)
        piv = piv[sorted(piv.columns, key=int)]
        piv = piv.reset_index().rename(columns={"raw_column": "Raw column"})
        for c in piv.columns[1:]:
            piv[c] = piv[c].map("{:,}".format)
        L += _md_table(piv) + [""]

    L += ["## Quality log summary", ""]
    qs = q.groupby(["issue", "action"]).size().reset_index(name="Rows")
    qs["Rows"] = qs["Rows"].map("{:,}".format)
    L += _md_table(qs.rename(columns={"issue": "Issue", "action": "Action"})) + [""]
    L += ["Row-level detail is in `quality_detail_201516.csv`, including the original reserved code "
          "and its reason group (structural_skip, missing, suppressed) in the evidence column.", ""]

    L += ["## Counts by group", ""]
    flags = ["flag_small_enrollment", "flag_fte_outlier", "flag_missing_seclusion",
             "flag_missing_enrollment", "flag_missing_lea", "flag_analysis_ready"]
    ana = out[out["flag_analysis_ready"]]
    gr = [["jj = Yes", f"{int((out['jj'] == 'Yes').sum()):,}", f"{int((ana['jj'] == 'Yes').sum()):,}"],
          ["jj = No", f"{int((out['jj'] == 'No').sum()):,}", f"{int((ana['jj'] == 'No').sum()):,}"],
          ["jj missing", f"{int(out['jj'].isna().sum()):,}", f"{int(ana['jj'].isna().sum()):,}"]]
    gr += [[f"{f} = True", f"{int(out[f].sum()):,}", f"{int(ana[f].sum()):,}"] for f in flags]
    L += _md_table(pd.DataFrame(gr, columns=["Group", "Full table", "Analysis table"])) + [""]
    L += ["grade_band counts (full table; NA means a KG-12 grade flag was unknown):", ""]
    gb = out["grade_band"].fillna("NA").value_counts().rename_axis("grade_band").reset_index(name="Rows")
    gb["Rows"] = gb["Rows"].map("{:,}".format)
    L += _md_table(gb) + [""]

    L += ["## Unresolved issues and notes", "",
          "- Restraint columns (MECH and PHYS) are not read. The EDA found restraint leaks the outcome (AUC 0.84 on its own in 2015-16).",
          "- flag_small_enrollment uses under 10 students (shared playbook).",
          "- pct_idea, pct_504 and pct_el are on a 0-100 scale and are NA when the subgroup is larger than enrollment_total.",
          "- flag_analysis_ready is True when the seclusion total is valid and enrollment_total is above 0. flag_missing_enrollment is True when enrollment_total is NA or not above 0.",
          "- FTE 999 placeholders (counselors, nurses, psychologists, social workers) are set to NA and logged. FTE outliers are flagged and logged, not changed.",
          "- grade_band and support_fte_per_100 follow AI_CONTEXT.md section A4 (support_fte_per_100 = nurses + psychologists + social workers; counselors are not included).",
          "- The mapping file marks manual references as unverified: they were not re-checked against the 2015-16 manual.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    args = ap.parse_args()

    result = clean(args.raw_dir)
    report = audit_report(result)
    print_audit_checks(report)
    assert list(result["out"].columns) == OUTPUT_COLUMNS and len(OUTPUT_COLUMNS) == 50
    write_outputs(result, args.out_dir)
    write_mapping(args.docs_dir / "mapping_201516.csv")
    write_qa(result, report, args.docs_dir / "qa_201516.md")


if __name__ == "__main__":
    main()
