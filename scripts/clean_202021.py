"""Clean 2020-21 CRDC school and LEA files into the shared 50-column format.

Usage (from the repository root):

    python scripts/clean_202021.py \
        --raw-dir data/raw/2020-21 --out-dir data/processed/202021 \
        --docs-dir docs/cleaning

Follows cleaning_feature_playbook.md and AI_CONTEXT.md (sections A2-A5):
read as strings -> validate and pad IDs -> left-join school modules and LEA ->
recode reserved codes to NA -> build the shared columns and flags -> write
outputs.

Outputs (CSVs stay out of git; the docs are committed):
    schools_202021.csv            every school, shared 50 columns
    schools_202021_analysis.csv   rows where flag_analysis_ready is True
    quality_detail_202021.csv     problem log, one row per issue
    covid_indicators_202021.csv   optional extension keyed by combokey
    docs/cleaning/qa_202021.md
    docs/cleaning/mapping_202021.csv

2020-21 is the COVID year. Seclusion reporting is incomplete (-11 DQ
suppression, -13 virtual-only skip), so use it as a robustness / sensitivity
year, not the primary modeling year.

Contents
    Part A: cleaning (constants, readers, ID checks, joins, recode, features)
    Part B: checks and outputs
    Part C: documentation writers (mapping file and QA report)
"""

from __future__ import annotations

import argparse
import hashlib
import platform
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "2020-21"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "processed" / "202021"
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "cleaning"
YEAR = "2020-21"

CHAR_FILE = "School_Characteristics.csv"
ENR_FILE = "Enrollment.csv"
RS_FILE = "Restraint_and_Seclusion.csv"
SUP_FILE = "School_Support.csv"
DIND_FILE = "COVID_Directional_Indicators.csv"
LEA_FILE = "LEA_Characteristics.csv"

# ---------------------------------------------------------------------------
# Part A: cleaning
# ---------------------------------------------------------------------------

# Reserved codes for 2020-21 (manual s5.4; data audit). Any other negative
# value is still set to NA and logged as an unexpected code.
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

GRADE_COLS = [
    "SCH_GRADE_KG", "SCH_GRADE_G01", "SCH_GRADE_G02", "SCH_GRADE_G03", "SCH_GRADE_G04",
    "SCH_GRADE_G05", "SCH_GRADE_G06", "SCH_GRADE_G07", "SCH_GRADE_G08", "SCH_GRADE_G09",
    "SCH_GRADE_G10", "SCH_GRADE_G11", "SCH_GRADE_G12",
]
GRADE_EXTRA_COLS = ["SCH_GRADE_PS", "SCH_GRADE_UG"]  # read, left out of grade_band
STATUS_COLS = ["SCH_STATUS_SPED", "SCH_STATUS_MAGNET", "SCH_STATUS_CHARTER", "SCH_STATUS_ALT"]

CHAR_COLS = (
    ["LEA_STATE", "LEAID", "LEA_NAME", "SCHID", "SCH_NAME", "COMBOKEY", "JJ"]
    + STATUS_COLS + GRADE_EXTRA_COLS + GRADE_COLS
)
ENROLLMENT_PARTS = {
    "enr_idea": ("SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F"),
    "enr_504": ("SCH_ENR_504_M", "SCH_ENR_504_F"),
    "enr_el": ("SCH_ENR_LEP_M", "SCH_ENR_LEP_F"),  # LEP in 2020-21
}
ENR_COLS = ["TOT_ENR_M", "TOT_ENR_F"] + [c for pair in ENROLLMENT_PARTS.values() for c in pair]
# Restraint columns (MECH / PHYS) are intentionally NOT read: the EDA found they
# leak the outcome.
SECL_COLS = {
    "SCH_RSINSTANCES_SECL_WODIS": "seclusion_instances_wodis",
    "SCH_RSINSTANCES_SECL_IDEA": "seclusion_instances_idea",
    "SCH_RSINSTANCES_SECL_504": "seclusion_instances_504",
}
RS_COLS = list(SECL_COLS)
FTE_COLS = {
    "SCH_FTETEACH_TOT": "fte_teachers",
    "SCH_FTECOUNSELORS": "fte_counselors",
    "SCH_FTESERVICES_NUR": "fte_nurses",
    "SCH_FTESERVICES_PSY": "fte_psych",
    "SCH_FTESERVICES_SOC": "fte_social",
    "SCH_FTESECURITY_LEO": "fte_leo",
    "SCH_FTESECURITY_GUA": "fte_guards",
}
SUP_COLS = list(FTE_COLS)
SUPPORT_FTE_COLS = ["fte_nurses", "fte_psych", "fte_social"]  # counselors not included
DIND_COLS = ["SCH_DIND_INSTRUCTIONTYPE", "SCH_DIND_VIRTUALTYPE"]
LEA_REQUIRED = ["LEAID", "LEA_ENR", "LEA_SCHOOLS"]
LEA_OPTIONAL = ["LEA_NAME", "LEA_STATE"]
LEA_NUM_COLS = ["LEA_ENR", "LEA_SCHOOLS"]

COUNT_COLS = ENR_COLS + RS_COLS + SUP_COLS + LEA_NUM_COLS
FTE_RAW_COLS = set(FTE_COLS)
YES_NO_COLS = ["JJ"] + STATUS_COLS + GRADE_EXTRA_COLS + GRADE_COLS

# COVID directional indicator labels (2020-21 Appendix Workbook, sheet B).
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
# Reviewer asked for sch_virt_ind to come from flag_covid_virtual_only. The
# playbook says 2020-21 should leave it NA. Set to False to follow the playbook.
SCH_VIRT_FROM_COVID = True

SMALL_ENROLLMENT_CUTOFF = 10  # playbook: under 10 students
FTE_REVIEW_TEACHERS = 2000    # playbook step 10: teachers > 2,000
FTE_REVIEW_OTHER = 200        # playbook step 10: any other core FTE > 200

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
COVID_COLUMNS = [
    "year", "combokey", "covid_instruction_type", "covid_virtual_type",
    "flag_covid_virtual_only", "flag_covid_hybrid", "flag_dind_virtual_skip",
    "flag_dind_missing",
]
# Problem log columns, per AI_CONTEXT.md section A5 / playbook section 3.3.
QUALITY_COLUMNS = [
    "year", "source_file", "source_row", "combokey", "leaid", "raw_column",
    "raw_value", "issue", "action", "cleaned_value", "evidence",
]

# Which file and row column each raw / derived column comes from (for the log).
ROWCOL = {CHAR_FILE: "_row_char", ENR_FILE: "_row_enr", RS_FILE: "_row_rs",
          SUP_FILE: "_row_sup", DIND_FILE: "_row_dind", LEA_FILE: "_row_lea"}
COLUMN_SOURCE: dict[str, str] = {}
for _file, _cols in [
    (CHAR_FILE, CHAR_COLS), (ENR_FILE, ENR_COLS), (RS_FILE, RS_COLS), (SUP_FILE, SUP_COLS),
    (DIND_FILE, DIND_COLS), (LEA_FILE, LEA_NUM_COLS),
]:
    for _c in _cols:
        COLUMN_SOURCE[_c] = _file
COLUMN_SOURCE.update({"enr_idea": ENR_FILE, "enr_504": ENR_FILE, "enr_el": ENR_FILE})


def find_file(raw_dir: Path, name: str) -> Path:
    """Find a module CSV directly in raw_dir or in any subfolder (School/, LEA/...)."""
    direct = raw_dir / name
    if direct.exists():
        return direct
    norm = lambda n: n.lower().replace(" ", "_")  # noqa: E731
    for p in sorted(raw_dir.rglob("*.csv")):
        if norm(p.name) == norm(name):
            return p
    raise FileNotFoundError(f"{name} not found under {raw_dir}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_crdc_csv(
    path: Path, required: list[str], optional: list[str] | None = None, row_col: str = "_row"
) -> tuple[pd.DataFrame, dict]:
    """Read a CRDC CSV as strings. Tries utf-8-sig, then cp1252 (playbook step 1)."""
    optional = optional or []
    wanted = set(required) | set(optional)
    kwargs = dict(dtype=str, keep_default_na=False, skip_blank_lines=True,
                  usecols=lambda c: c.strip() in wanted)
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
    df[row_col] = np.arange(parsed) + 1  # first data row = 1 (playbook 3.3)
    empty = df.drop(columns=row_col).eq("").all(axis=1)
    if empty.any():
        df = df.loc[~empty].copy()
    info = {
        "file": path.name,
        "path": str(path),
        "encoding": encoding,
        "rows_parsed": parsed,
        "rows_kept": len(df),
        "sha256": sha256_of(path),
        "optional_missing": [c for c in optional if c not in df.columns],
    }
    print(f"Read {path.name}: {parsed:,} rows, kept {len(df):,}, encoding={encoding}")
    return df, info


def _log(df, mask, column, issue, action, values, cleaned, evidence, file=None) -> pd.DataFrame:
    """Build problem-log rows (playbook 3.3) for the rows where mask is True."""
    file = file or COLUMN_SOURCE.get(column, CHAR_FILE)
    rows = df.loc[mask]
    n = len(rows)
    rowcol = ROWCOL[file]

    def pick(x):
        if isinstance(x, str):
            return x
        return np.asarray(x[mask].astype(str))

    return pd.DataFrame(
        {
            "year": YEAR,
            "source_file": file,
            "source_row": rows[rowcol].to_numpy() if rowcol in rows else [pd.NA] * n,
            "combokey": rows["COMBOKEY"].to_numpy() if "COMBOKEY" in rows else [""] * n,
            "leaid": rows["LEAID"].to_numpy() if "LEAID" in rows else [""] * n,
            "raw_column": column,
            "raw_value": pick(values),
            "issue": issue,
            "action": action,
            "cleaned_value": pick(cleaned),
            "evidence": pick(evidence),
        }
    )


def validate_ids(df: pd.DataFrame, widths: dict[str, int], file: str, logs: list) -> tuple[pd.DataFrame, int]:
    """Check blank / non-digit / too-long IDs, then zero-pad short digit IDs.

    Non-digit IDs (for example state-operated programs) are kept as reported and
    logged. IDs are never converted through floats.
    """
    df = df.copy()
    padded = 0
    for col, width in widths.items():
        s = df[col]
        blank = s.eq("")
        nondigit = ~blank & ~s.str.fullmatch(r"\d+")
        too_long = s.str.len() > width
        for mask, issue, action, why in [
            (blank, "blank_id", "kept_blank", "ID is blank"),
            (nondigit, "non_digit_id", "kept_as_reported", "ID has non-digit characters"),
            (too_long, "id_too_long", "kept_as_reported", f"ID is longer than {width} characters"),
        ]:
            if mask.any():
                logs.append(_log(df, mask, col, issue, action, s, s, why, file=file))
        short = ~blank & ~nondigit & ~too_long & (s.str.len() < width)
        padded += int(short.sum())
        df[col] = s.where(~short, s.str.zfill(width))
    return df, padded


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
            logs.append(_log(df, neg & known, col, "reserved_code", "set_to_NA", codes.astype(str), "", ev))
            if (neg & ~known).any():
                logs.append(_log(df, neg & ~known, col, "unexpected_code", "set_to_NA", codes.astype(str), "",
                                 "negative code not in the 2020-21 reserved set"))
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
                logs.append(_log(df, frac, col, "fractional_count", "retained", raw, raw,
                                 "count is not a whole number"))
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
            ev = "reserved code " + codes.astype(str) + " (" + codes.map(RESERVED_GROUPS).fillna("unknown_code") + ")"
            logs.append(_log(df, neg, col, "reserved_code", "set_to_NA", codes.astype(str), "", ev))
        odd = raw.notna() & raw.ne("") & ~up.isin(["YES", "NO"]) & ~neg
        if odd.any():
            logs.append(_log(df, odd, col, "unexpected_category", "set_to_NA", raw, "",
                             "expected Yes or No"))
        df[col] = up.map({"YES": "Yes", "NO": "No"})
    return df, logs


def clean_dind(df: pd.DataFrame) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """COVID indicators are letter categories with reserved numeric codes mixed in."""
    df = df.copy()
    logs = []
    labels = {"SCH_DIND_INSTRUCTIONTYPE": INSTRUCTION_TYPE_LABELS, "SCH_DIND_VIRTUALTYPE": VIRTUAL_TYPE_LABELS}
    for col in DIND_COLS:
        raw = df[col]
        up = raw.str.upper()
        num = pd.to_numeric(raw, errors="coerce")
        neg = num < 0
        df[f"{col}_code"] = num.where(neg)
        if neg.any():
            codes = num.where(neg).astype("Int64")
            ev = "reserved code " + codes.astype(str) + " (" + codes.map(RESERVED_GROUPS).fillna("unknown_code") + ")"
            logs.append(_log(df, neg, col, "reserved_code", "set_to_NA", codes.astype(str), "", ev))
        odd = raw.notna() & raw.ne("") & ~up.isin(list(labels[col])) & ~neg
        if odd.any():
            logs.append(_log(df, odd, col, "unexpected_category", "set_to_NA", raw, "",
                             f"expected one of {sorted(labels[col])}"))
        df[col] = up.where(up.isin(list(labels[col])))
    return df, logs


def strict_sum(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Sum across columns; NA if any column is NA. Never fills with zero."""
    return df[cols].sum(axis=1, min_count=len(cols))


def pct_of_total(n: pd.Series, total: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (percent on a 0-100 scale, mask where subgroup > total)."""
    defined = n.notna() & total.notna() & (total > 0)
    exceeds = defined & (n > total)
    return (100.0 * n / total).where(defined & ~exceeds), exceeds


def grade_band(df: pd.DataFrame) -> pd.Series:
    """Grade band per playbook section 4. Preschool / ungraded are ignored.

    E = any KG-G5, M = any G6-G8, H = any G9-G12.
    Two or three of E/M/H -> span; only one -> elementary / middle / high;
    none -> other; any KG-G12 flag unknown -> NA.
    """
    flags = df[GRADE_COLS]
    known = flags.isin(["Yes", "No"]).all(axis=1)
    yes = flags.eq("Yes")
    e = yes[GRADE_COLS[:6]].any(axis=1)
    m = yes[GRADE_COLS[6:9]].any(axis=1)
    h = yes[GRADE_COLS[9:]].any(axis=1)
    n_groups = e.astype(int) + m.astype(int) + h.astype(int)
    band = pd.Series("span", index=df.index, dtype="object")
    band[n_groups == 0] = "other"
    band[(n_groups == 1) & e] = "elementary"
    band[(n_groups == 1) & m] = "middle"
    band[(n_groups == 1) & h] = "high"
    band[~known] = pd.NA
    return band


def _norm_name(s: pd.Series) -> pd.Series:
    return s.str.casefold().str.replace(r"\s+", " ", regex=True)


def join_module(roster, mod, name, file, joins, logs):
    """Left-join one module on COMBOKEY (one_to_one). Log missing and extra keys."""
    dup = int(mod["COMBOKEY"].duplicated().sum())
    if dup:
        raise ValueError(f"{dup} duplicate COMBOKEY values in {file}; check them before continuing")
    missing = ~roster["COMBOKEY"].isin(mod["COMBOKEY"])
    extra = ~mod["COMBOKEY"].isin(roster["COMBOKEY"])
    if missing.any():
        logs.append(_log(roster, missing, "COMBOKEY", "missing_module_row", "kept_roster_row",
                         roster["COMBOKEY"], "", f"no row in {file}", file=CHAR_FILE))
    if extra.any():
        logs.append(_log(mod, extra, "COMBOKEY", "extra_module_key", "ignored",
                         mod["COMBOKEY"], "", "key not in School Characteristics", file=file))
    merged = roster.merge(mod, on="COMBOKEY", how="left", validate="one_to_one")
    if len(merged) != len(roster):
        raise ValueError(f"Join with {file} changed the roster row count")
    merged[f"_missing_{name}"] = missing.to_numpy()
    joins.append({"Join": name, "Key": "combokey", "Roster rows": len(roster), "Module rows": len(mod),
                  "Roster keys missing": int(missing.sum()), "Extra keys": int(extra.sum()),
                  "Matched": int((~missing).sum())})
    return merged


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[pd.DataFrame]]:
    """Return (shared 50-column table, COVID extension table, extra problem-log rows)."""
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

    for raw, name in SECL_COLS.items():
        out[name] = df[raw]
    out["seclusion_instances"] = strict_sum(df, list(SECL_COLS))

    out["enrollment_total"] = strict_sum(df, ["TOT_ENR_M", "TOT_ENR_F"])
    out["enr_nonbinary"] = np.nan  # not collected in 2020-21
    enr = out["enrollment_total"]
    for name, (m_col, f_col) in ENROLLMENT_PARTS.items():
        out[name] = strict_sum(df, [m_col, f_col])
    rate_ok = out["seclusion_instances"].notna() & enr.notna() & (enr > 0)
    out["seclusion_rate"] = (100.0 * out["seclusion_instances"] / enr).where(rate_ok)

    out["sch_status_sped"] = df["SCH_STATUS_SPED"]
    out["sch_status_charter"] = df["SCH_STATUS_CHARTER"]
    out["sch_status_alt"] = df["SCH_STATUS_ALT"]
    out["sch_status_magnet"] = df["SCH_STATUS_MAGNET"]

    instr = df["SCH_DIND_INSTRUCTIONTYPE"]
    if SCH_VIRT_FROM_COVID:
        out["sch_virt_ind"] = pd.Series(pd.NA, index=df.index, dtype="object")
        out.loc[instr.notna(), "sch_virt_ind"] = "No"
        out.loc[instr.eq("B"), "sch_virt_ind"] = "Yes"
    else:
        out["sch_virt_ind"] = pd.NA
    out["grade_band"] = grade_band(df)

    # FTE: review flags only. No value is changed (playbook step 10).
    outlier_any = pd.Series(False, index=df.index)
    for raw, name in FTE_COLS.items():
        s = df[raw]
        out[name] = s
        cap = FTE_REVIEW_TEACHERS if raw == "SCH_FTETEACH_TOT" else FTE_REVIEW_OTHER
        over = s.notna() & (s > cap)
        if over.any():
            logs.append(_log(df, over, raw, "fte_outlier", "retained", s, s,
                             f"FTE is above the review cutoff of {cap:,}"))
        outlier_any |= over
    out["flag_fte_outlier"] = outlier_any
    out["counselors_per_100"] = (100.0 * out["fte_counselors"] / enr).where(enr > 0)
    out["teachers_per_100"] = (100.0 * out["fte_teachers"] / enr).where(enr > 0)
    support_total = strict_sum(out, SUPPORT_FTE_COLS)
    out["support_fte_per_100"] = (100.0 * support_total / enr).where(enr > 0)

    for share, count in [("pct_idea", "enr_idea"), ("pct_504", "enr_504"), ("pct_el", "enr_el")]:
        out[share], exceeds = pct_of_total(out[count], enr)
        if exceeds.any():
            logs.append(_log(df, exceeds, count, "subgroup_exceeds_total", "pct_set_to_NA", out[count], "",
                             "subgroup count is larger than enrollment_total"))

    out["lea_enrollment"] = df["LEA_ENR"]
    out["lea_schools"] = df["LEA_SCHOOLS"]

    out["flag_missing_seclusion"] = out["seclusion_instances"].isna()
    out["flag_missing_enrollment"] = ~(enr > 0)  # NA or not above 0
    out["flag_small_enrollment"] = enr.notna() & (enr < SMALL_ENROLLMENT_CUTOFF)
    for col in ["flag_partial_enrollment", "flag_partial_idea", "flag_partial_504", "flag_partial_el"]:
        out[col] = False  # no nonbinary (X) counts in 2020-21
    out["flag_missing_module"] = df[["_missing_enr", "_missing_rs", "_missing_sup"]].any(axis=1)
    out["flag_missing_lea"] = df["_missing_lea"]
    out["flag_analysis_ready"] = ~out["flag_missing_seclusion"] & enr.notna() & (enr > 0)

    covid = pd.DataFrame(index=df.index)
    covid["year"] = YEAR
    covid["combokey"] = df["COMBOKEY"]
    covid["covid_instruction_type"] = instr.map(INSTRUCTION_TYPE_LABELS)
    covid["covid_virtual_type"] = df["SCH_DIND_VIRTUALTYPE"].map(VIRTUAL_TYPE_LABELS)
    covid["flag_covid_virtual_only"] = instr.eq("B")
    covid["flag_covid_hybrid"] = instr.eq("C")
    covid["flag_dind_virtual_skip"] = df["SCH_DIND_VIRTUALTYPE_code"].eq(-13)
    covid["flag_dind_missing"] = instr.isna() | df["SCH_DIND_VIRTUALTYPE"].isna()

    return out[OUTPUT_COLUMNS], covid[COVID_COLUMNS], logs


def load_and_join(raw_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Steps 1-3: read, validate IDs, join school modules and LEA."""
    logs: list[pd.DataFrame] = []
    sources: list[dict] = []

    char, info = read_crdc_csv(find_file(raw_dir, CHAR_FILE), CHAR_COLS, row_col="_row_char")
    sources.append(info)
    mods = {}
    for name, file, cols, rowcol in [
        ("enr", ENR_FILE, ENR_COLS, "_row_enr"),
        ("rs", RS_FILE, RS_COLS, "_row_rs"),
        ("sup", SUP_FILE, SUP_COLS, "_row_sup"),
        ("dind", DIND_FILE, DIND_COLS, "_row_dind"),
    ]:
        mods[name], info = read_crdc_csv(find_file(raw_dir, file), ["COMBOKEY"] + cols, row_col=rowcol)
        sources.append(info)
    lea, info = read_crdc_csv(find_file(raw_dir, LEA_FILE), LEA_REQUIRED, LEA_OPTIONAL, row_col="_row_lea")
    sources.append(info)

    # IDs: validate, then pad.
    padded = {}
    char, padded[CHAR_FILE] = validate_ids(char, {"LEAID": 7, "SCHID": 5, "COMBOKEY": 12}, CHAR_FILE, logs)
    for name, file in [("enr", ENR_FILE), ("rs", RS_FILE), ("sup", SUP_FILE), ("dind", DIND_FILE)]:
        mods[name], padded[file] = validate_ids(mods[name], {"COMBOKEY": 12}, file, logs)
    lea, padded[LEA_FILE] = validate_ids(lea, {"LEAID": 7}, LEA_FILE, logs)

    n_schools = len(char)
    dup = int(char["COMBOKEY"].duplicated().sum())
    if dup:
        raise ValueError(f"{dup} duplicate COMBOKEY values in {CHAR_FILE}; check them before continuing")
    mismatch = char["LEAID"] + char["SCHID"] != char["COMBOKEY"]
    if mismatch.any():
        logs.append(_log(char, mismatch, "COMBOKEY", "combokey_component_mismatch", "kept_stored_combokey",
                         char["COMBOKEY"], char["COMBOKEY"], "COMBOKEY differs from LEAID + SCHID", file=CHAR_FILE))
    print(f"COMBOKEY: {char['COMBOKEY'].nunique():,} unique keys from {n_schools:,} rows; "
          f"{int(mismatch.sum()):,} differ from LEAID + SCHID")

    # Roster + modules.
    joins: list[dict] = []
    df = char
    for name, file in [("enr", ENR_FILE), ("rs", RS_FILE), ("sup", SUP_FILE), ("dind", DIND_FILE)]:
        df = join_module(df, mods[name], name, file, joins, logs)

    # District join.
    lea_dup = int(lea["LEAID"].duplicated().sum())
    if lea_dup:
        raise ValueError(f"{lea_dup} duplicate LEAID values in {LEA_FILE}; check them before continuing")
    missing_lea = ~df["LEAID"].isin(lea["LEAID"])
    lea = lea.rename(columns={"LEA_NAME": "LEA_NAME_lea", "LEA_STATE": "LEA_STATE_lea"})
    df = df.merge(lea, on="LEAID", how="left", validate="many_to_one")
    if len(df) != n_schools:
        raise ValueError("LEA join changed the school row count")
    df["_missing_lea"] = missing_lea.to_numpy()
    if missing_lea.any():
        logs.append(_log(df, missing_lea, "LEAID", "lea_unmatched", "kept", df["LEAID"], df["LEAID"],
                         f"district not found in {LEA_FILE}", file=CHAR_FILE))
    joins.append({"Join": "lea", "Key": "leaid", "Roster rows": n_schools, "Module rows": len(lea),
                  "Roster keys missing": int(missing_lea.sum()),
                  "Extra keys": int((~lea["LEAID"].isin(df["LEAID"])).sum()),
                  "Matched": int((~missing_lea).sum())})
    for sch_col, lea_col, issue in [("LEA_NAME", "LEA_NAME_lea", "lea_name_disagreement"),
                                    ("LEA_STATE", "LEA_STATE_lea", "lea_state_disagreement")]:
        if lea_col in df:
            both = ~missing_lea & df[lea_col].notna() & df[lea_col].ne("") & df[sch_col].ne("")
            diff = both & (_norm_name(df[sch_col]) != _norm_name(df[lea_col].fillna("")))
            if diff.any():
                keep = "kept_lea_file_value" if sch_col == "LEA_NAME" else "kept_school_file_value"
                logs.append(_log(df, diff, sch_col, issue, keep, df[sch_col], df[lea_col],
                                 f"school file and {LEA_FILE} disagree", file=CHAR_FILE))
    print(f"Schools with no LEA match: {int(missing_lea.sum()):,}")

    ctx = {
        "logs": logs, "sources": sources, "joins": joins, "padded": padded,
        "info": {"n_schools": n_schools, "unique_combokey": int(char["COMBOKEY"].nunique()),
                 "key_mismatch": int(mismatch.sum()), "unmatched_lea": int(missing_lea.sum())},
    }
    return df, ctx


def recode_and_build(df: pd.DataFrame, ctx: dict) -> dict:
    """Steps 4-5: recode reserved codes, then build the shared columns."""
    logs = list(ctx["logs"])
    # Recode.
    df, recode_logs = recode_reserved(df, COUNT_COLS)
    logs += recode_logs
    df, yn_logs = clean_yes_no(df, YES_NO_COLS)
    logs += yn_logs
    df, dind_logs = clean_dind(df)
    logs += dind_logs

    out, covid, feature_logs = build_features(df)
    logs += feature_logs
    quality = pd.concat(logs, ignore_index=True) if logs else pd.DataFrame(columns=QUALITY_COLUMNS)
    quality = quality[QUALITY_COLUMNS].copy()
    quality["source_row"] = pd.to_numeric(quality["source_row"]).astype("Int64")
    return {
        "work": df, "out": out, "covid": covid, "quality": quality, "sources": ctx["sources"],
        "joins": ctx["joins"], "padded": ctx["padded"], "info": ctx["info"],
    }


def clean(raw_dir: Path) -> dict:
    df, ctx = load_and_join(raw_dir)
    return recode_and_build(df, ctx)


# ---------------------------------------------------------------------------
# Part B: checks and outputs
# ---------------------------------------------------------------------------

AUDIT_EXPECTED = {
    "n_schools": 97575,
    "unique_combokey": 97575,
    "key_mismatch": 0,
    "unmatched_lea": 0,
    "rows_lost_in_join": 0,
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
}


def code_count(q: pd.DataFrame, col: str, code: int) -> int:
    m = (q["raw_column"] == col) & (q["issue"] == "reserved_code") & (q["raw_value"] == str(code))
    return int(m.sum())


def audit_report(result: dict) -> dict:
    df, out, q, info = result["work"], result["out"], result["quality"], result["info"]
    jj = out["jj"].eq("Yes")
    guard_neg9 = q[(q["raw_column"] == "SCH_FTESECURITY_GUA") & (q["raw_value"] == "-9")]["combokey"]
    instr = df["SCH_DIND_INSTRUCTIONTYPE"]
    wodis_neg13 = (q["raw_column"] == "SCH_RSINSTANCES_SECL_WODIS") & (q["raw_value"] == "-13") & (q["issue"] == "reserved_code")
    neg13_keys = set(q.loc[wodis_neg13, "combokey"])
    return {
        "n_schools": info["n_schools"],
        "unique_combokey": info["unique_combokey"],
        "key_mismatch": info["key_mismatch"],
        "unmatched_lea": info["unmatched_lea"],
        "rows_lost_in_join": info["n_schools"] - len(out),
        "jj_yes": int(jj.sum()),
        "seclusion_all_three_valid": int(out["seclusion_instances"].notna().sum()),
        "wodis_neg9": code_count(q, "SCH_RSINSTANCES_SECL_WODIS", -9),
        "wodis_neg11": code_count(q, "SCH_RSINSTANCES_SECL_WODIS", -11),
        "wodis_neg13": code_count(q, "SCH_RSINSTANCES_SECL_WODIS", -13),
        "wodis_neg5": code_count(q, "SCH_RSINSTANCES_SECL_WODIS", -5),
        "wodis_positive": int((df["SCH_RSINSTANCES_SECL_WODIS"] > 0).sum()),
        "idea_positive": int((df["SCH_RSINSTANCES_SECL_IDEA"] > 0).sum()),
        "enr_m_usable": int(df["TOT_ENR_M"].notna().sum()),
        "enr_f_usable": int(df["TOT_ENR_F"].notna().sum()),
        "enr_m_neg11": code_count(q, "TOT_ENR_M", -11),
        "enr_f_neg11": code_count(q, "TOT_ENR_F", -11),
        "enr_m_zero": int((df["TOT_ENR_M"] == 0).sum()),
        "enr_sum_zero": int((out["enrollment_total"] == 0).sum()),
        # Information only (compared with the data audit, not hard checks).
        "jj_guard_neg9": int(out.loc[jj, "combokey"].isin(set(guard_neg9)).sum()),
        "dind_virtual_neg13": int(df["SCH_DIND_VIRTUALTYPE_code"].eq(-13).sum()),
        "dind_neg13_not_AD": int((df["SCH_DIND_VIRTUALTYPE_code"].eq(-13) & ~instr.isin(["A", "D"])).sum()),
        "secl_neg13_not_virtual_only": int((out["combokey"].isin(neg13_keys) & instr.ne("B")).sum()),
        "secl_neg13_virtual_only": int((out["combokey"].isin(neg13_keys) & instr.eq("B")).sum()),
    }


def print_audit_checks(report: dict) -> None:
    print("\nAudit checks (expected vs observed)")
    for key, exp in AUDIT_EXPECTED.items():
        obs = report[key]
        status = "OK" if obs == exp else "DIFF"
        print(f"  {status:4} {key}: expected {exp:,}  observed {obs:,}")
    print(f"  info JJ schools with security guard FTE = -9: {report['jj_guard_neg9']:,} (audit: 573 of 579)")
    print(f"  info DIND virtual -13 where instruction type is not A/D: {report['dind_neg13_not_AD']:,} (expect 0)")
    print(f"  info seclusion -13 where instruction type is not B: {report['secl_neg13_not_virtual_only']:,} (expect 0)")


def run_self_checks() -> None:
    """Small unit checks of the cleaning rules, run before every cleaning run."""
    f = pd.DataFrame
    # strict sums: any NA makes the total NA; zeros stay zeros.
    s = strict_sum(f({"a": [1.0, np.nan, 0.0], "b": [2.0, 3.0, 0.0]}), ["a", "b"])
    assert s.iloc[0] == 3 and np.isnan(s.iloc[1]) and s.iloc[2] == 0
    # percentages: NA when subgroup > total, total missing or zero.
    p, ex = pct_of_total(pd.Series([5.0, 12.0, 1.0, 1.0]), pd.Series([10.0, 10.0, np.nan, 0.0]))
    assert p.iloc[0] == 50 and np.isnan(p.iloc[1]) and ex.iloc[1] and np.isnan(p.iloc[2]) and np.isnan(p.iloc[3])
    # grade band.
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
    # ID checks: pad short digit IDs, keep letters, log both.
    ids = f({"COMBOKEY": ["123", "24SOP02", ""], "_row_char": [1, 2, 3], "LEAID": ["", "", ""]})
    logs: list = []
    padded, n = validate_ids(ids, {"COMBOKEY": 12}, CHAR_FILE, logs)
    assert padded["COMBOKEY"].iloc[0] == "123".zfill(12) and padded["COMBOKEY"].iloc[1] == "24SOP02" and n == 1
    assert {"blank_id", "non_digit_id"} <= set(pd.concat(logs)["issue"])
    # reserved codes.
    r = f({"COMBOKEY": ["1", "2"], "LEAID": ["", ""], "_row_enr": [1, 2], "TOT_ENR_M": ["-11", "0"]})
    r, lg = recode_reserved(r, ["TOT_ENR_M"])
    assert np.isnan(r["TOT_ENR_M"].iloc[0]) and r["TOT_ENR_M"].iloc[1] == 0 and len(lg) == 1
    print("Self-checks passed")


def validate_outputs(result: dict, paths: dict) -> None:
    """Reload the written files with explicit dtypes and check them (playbook section 6)."""
    ids = {"combokey": str, "leaid": str, "schid": str}
    full = pd.read_csv(paths["full"], dtype=ids, float_precision="round_trip")
    ana = pd.read_csv(paths["analysis"], dtype=ids, float_precision="round_trip")
    assert list(full.columns) == OUTPUT_COLUMNS and len(OUTPUT_COLUMNS) == 50, "column schema"
    assert len(full) == result["info"]["n_schools"], "full table must keep every roster school"
    assert full["combokey"].is_unique, "combokey must be unique"
    ok = full["combokey"].str.fullmatch(r"\d{12}") | full["combokey"].isin(result["quality"].query("issue == 'non_digit_id'")["raw_value"])
    assert ok.all(), "combokey values must be 12 digits (except logged non-digit IDs)"
    assert full["leaid"].str.len().eq(7).all() and full["schid"].str.len().eq(5).all(), "ID lengths"
    flags = [c for c in OUTPUT_COLUMNS if c.startswith("flag_")]
    for c in flags:
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
        "full": out_dir / "schools_202021.csv",
        "analysis": out_dir / "schools_202021_analysis.csv",
        "quality": out_dir / "quality_detail_202021.csv",
        "covid": out_dir / "covid_indicators_202021.csv",
    }
    out.to_csv(paths["full"], index=False, encoding="utf-8")
    out.loc[out["flag_analysis_ready"]].to_csv(paths["analysis"], index=False, encoding="utf-8")
    result["quality"].to_csv(paths["quality"], index=False, encoding="utf-8")
    result["covid"].to_csv(paths["covid"], index=False, encoding="utf-8")
    for p in paths.values():
        print(f"Wrote {p}")
    return paths


# ---------------------------------------------------------------------------
# Part C: documentation (mapping file and QA report)
# ---------------------------------------------------------------------------

MAPPING_HEADER = [
    "source_file", "source_column", "shared_output_column", "transformation",
    "units_population_period", "manual_reference", "verification_status",
]
_REF = "2020-21 CRDC data layout; not re-checked against the manual"
_CODES = "2020-21 manual s5.4 reserved codes"


def mapping_rows() -> list[list[str]]:
    rows = [
        [CHAR_FILE, "LEAID", "leaid", "Validate, zero-pad to 7", "District ID, 2020-21", _REF, "unverified"],
        [CHAR_FILE, "SCHID", "schid", "Validate, zero-pad to 5", "School ID, 2020-21", _REF, "unverified"],
        [CHAR_FILE, "COMBOKEY", "combokey", "Validate, zero-pad to 12, roster join key; compared with LEAID + SCHID", "School ID, 2020-21", _REF, "verified"],
        [LEA_FILE, "LEAID", "leaid", "Validate, zero-pad to 7, join key", "District ID, 2020-21", _REF, "unverified"],
        [CHAR_FILE, "LEA_STATE", "lea_state", "Trim, uppercase; compared with the LEA file", "State code, 2020-21", "Descriptive field", "unresolved"],
        [CHAR_FILE, "SCH_NAME", "sch_name", "Trim", "School name, 2020-21", "Descriptive field", "unresolved"],
        [CHAR_FILE, "LEA_NAME", "", "Compared with the LEA file, not output", "District name, 2020-21", "Descriptive field", "unresolved"],
        [LEA_FILE, "LEA_NAME", "lea_name", "Trim; district name comes from the LEA file", "District name, 2020-21", "Descriptive field", "unresolved"],
        [LEA_FILE, "LEA_STATE", "", "Compared with the school file, not output", "State code, 2020-21", "Descriptive field", "unresolved"],
        [CHAR_FILE, "JJ", "jj", "Yes/No/NA", "School, justice facility, 2020-21", _REF, "unresolved"],
        [CHAR_FILE, "(none)", "enr_nonbinary", "Always NA: no nonbinary counts in 2020-21", "Students, 2020-21", "Not collected", "verified"],
        [DIND_FILE, "SCH_DIND_INSTRUCTIONTYPE", "sch_virt_ind", "Yes if instruction type is B (virtual only), No if A/C/D, NA if unknown. Requested in PR review; the playbook says to leave NA", "School, COVID instruction mode, 2020-21", "PR #27 review vs playbook section 5", "unresolved"],
    ]
    for c in STATUS_COLS:
        rows.append([CHAR_FILE, c, c.lower().replace("sch_status_", "sch_status_"), "Yes/No/NA", "School, 2020-21", _REF, "unverified"])
    for c in GRADE_EXTRA_COLS:
        rows.append([CHAR_FILE, c, "", "Read, left out of grade_band", "Preschool / ungraded flag, 2020-21", _REF, "unverified"])
    for c in GRADE_COLS:
        rows.append([CHAR_FILE, c, "grade_band", "Yes/No; combined by the grade-band rule (elementary, middle, high, span, other)", "Grade offered, 2020-21", _REF, "unverified"])
    for c in ["TOT_ENR_M", "TOT_ENR_F"]:
        rows.append([ENR_FILE, c, "enrollment_total", "Calculated total M+F; NA if either is NA", "Students, overall, 2020-21 (preschool coverage not stated)", _REF, "unresolved"])
    labels = {"enr_idea": "IDEA", "enr_504": "Section 504 only", "enr_el": "EL (LEP in 2020-21)"}
    for name, (m, f) in ENROLLMENT_PARTS.items():
        for c in (m, f):
            rows.append([ENR_FILE, c, name, "Count; M+F strict", f"Students, {labels[name]}, 2020-21", _REF, "unverified"])
    for raw, name in SECL_COLS.items():
        rows.append([RS_FILE, raw, name, f"Count; summed with the other two groups, NA if any is NA. Reserved codes: {_CODES}", "Instances of seclusion (not students), 2020-21", _REF, "unverified"])
    for raw, name in FTE_COLS.items():
        rows.append([SUP_FILE, raw, name, "Numeric FTE, fractions kept; flagged if teachers > 2,000 or other FTE > 200, never changed", "FTE (decimal), 2020-21", _REF, "unverified"])
    rows.append([LEA_FILE, "LEA_ENR", "lea_enrollment", "Count", "Students in district, 2020-21", _REF, "unverified"])
    rows.append([LEA_FILE, "LEA_SCHOOLS", "lea_schools", "Count", "Public schools in district, 2020-21", _REF, "unverified"])
    rows.append([DIND_FILE, "SCH_DIND_INSTRUCTIONTYPE", "(covid_indicators) covid_instruction_type, flag_covid_virtual_only, flag_covid_hybrid", "Letter category A-D with labels; reserved codes to NA (logged)", "School, COVID instruction mode, 2020-21", "2020-21 Appendix Workbook, sheet B", "unverified"])
    rows.append([DIND_FILE, "SCH_DIND_VIRTUALTYPE", "(covid_indicators) covid_virtual_type, flag_dind_virtual_skip", "Letter category A-C with labels; -13 is a structural skip (no virtual instruction)", "School, COVID virtual mode, 2020-21", "2020-21 Appendix Workbook, sheet B", "unverified"])
    rows.append([RS_FILE, "SCH_RSINSTANCES_MECH_* / SCH_RSINSTANCES_PHYS_* / TOT_RS_*", "", "Not read: restraint leaks the outcome (AUC 0.84 on its own in 2015-16); student counts are not instances", "Restraint, 2020-21", "Team EDA", "verified"])
    return rows


def write_mapping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(mapping_rows(), columns=MAPPING_HEADER).to_csv(path, index=False)
    print(f"Wrote {path}")


def _md_table(df: pd.DataFrame) -> list[str]:
    lines = ["| " + " | ".join(str(c) for c in df.columns) + " |", "|" + "---|" * len(df.columns)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return lines


def _fmt(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = df[c].map("{:,}".format)
    return df


def write_qa(result: dict, report: dict, path: Path, raw_dir: Path) -> None:
    """QA report with no timestamps, so reruns give identical text."""
    out, q, covid, work = result["out"], result["quality"], result["covid"], result["work"]
    L: list[str] = []
    L += ["# QA report for 2020-21 CRDC cleaning", "",
          "This file is written by `scripts/clean_202021.py`. Do not edit it by hand.", ""]
    L += ["## How to rerun", "", "```text",
          "python scripts/clean_202021.py --raw-dir data/raw/2020-21 "
          "--out-dir data/processed/202021 --docs-dir docs/cleaning", "```", "",
          f"Dependencies are listed in requirements.txt. This run used Python {platform.python_version()}, "
          f"pandas {pd.__version__}, numpy {np.__version__}.", ""]

    L += ["## Sources", ""]
    src = pd.DataFrame(result["sources"])
    src["path"] = [str(Path(p).relative_to(raw_dir)) if Path(p).is_relative_to(raw_dir) else Path(p).name for p in src["path"]]
    src = _fmt(src, ["rows_parsed", "rows_kept"])[["path", "encoding", "rows_parsed", "rows_kept", "sha256"]]
    L += _md_table(src) + [""]
    miss_opt = [f"{s['file']}: {', '.join(s['optional_missing'])}" for s in result["sources"] if s["optional_missing"]]
    if miss_opt:
        L += ["Optional columns not found: " + "; ".join(miss_opt) + ".", ""]
    L += ["Manual and appendix files were not available to the script, so their hashes are not listed. "
          "Add them here when the team records the package version.", ""]

    L += ["## Row counts", ""]
    ana = out[out["flag_analysis_ready"]]
    rows = pd.DataFrame([
        ["Roster schools (full table)", f"{len(out):,}", f"{AUDIT_EXPECTED['n_schools']:,}"],
        ["Analysis-ready schools", f"{len(ana):,}", "Recomputed, not matched"],
        ["Schools with all three seclusion fields valid", f"{report['seclusion_all_three_valid']:,}", f"{AUDIT_EXPECTED['seclusion_all_three_valid']:,}"],
        ["Rows in covid_indicators_202021.csv", f"{len(covid):,}", "Same as roster"],
    ], columns=["Item", "Count", "Audit comparison"])
    L += _md_table(rows) + [""]

    L += ["## IDs", "",
          f"{result['info']['unique_combokey']:,} unique combokeys from {result['info']['n_schools']:,} rows. "
          f"{result['info']['key_mismatch']:,} differ from leaid + schid.", ""]
    idq = q[q["issue"].isin(["blank_id", "non_digit_id", "id_too_long", "combokey_component_mismatch"])]
    if len(idq):
        t = idq.groupby(["source_file", "raw_column", "issue"]).size().reset_index(name="Rows")
        L += _md_table(_fmt(t, ["Rows"])) + [""]
    else:
        L += ["No blank, non-digit, too-long or mismatched IDs were found.", ""]
    pad = pd.DataFrame([[f, f"{n:,}"] for f, n in result["padded"].items()], columns=["File", "Rows with an ID padded"])
    L += _md_table(pad) + [""]
    L += ["Five sample keys:", ""]
    h = out.head(5)
    samp = pd.DataFrame({"combokey": h["combokey"], "combokey length": h["combokey"].str.len(),
                         "leaid": h["leaid"], "leaid length": h["leaid"].str.len(),
                         "schid": h["schid"], "schid length": h["schid"].str.len()})
    L += _md_table(samp) + [""]

    L += ["## Joins", ""]
    jt = _fmt(pd.DataFrame(result["joins"]), ["Roster rows", "Module rows", "Roster keys missing", "Extra keys", "Matched"])
    L += _md_table(jt) + [""]
    L += ["Every join kept the roster row count. Missing and extra keys are listed one by one in the quality detail file.", ""]

    L += ["## Audit checks", ""]
    chk = pd.DataFrame([[k, f"{v:,}", f"{report[k]:,}", "OK" if report[k] == v else "DIFF"] for k, v in AUDIT_EXPECTED.items()],
                       columns=["Check", "Expected", "Observed", "Status"])
    L += _md_table(chk) + [""]
    L += [f"Information only: JJ schools with security guard FTE = -9: {report['jj_guard_neg9']:,} (audit: 573 of 579).", ""]

    L += ["## Missing values by output column", ""]
    miss = out.drop(columns=["year"]).isna().sum()
    miss = miss[miss > 0]
    mt = pd.DataFrame({"Column": miss.index, "Missing rows": [f"{v:,}" for v in miss.values],
                       "Share": [f"{100 * v / len(out):.1f}%" for v in miss.values]})
    L += _md_table(mt) + [""]
    L += ["`enr_nonbinary` is always NA because 2020-21 does not collect it. "
          + ("`sch_virt_ind` comes from the COVID instruction type (see unresolved issues)." if SCH_VIRT_FROM_COVID else "`sch_virt_ind` is always NA."), ""]
    L += ["Reserved codes by raw column (counts of values set to NA):", ""]
    rc = q[q["issue"] == "reserved_code"]
    if len(rc):
        piv = rc.pivot_table(index="raw_column", columns="raw_value", values="combokey", aggfunc="count", fill_value=0)
        piv = piv[sorted(piv.columns, key=int)].reset_index().rename(columns={"raw_column": "Raw column"})
        piv = _fmt(piv, list(piv.columns[1:]))
        L += _md_table(piv) + [""]
    unexpected = q[q["issue"] == "unexpected_code"]
    L += [f"Negative values that are not 2020-21 reserved codes: {len(unexpected):,}.", ""]

    L += ["## COVID-year seclusion gaps", "",
          f"- {report['wodis_neg11']:,} schools have seclusion instances suppressed for data quality (-11).",
          f"- {report['wodis_neg13']:,} schools were skipped on the seclusion module as virtual-only (-13). "
          f"Of those, {report['secl_neg13_virtual_only']:,} have COVID instruction type B and "
          f"{report['secl_neg13_not_virtual_only']:,} do not (audit expects 0).",
          f"- {report['dind_virtual_neg13']:,} schools have -13 on the COVID virtual-type field. "
          f"{report['dind_neg13_not_AD']:,} of them have an instruction type other than A or D (expect 0).",
          f"- {int(out['flag_missing_seclusion'].sum()):,} schools in total have no valid seclusion total "
          f"({100 * out['flag_missing_seclusion'].mean():.1f}% of the roster). They are flagged, never filled with 0.", ""]
    ct = pd.crosstab(work["SCH_DIND_INSTRUCTIONTYPE"].fillna("NA"), out["flag_missing_seclusion"].map({True: "missing seclusion", False: "valid seclusion"}))
    ct = ct.reset_index().rename(columns={"SCH_DIND_INSTRUCTIONTYPE": "COVID instruction type"})
    L += _md_table(_fmt(ct, list(ct.columns[1:]))) + [""]

    L += ["## Quality log summary", ""]
    qs = q.groupby(["issue", "action"]).size().reset_index(name="Rows")
    L += _md_table(_fmt(qs, ["Rows"]).rename(columns={"issue": "Issue", "action": "Action"})) + [""]
    L += ["Row-level detail is in `quality_detail_202021.csv`, including the original reserved code and its reason group in the evidence column.", ""]

    L += ["## Counts by group", ""]
    flags = ["flag_small_enrollment", "flag_fte_outlier", "flag_missing_seclusion", "flag_missing_enrollment",
             "flag_missing_module", "flag_missing_lea", "flag_partial_enrollment", "flag_partial_idea",
             "flag_partial_504", "flag_partial_el", "flag_analysis_ready"]
    gr = [[f"jj = {v}", f"{int(out['jj'].eq(v).sum()):,}", f"{int(ana['jj'].eq(v).sum()):,}"] for v in ["Yes", "No"]]
    gr.append(["jj missing", f"{int(out['jj'].isna().sum()):,}", f"{int(ana['jj'].isna().sum()):,}"])
    gr += [[f"{f} = True", f"{int(out[f].sum()):,}", f"{int(ana[f].sum()):,}"] for f in flags]
    L += _md_table(pd.DataFrame(gr, columns=["Group", "Full table", "Analysis table"])) + [""]
    L += ["No nonbinary (X) counts exist in 2020-21, so no total is partial and every flag_partial_* is False.", ""]
    L += ["grade_band counts (full table; NA means a KG-12 grade flag was unknown):", ""]
    gb = out["grade_band"].fillna("NA").value_counts().rename_axis("grade_band").reset_index(name="Rows")
    L += _md_table(_fmt(gb, ["Rows"])) + [""]

    L += ["## FTE review", "",
           f"Schools with flag_fte_outlier: {int(out['flag_fte_outlier'].sum()):,} (teachers above {FTE_REVIEW_TEACHERS:,} "
           f"or any other core FTE above {FTE_REVIEW_OTHER}). No value was changed or capped. The team decides what to do with them.", "",
           "Largest 10 values per FTE column (combokey in brackets):", ""]
    top = []
    for name in FTE_COLS.values():
        t = out[["combokey", name]].dropna().nlargest(10, name)
        top.append([name, ", ".join(f"{v:g} ({k})" for k, v in zip(t["combokey"], t[name]))])
    L += _md_table(pd.DataFrame(top, columns=["Column", "Largest 10 values (combokey)"])) + [""]

    L += ["## Unresolved issues and notes", "",
          "- Restraint columns (MECH and PHYS) and student counts (TOT_RS_*) are not read. The EDA found restraint leaks the outcome.",
          "- flag_small_enrollment uses under 10 students. flag_missing_enrollment is True when enrollment_total is NA or not above 0. flag_analysis_ready is True when the seclusion total is valid and enrollment_total is above 0.",
          "- pct_idea, pct_504 and pct_el are on a 0-100 scale and NA when the subgroup is larger than enrollment_total.",
          "- support_fte_per_100 = nurses + psychologists + social workers; counselors are not included.",
          "- sch_virt_ind: the PR review asked for it to come from flag_covid_virtual_only, but the playbook says to leave it NA and not substitute COVID instruction mode. "
          f"This run used {'the COVID instruction type (Yes only for type B)' if SCH_VIRT_FROM_COVID else 'NA'}. The team needs to decide; set SCH_VIRT_FROM_COVID in the script to change it.",
          "- The mapping file marks manual references as unverified: they were not re-checked against the 2020-21 manual. Whether total enrollment includes preschool is not stated.",
          "- Distance Education and High School Equivalency are LEA-level files outside the shared columns and are not joined.",
          "- 2020-21 seclusion data is incomplete (see above). Use this year for sensitivity checks; the main modeling year is 2021-22.", ""]
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
    write_mapping(args.docs_dir / "mapping_202021.csv")
    write_qa(result, report, args.docs_dir / "qa_202021.md", args.raw_dir)


if __name__ == "__main__":
    main()
