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
import platform
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

# Reserved codes listed for 2015-16 (audit: manual Table 2, p. 18). Any other
# negative value is still set to NA but logged as an unexpected code.
RESERVED_GROUPS = {
    -9: "structural_skip",
    -5: "missing",
    -6: "missing",
    -7: "missing",
    -8: "missing",
    -2: "suppressed",
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
LEA_REQUIRED = ["LEAID", "LEA_ENR", "LEA_SCHOOLS"]
LEA_OPTIONAL = ["LEA_NAME", "LEA_STATE"]

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
# The audit says 999 "looks like a placeholder" in these four columns, but the
# playbook (step 10) says to keep FTE values unless the documentation or a recorded
# team decision supports changing them. Default: keep and flag. Set True only after
# the team records a decision to treat 999 as NA.
PLACEHOLDER_999_TO_NA = False
FTE_PLACEHOLDER_COLS = [
    "SCH_FTECOUNSELORS",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
]
SUPPORT_FTE_COLS = ["fte_nurses", "fte_psych", "fte_social"]  # counselors not included

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

STATUS_COLS = ["SCH_STATUS_SPED", "SCH_STATUS_MAGNET", "SCH_STATUS_CHARTER", "SCH_STATUS_ALT"]
YES_NO_COLS = ["JJ"] + STATUS_COLS + GRADE_EXTRA_COLS + GRADE_COLS
FTE_RAW_COLS = set(FTE_COLS)

SMALL_ENROLLMENT_CUTOFF = 10  # shared playbook: under 10 students
FTE_REVIEW_TEACHERS = 2000  # playbook step 10: teachers > 2,000
FTE_REVIEW_OTHER = 200      # playbook step 10: any other core FTE > 200

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


def read_crdc_csv(path: Path, required: list[str], optional: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Read a CRDC CSV as strings. Tries utf-8-sig, then cp1252 (playbook step 1)."""
    optional = optional or []
    wanted = set(required) | set(optional)
    kwargs = dict(dtype=str, keep_default_na=False, skip_blank_lines=True, usecols=lambda c: c.strip() in wanted)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", **kwargs)
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp1252", **kwargs)
        encoding = "cp1252"
    df.columns = df.columns.str.strip()
    absent = [c for c in required if c not in df.columns]
    if absent:
        raise ValueError(f"{path.name}: expected columns not found: {absent}")
    df = df.apply(lambda s: s.str.strip())
    parsed = len(df)
    df["_source_row"] = np.arange(parsed) + 1  # first data row = 1 (playbook 3.3)
    empty = df.drop(columns="_source_row").eq("").all(axis=1)
    if empty.any():
        df = df.loc[~empty].copy()
    info = {
        "file": path.name,
        "encoding": encoding,
        "rows_parsed": parsed,
        "rows_kept": len(df),
        "sha256": sha256_of(path),
        "optional_missing": [c for c in optional if c not in df.columns],
    }
    print(f"Read {path.name}: {parsed:,} rows, kept {len(df):,}, encoding={encoding}")
    return df, info


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_ids(df: pd.DataFrame, widths: dict[str, int], file: str, logs: list) -> tuple[pd.DataFrame, dict]:
    """Repair a trailing ".0", check blank / non-digit / too-long IDs, then zero-pad.

    The ".0" suffix comes from Excel and is the only automatic repair; it is logged.
    Non-digit IDs are kept as reported and logged. IDs are never converted through floats.
    """
    df = df.copy()
    counts = {}
    for col, width in widths.items():
        s = df[col]
        fixed = s.str.replace(r"\.0$", "", regex=True)
        changed = fixed.ne(s)
        if changed.any():
            logs.append(_log(df, changed, col, "id_repair", "removed_trailing_.0", s, fixed, "Excel float suffix", file=file))
        s = fixed
        blank = s.eq("")
        nondigit = ~blank & ~s.str.fullmatch(r"\d+")
        too_long = s.str.len() > width
        for mask, issue, why in [
            (blank, "blank_id", "ID is blank"),
            (nondigit, "non_digit_id", "ID has non-digit characters"),
            (too_long, "id_too_long", f"ID is longer than {width} characters"),
        ]:
            if mask.any():
                logs.append(_log(df, mask, col, issue, "kept_as_reported", s, s, why, file=file))
        short = ~blank & ~nondigit & ~too_long & (s.str.len() < width)
        counts[col] = int(short.sum())
        df[col] = s.where(~short, s.str.zfill(width))
    return df, counts


def _norm_name(s: pd.Series) -> pd.Series:
    return s.str.casefold().str.replace(r"\s+", " ", regex=True)


def build_keys_and_join(sch: pd.DataFrame, lea: pd.DataFrame) -> tuple[pd.DataFrame, dict, list]:
    """Validate and pad IDs, rebuild COMBOKEY, left-join LEA on LEAID."""
    logs: list[pd.DataFrame] = []
    sch = sch.copy()
    lea = lea.copy().rename(columns={"_source_row": "_lea_row"})
    sch["COMBOKEY_stored"] = sch["COMBOKEY"]
    sch, padded_sch = validate_ids(sch, {"LEAID": 7, "SCHID": 5}, SCH_FILE, logs)
    sch["COMBOKEY"] = sch["LEAID"] + sch["SCHID"]
    lea, padded_lea = validate_ids(lea, {"LEAID": 7}, LEA_FILE, logs)

    n_schools = len(sch)
    n_unique = sch["COMBOKEY"].nunique()
    if n_unique != n_schools:
        raise ValueError(f"Rebuilt COMBOKEY is not unique ({n_schools - n_unique} duplicates); check them before continuing")
    lea_dup = int(lea["LEAID"].duplicated().sum())
    if lea_dup:
        raise ValueError(f"Duplicate LEAID in LEA file: {lea_dup}")

    missing_lea = ~sch["LEAID"].isin(lea["LEAID"])
    lea = lea.rename(columns={"LEA_NAME": "LEA_NAME_lea", "LEA_STATE": "LEA_STATE_lea"})
    df = sch.merge(lea, on="LEAID", how="left", validate="many_to_one")
    if len(df) != n_schools:
        raise ValueError("LEA join changed the school row count")
    df["_missing_lea"] = missing_lea.to_numpy()
    for sch_col, lea_col, issue in [("LEA_NAME", "LEA_NAME_lea", "lea_name_disagreement"),
                                    ("LEA_STATE", "LEA_STATE_lea", "lea_state_disagreement")]:
        if lea_col in df:
            both = ~missing_lea & df[lea_col].notna() & df[lea_col].ne("") & df[sch_col].ne("")
            diff = both & (_norm_name(df[sch_col]) != _norm_name(df[lea_col].fillna("")))
            if diff.any():
                keep = "kept_lea_file_value" if sch_col == "LEA_NAME" else "kept_school_file_value"
                logs.append(_log(df, diff, sch_col, issue, keep, df[sch_col], df[lea_col],
                                 f"school file and LEA file disagree", file=SCH_FILE))
    info = {
        "n_schools": n_schools,
        "unique_combokey": n_unique,
        "stored_combokey_unique": int(sch["COMBOKEY_stored"].nunique()),
        "lea_rows": len(lea),
        "unmatched_lea": int(missing_lea.sum()),
        "padded": {**{f"{SCH_FILE}:{k}": v for k, v in padded_sch.items()}, **{f"{LEA_FILE}:{k}": v for k, v in padded_lea.items()}},
    }
    print(f"Rebuilt COMBOKEY: {n_unique:,} unique keys from {n_schools:,} rows")
    print(f"Schools with no LEA match: {info['unmatched_lea']:,}")
    return df, info, logs


def recode_reserved(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Numeric parse; negative, infinite and unparseable values become NA (all logged)."""
    df = df.copy()
    logs: list[pd.DataFrame] = []
    for col in cols:
        raw = df[col]
        num = pd.to_numeric(raw, errors="coerce")
        neg = num < 0
        if neg.any():
            codes = num.where(neg).astype("Int64")
            known = codes.isin(list(RESERVED_GROUPS))
            ev = "reserved code " + codes.astype(str) + " (" + codes.map(RESERVED_GROUPS).fillna("unknown_code") + ")"
            if (neg & known).any():
                logs.append(_log(df, neg & known, col, "reserved_code", "set_to_NA", codes.astype(str), "", ev))
            if (neg & ~known).any():
                logs.append(_log(df, neg & ~known, col, "unexpected_code", "set_to_NA", codes.astype(str), "",
                                 "negative code not in the 2015-16 reserved set"))
        inf = np.isinf(num)
        if inf.any():
            logs.append(_log(df, inf, col, "non_finite", "set_to_NA", raw, "", "value is infinite"))
        bad = num.isna() & raw.notna() & raw.ne("")
        if bad.any():
            logs.append(_log(df, bad, col, "non_numeric", "set_to_NA", raw, "", "value is not a number"))
        num = num.where(num >= 0).where(~inf)
        if col not in FTE_RAW_COLS:
            frac = num.notna() & (num % 1 != 0)
            if frac.any():
                logs.append(_log(df, frac, col, "fractional_count", "retained", raw, raw, "count is not a whole number"))
        df[col] = num
    return df, logs


def clean_yes_no(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Yes/No/NA text. Reserved codes and unexpected values become NA and are logged."""
    df = df.copy()
    logs = []
    for col in cols:
        raw = df[col]
        up = raw.str.upper()
        num = pd.to_numeric(raw, errors="coerce")
        neg = num < 0
        if neg.any():
            codes = num.where(neg).astype("Int64")
            known = codes.isin(list(RESERVED_GROUPS))
            ev = "reserved code " + codes.astype(str) + " (" + codes.map(RESERVED_GROUPS).fillna("unknown_code") + ")"
            if (neg & known).any():
                logs.append(_log(df, neg & known, col, "reserved_code", "set_to_NA", codes.astype(str), "", ev))
            if (neg & ~known).any():
                logs.append(_log(df, neg & ~known, col, "unexpected_code", "set_to_NA", codes.astype(str), "",
                                 "negative code not in the 2015-16 reserved set"))
        odd = raw.notna() & raw.ne("") & ~up.isin(["YES", "NO"]) & ~neg
        if odd.any():
            logs.append(_log(df, odd, col, "unexpected_category", "set_to_NA", raw, "", "expected Yes or No"))
        df[col] = up.map({"YES": "Yes", "NO": "No"})
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
    out["lea_name"] = df["LEA_NAME_lea"] if "LEA_NAME_lea" in df else pd.NA
    out["jj"] = df["JJ"]
    out["sch_virt_ind"] = pd.NA  # no virtual-school indicator in 2015-16
    out["sch_status_sped"] = df["SCH_STATUS_SPED"]
    out["sch_status_magnet"] = df["SCH_STATUS_MAGNET"]
    out["sch_status_charter"] = df["SCH_STATUS_CHARTER"]
    out["sch_status_alt"] = df["SCH_STATUS_ALT"]
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

    # FTE: 999 in four columns is reviewed (playbook step 10). Kept by default.
    fte = {}
    for raw, name in FTE_COLS.items():
        s_ = df[raw].copy()
        if raw in FTE_PLACEHOLDER_COLS:
            is_999 = s_.eq(999)
            if is_999.any():
                if PLACEHOLDER_999_TO_NA:
                    logs.append(_log(df, is_999, raw, "fte_placeholder_999", "set_to_NA", s_, "",
                                     "999 looks like a placeholder (audit); set to NA by recorded team decision"))
                    s_ = s_.mask(is_999)
                else:
                    logs.append(_log(df, is_999, raw, "fte_placeholder_999", "retained_flagged", s_, s_,
                                     "999 looks like a placeholder (audit) but its meaning is not documented; kept for review"))
        fte[raw] = s_
        out[name] = s_
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

    # FTE review flags only (playbook step 10). The flag uses the reported value, so it
    # stays True even if a 999 was later set to NA.
    outlier_any = pd.Series(False, index=df.index)
    for raw, name in FTE_COLS.items():
        cap = FTE_REVIEW_TEACHERS if raw == "SCH_FTETEACH_TOT" else FTE_REVIEW_OTHER
        reported = df[raw]
        over = reported.notna() & (reported > cap)
        removed = over & fte[raw].isna()
        kept = over & ~removed
        why = f"FTE is above the review cutoff of {cap:,}"
        if kept.any():
            logs.append(_log(df, kept, raw, "fte_outlier", "retained", reported, reported, why))
        if removed.any():
            logs.append(_log(df, removed, raw, "fte_outlier", "flag_only_value_set_to_NA", reported, "", why))
        outlier_any |= over
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


def _log(df, mask, column, issue, action, values, cleaned, evidence, file=None) -> pd.DataFrame:
    """Build problem-log rows (AI_CONTEXT.md A5) for the rows where mask is True."""
    is_lea = (file == LEA_FILE) if file else column in LEA_RAW_COLS
    n = int(mask.sum())
    rows = df.loc[mask]
    return pd.DataFrame(
        {
            "year": YEAR,
            "source_file": LEA_FILE if is_lea else SCH_FILE,
            "source_row": rows["_lea_row" if is_lea else "_source_row"].to_numpy(),
            "combokey": rows["COMBOKEY"].to_numpy() if "COMBOKEY" in rows else [pd.NA] * n,
            "leaid": rows["LEAID"].to_numpy() if "LEAID" in rows else [pd.NA] * n,
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
    lea, lea_info = read_crdc_csv(raw_dir / LEA_FILE, LEA_REQUIRED, LEA_OPTIONAL)
    df, join_info, id_logs = build_keys_and_join(sch, lea)
    df, recode_logs = recode_reserved(df, COUNT_COLS)
    df, yn_logs = clean_yes_no(df, YES_NO_COLS)
    out, feature_logs = build_features(df)

    logs = id_logs + recode_logs + yn_logs + feature_logs
    quality = pd.concat(logs, ignore_index=True) if logs else pd.DataFrame(columns=QUALITY_COLUMNS)
    quality = quality[QUALITY_COLUMNS].copy()
    quality["source_row"] = pd.to_numeric(quality["source_row"]).astype("Int64")
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


def run_self_checks() -> None:
    """Small unit checks of the cleaning rules, run before every cleaning run."""
    f = pd.DataFrame
    s = strict_sum(f({"a": [1.0, np.nan, 0.0], "b": [2.0, 3.0, 0.0]}), ["a", "b"])
    assert s.iloc[0] == 3 and np.isnan(s.iloc[1]) and s.iloc[2] == 0
    p, ex = pct_of_total(pd.Series([5.0, 12.0, 1.0, 1.0]), pd.Series([10.0, 10.0, np.nan, 0.0]))
    assert p.iloc[0] == 50 and np.isnan(p.iloc[1]) and ex.iloc[1] and np.isnan(p.iloc[2]) and np.isnan(p.iloc[3])

    def band(yes):
        row = {c: "No" for c in GRADE_COLS}
        row.update({c: "Yes" for c in yes})
        return grade_band(f([row])).iloc[0]

    assert band(GRADE_COLS) == "span" and band(GRADE_COLS[:9]) == "span"
    assert band(GRADE_COLS[:6]) == "elementary" and band(GRADE_COLS[6:9]) == "middle"
    assert band(GRADE_COLS[9:]) == "high" and band([]) == "other"
    unk = {c: "No" for c in GRADE_COLS}
    unk["SCH_GRADE_G03"] = pd.NA
    assert pd.isna(grade_band(f([unk])).iloc[0])
    ids = f({"LEAID": ["123", "24SOP0", "", "1234567.0"], "COMBOKEY": ["x"] * 4, "_source_row": [1, 2, 3, 4]})
    logs: list = []
    fixed, _ = validate_ids(ids, {"LEAID": 7}, SCH_FILE, logs)
    assert fixed["LEAID"].tolist() == ["0000123", "24SOP0", "", "1234567"]
    assert {"blank_id", "non_digit_id", "id_repair"} <= set(pd.concat(logs)["issue"])
    r = f({"COMBOKEY": ["1", "2"], "LEAID": ["", ""], "_source_row": [1, 2], "TOT_ENR_M": ["-9", "0"]})
    r, lg = recode_reserved(r, ["TOT_ENR_M"])
    assert np.isnan(r["TOT_ENR_M"].iloc[0]) and r["TOT_ENR_M"].iloc[1] == 0 and len(lg) == 1
    # End-to-end: sums, rates and flags on a tiny recoded frame (playbook section 6).
    base = {c: "No" for c in YES_NO_COLS}
    base.update({"COMBOKEY": "000000000001", "LEAID": "0000001", "SCHID": "00001", "LEA_STATE": "ca",
                 "SCH_NAME": "S", "LEA_NAME": "D", "LEA_NAME_lea": "D", "_missing_lea": False,
                 "_source_row": 1, "_lea_row": 1})
    base.update({c: 1.0 for c in COUNT_COLS})
    base.update({"TOT_ENR_M": 50.0, "TOT_ENR_F": 50.0, "SCH_RSINSTANCES_SECL_WODIS": 1.0,
                 "SCH_RSINSTANCES_SECL_IDEA": 1.0, "SCH_RSINSTANCES_SECL_504": 0.0,
                 "SCH_FTECOUNSELORS": 2.0, "SCH_FTESERVICES_NUR": 1.0, "SCH_FTESERVICES_PSY": 1.0,
                 "SCH_FTESERVICES_SOC": 1.0, "SCH_FTETEACH_TOT": 10.0})
    cases = [
        {},                                                   # 0 normal
        {"TOT_ENR_M": np.nan},                                # 1 missing M
        {"TOT_ENR_M": 0.0, "TOT_ENR_F": 0.0},                 # 2 zero enrollment
        {"SCH_FTESERVICES_PSY": np.nan},                      # 3 missing support FTE
        {"SCH_RSINSTANCES_SECL_504": np.nan},                 # 4 missing seclusion part
        {"SCH_FTECOUNSELORS": 999.0},                         # 5 999 FTE
        {"SCH_ENR_IDEA_M": 70.0, "SCH_ENR_IDEA_F": 70.0},     # 6 subgroup > total
    ]
    work = f([{**base, **c, "COMBOKEY": f"{i + 1:012d}"} for i, c in enumerate(cases)])
    t, _ = build_features(work)
    assert t["seclusion_rate"].iloc[0] == 2 and t["counselors_per_100"].iloc[0] == 2
    assert t["support_fte_per_100"].iloc[0] == 3 and t["flag_analysis_ready"].iloc[0]
    assert np.isnan(t["enrollment_total"].iloc[1]) and t["flag_missing_enrollment"].iloc[1]
    assert np.isnan(t["seclusion_rate"].iloc[1]) and not t["flag_analysis_ready"].iloc[1]
    assert t["enrollment_total"].iloc[2] == 0 and np.isnan(t["seclusion_rate"].iloc[2])
    assert np.isnan(t["counselors_per_100"].iloc[2]) and t["flag_small_enrollment"].iloc[2]
    assert np.isnan(t["support_fte_per_100"].iloc[3]) and t["counselors_per_100"].iloc[3] == 2
    assert np.isnan(t["seclusion_instances"].iloc[4]) and t["flag_missing_seclusion"].iloc[4]
    assert t["flag_fte_outlier"].iloc[5] and not t["flag_fte_outlier"].iloc[0]
    assert np.isnan(t["pct_idea"].iloc[6]) and np.isfinite(t["pct_idea"].iloc[:6].dropna()).all()
    assert not t[[c for c in OUTPUT_COLUMNS if c.startswith("flag_partial")]].any().any()
    print("Self-checks passed")


def validate_outputs(result: dict, paths: dict) -> None:
    """Reload the written files with explicit dtypes and check them (playbook section 6)."""
    ids = {"combokey": str, "leaid": str, "schid": str}
    full = pd.read_csv(paths["full"], dtype=ids, float_precision="round_trip")
    ana = pd.read_csv(paths["analysis"], dtype=ids, float_precision="round_trip")
    assert list(full.columns) == OUTPUT_COLUMNS and len(OUTPUT_COLUMNS) == 50, "column schema"
    assert len(full) == result["join"]["n_schools"], "full table must keep every roster school"
    assert full["combokey"].is_unique, "combokey must be unique"
    if not (result["quality"]["issue"] == "non_digit_id").any():
        assert full["combokey"].str.fullmatch(r"\d{12}").all(), "combokey must be 12 digits"
    assert full["leaid"].str.len().eq(7).all() and full["schid"].str.len().eq(5).all(), "ID lengths"
    for c in [c for c in OUTPUT_COLUMNS if c.startswith("flag_")]:
        assert set(full[c].unique()) <= {True, False}, f"{c} must be True/False"
    assert ana.equals(full[full["flag_analysis_ready"]].reset_index(drop=True)), "analysis = filtered full"
    num = [c for c in OUTPUT_COLUMNS if c.startswith(("seclusion_", "enr", "fte_", "pct_", "lea_")) and c not in ("lea_state", "lea_name")]
    num = [c for c in num if full[c].dtype != object]
    vals = full[num].to_numpy(dtype=float)
    assert not np.isinf(vals).any(), "no infinite values"
    assert not (vals[~np.isnan(vals)] < 0).any(), "no negative values in count/FTE/rate columns"
    print("Output checks passed (reloaded with explicit dtypes)")


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
        [s, "LEAID", "leaid", "Validate, zero-pad to 7", "District ID, 2015-16", _REF, "unresolved"],
        [s, "SCHID", "schid", "Validate, zero-pad to 5", "School ID, 2015-16", _REF, "unresolved"],
        [s, "COMBOKEY", "combokey", "Rebuilt as LEAID + SCHID; stored value lost leading zeros", "School ID, 2015-16", _REF, "verified"],
        [l, "LEAID", "leaid", "Validate, zero-pad to 7, join key", "District ID, 2015-16", _REF, "unresolved"],
        [s, "LEA_STATE", "lea_state", "Trim, uppercase", "State code, 2015-16", "Descriptive field", "unresolved"],
        [s, "SCH_NAME", "sch_name", "Trim", "School name, 2015-16", "Descriptive field", "unresolved"],
        [s, "LEA_NAME", "", "Compared with the LEA file, not output", "District name, 2015-16", "Descriptive field", "unresolved"],
        [l, "LEA_NAME", "lea_name", "Trim; district name comes from the LEA file", "District name, 2015-16", "Descriptive field", "unresolved"],
        [l, "LEA_STATE", "", "Compared with the school file, not output", "State code, 2015-16", "Descriptive field", "unresolved"],
        [s, "JJ", "jj", "Yes/No/NA", "School, justice facility, 2015-16", _REF, "unresolved"],
        [s, "(none)", "sch_virt_ind", "Always NA: no virtual-school indicator in 2015-16", "School, 2015-16", "Not collected", "verified"],
        [s, "SCH_STATUS_SPED", "sch_status_sped", "Yes/No/NA", "School, 2015-16", _REF, "unresolved"],
        [s, "SCH_STATUS_MAGNET", "sch_status_magnet", "Yes/No/NA", "School, 2015-16", _REF, "unresolved"],
        [s, "SCH_STATUS_CHARTER", "sch_status_charter", "Yes/No/NA", "School, 2015-16", _REF, "unresolved"],
        [s, "SCH_STATUS_ALT", "sch_status_alt", "Yes/No/NA", "School, 2015-16", _REF, "unresolved"],
        [s, "SCH_GRADE_PS", "", "Read, left out of grade_band", "Preschool flag, 2015-16", _REF, "unresolved"],
        [s, "SCH_GRADE_UG", "", "Read, left out of grade_band", "Ungraded flag, 2015-16", _REF, "unresolved"],
    ]
    for c in GRADE_COLS:
        rows.append([s, c, "grade_band", "Yes/No; combined by the grade-band rule (elementary, middle, high, span, other)", "Grade offered, 2015-16", _REF, "unresolved"])
    for c in ["TOT_ENR_M", "TOT_ENR_F"]:
        rows.append([s, c, "enrollment_total", "Calculated total M+F; NA if either is NA", "Students, overall, 2015-16", _REF, "unresolved"])
    rows.append([s, "(none)", "enr_nonbinary", "Always NA: 2015-16 has no nonbinary counts", "Students, 2015-16", "Not collected", "verified"])
    for name, (m, f) in ENROLLMENT_PARTS.items():
        label = {"enr_idea": "IDEA", "enr_504": "Section 504 only", "enr_el": "EL (LEP in 2015-16)"}[name]
        for c in (m, f):
            rows.append([s, c, name, "Count; M+F strict", f"Students, {label}, 2015-16", _REF, "unresolved"])
    for raw, name in SECL_COLS.items():
        rows.append([s, raw, name, "Count; summed with the other two groups, NA if any is NA. Additivity of the three groups not yet confirmed against the manual", "Instances of seclusion (not students), 2015-16", _REF, "unresolved"])
    for raw, name in FTE_COLS.items():
        t = "Numeric FTE, fractions kept; flagged if teachers > 2,000 or other FTE > 200, never changed"
        if raw in FTE_PLACEHOLDER_COLS:
            t += "; 999 set to NA (team decision)" if PLACEHOLDER_999_TO_NA else "; 999 kept and flagged for review (placeholder meaning not documented)"
        rows.append([s, raw, name, t, "FTE (decimal), 2015-16", _REF, "unresolved"])
    rows.append([l, "LEA_ENR", "lea_enrollment", "Count", "Students in district, 2015-16", _REF, "unresolved"])
    rows.append([l, "LEA_SCHOOLS", "lea_schools", "Count", "Public schools in district, 2015-16", _REF, "unresolved"])
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
          "--out-dir data/processed/201516 --docs-dir docs/cleaning", "```", "",
          f"Dependencies are listed in requirements.txt. This run used Python {platform.python_version()}, "
          f"pandas {pd.__version__}, numpy {np.__version__}.", ""]
    L += ["## Sources", ""]
    src = pd.DataFrame(result["sources"])[["file", "encoding", "rows_parsed", "rows_kept", "sha256"]]
    opt = [f"{x['file']}: {', '.join(x['optional_missing'])}" for x in result["sources"] if x["optional_missing"]]
    src["rows_parsed"] = src["rows_parsed"].map("{:,}".format)
    src["rows_kept"] = src["rows_kept"].map("{:,}".format)
    L += _md_table(src) + [""]
    if opt:
        L += ["Optional columns not found: " + "; ".join(opt) + ". lea_name is NA without LEA_NAME in the LEA file.", ""]

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
    idq = q[q["issue"].isin(["blank_id", "non_digit_id", "id_too_long", "id_repair"])]
    if len(idq):
        t = idq.groupby(["source_file", "raw_column", "issue"]).size().reset_index(name="Rows")
        t["Rows"] = t["Rows"].map("{:,}".format)
        L += _md_table(t) + [""]
    else:
        L += ["No blank, non-digit, too-long or repaired IDs were found.", ""]
    pad = pd.DataFrame([[k.replace(":", " / "), f"{v:,}"] for k, v in join["padded"].items()], columns=["File / column", "Rows padded"])
    L += _md_table(pad) + [""]
    L += ["Five sample keys:", ""]
    h = out.head(5)
    samp = pd.DataFrame({"combokey": h["combokey"], "combokey length": h["combokey"].str.len(),
                         "leaid": h["leaid"], "leaid length": h["leaid"].str.len(),
                         "schid": h["schid"], "schid length": h["schid"].str.len()})
    L += _md_table(samp) + [""]

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

    unexpected = q[q["issue"] == "unexpected_code"]
    L += [f"Negative values that are not 2015-16 reserved codes: {len(unexpected):,}.", ""]

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

    L += ["## FTE review", "",
          f"Schools with flag_fte_outlier: {int(out['flag_fte_outlier'].sum()):,} (teachers above {FTE_REVIEW_TEACHERS:,} "
          f"or any other core FTE above {FTE_REVIEW_OTHER}). " + ("999 values were set to NA by team decision but stay flagged. " if PLACEHOLDER_999_TO_NA else "999 values are kept and flagged. ") + "No other value was changed or capped.", "",
          "Largest 10 values per FTE column (combokey in brackets):", ""]
    top = []
    for name in FTE_COLS.values():
        t = out[["combokey", name]].dropna().nlargest(10, name)
        top.append([name, ", ".join(f"{v:g} ({k})" for k, v in zip(t["combokey"], t[name]))])
    L += _md_table(pd.DataFrame(top, columns=["Column", "Largest 10 values (combokey)"])) + [""]

    L += ["## Unresolved issues and notes", "",
          "- Restraint columns (MECH and PHYS) are not read. The EDA found restraint leaks the outcome (AUC 0.84 on its own in 2015-16).",
          "- flag_small_enrollment uses under 10 students (shared playbook).",
          "- pct_idea, pct_504 and pct_el are on a 0-100 scale and are NA when the subgroup is larger than enrollment_total.",
          "- flag_analysis_ready is True when the seclusion total is valid and enrollment_total is above 0. flag_missing_enrollment is True when enrollment_total is NA or not above 0.",
          ("- FTE 999 values (counselors, nurses, psychologists, social workers) were set to NA by recorded team decision and flagged." if PLACEHOLDER_999_TO_NA else "- FTE 999 values (counselors, nurses, psychologists, social workers) are kept and flagged: the audit says they look like placeholders, but their meaning is not documented. The team needs to record a decision (PLACEHOLDER_999_TO_NA in the script)."),
          "- FTE outliers (teachers > 2,000, other FTE > 200) are flagged and logged, not changed.",
          "- Playbook step 7: the manual has not been checked to confirm that WODIS, IDEA and 504 instances can be added. The seclusion mapping rows are marked unresolved until that is confirmed.",
          "- grade_band and support_fte_per_100 follow AI_CONTEXT.md section A4 (support_fte_per_100 = nurses + psychologists + social workers; counselors are not included).",
          "- The mapping file marks rows as unresolved: manual references were not re-checked against the 2015-16 manual.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    args = ap.parse_args()

    run_self_checks()
    result = clean(args.raw_dir)
    report = audit_report(result)
    print_audit_checks(report)
    paths = write_outputs(result, args.out_dir)
    validate_outputs(result, paths)
    write_mapping(args.docs_dir / "mapping_201516.csv")
    write_qa(result, report, args.docs_dir / "qa_201516.md")


if __name__ == "__main__":
    main()
