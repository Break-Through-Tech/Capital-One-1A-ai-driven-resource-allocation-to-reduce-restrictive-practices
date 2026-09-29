#!/usr/bin/env python3
"""Clean CRDC school files into analysis-ready tables (Task 3).

Reads local public-use CSVs under lia/data/, applies the Task 2 audit rules,
and writes processed tables under lia/data/processed/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT.parent / "lia" / "data"
OUT = RAW / "processed"

YES_NO_COLS = [
    "jj",
    "sch_status_sped",
    "sch_status_magnet",
    "sch_status_charter",
    "sch_status_alt",
    "sch_virt_ind",
    "sch_just_ind",
]

# FTE values above these are treated as reporting errors (audit: 102k guards, 19k psych).
FTE_OUTLIER_CAPS = {
    "fte_teachers": 2000,
    "fte_counselors": 200,
    "fte_nurses": 200,
    "fte_psych": 200,
    "fte_social": 200,
    "fte_leo": 200,
    "fte_guards": 200,
}

SMALL_ENROLLMENT = 10


def read_csv(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    kwargs: dict = {
        "dtype": str,
        "low_memory": False,
        "keep_default_na": False,
        "na_values": ["", "NA", "NULL", "null", "None"],
    }
    header = None
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            header = pd.read_csv(path, encoding=enc, nrows=0).columns.tolist()
            if usecols is not None:
                kwargs["usecols"] = [c for c in usecols if c in header]
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError as err:
            last_err = err
            kwargs.pop("usecols", None)
    raise last_err or RuntimeError(f"Could not read {path}")


def pad_id(series: pd.Series, width: int) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace(r"\.0$", "", regex=True)
    sci = s.str.contains(r"[Ee][+\-]", regex=True, na=False)
    s = s.mask(sci, pd.NA)
    empty = s.isin(["", "nan", "None", "<NA>"])
    s = s.mask(empty, pd.NA)
    return s.str.zfill(width)


def standardize_ids(df: pd.DataFrame, *, rebuild_combokey: bool, drop_schid: bool) -> pd.DataFrame:
    out = df.copy()
    if "LEAID" in out.columns:
        out["LEAID"] = pad_id(out["LEAID"], 7)
    if drop_schid and "SCHID" in out.columns:
        out = out.drop(columns=["SCHID"])
    elif "SCHID" in out.columns:
        out["SCHID"] = pad_id(out["SCHID"], 5)
    if rebuild_combokey and {"LEAID", "SCHID"}.issubset(out.columns):
        out["COMBOKEY"] = out["LEAID"] + out["SCHID"]
    elif "COMBOKEY" in out.columns:
        out["COMBOKEY"] = pad_id(out["COMBOKEY"], 12)
        if {"LEAID", "SCHID"}.issubset(out.columns):
            rebuilt = out["LEAID"] + out["SCHID"]
            mismatch = out["COMBOKEY"].notna() & rebuilt.notna() & (out["COMBOKEY"] != rebuilt)
            # Prefer rebuilt when stored COMBOKEY is corrupted (2015-16).
            out.loc[mismatch, "COMBOKEY"] = rebuilt[mismatch]
    return out.dropna(subset=["COMBOKEY"]) if "COMBOKEY" in out.columns else out


def to_numeric_reserved_as_na(series: pd.Series) -> pd.Series:
    """Mask reserved codes in counts/FTEs, preserving reported zeros.

    Source: Table 2 in the bundled public-use manuals (2015-16 p. 18;
    2017-18 p. 12); see docs/data_dictionary.md for source links.
    Both years: -9 Not Applicable / Skipped, -5 Action Plan,
    -6 Force Certified, -8 EDFacts Missing Data.
    2015-16 additionally: -2 Small Cell Value, -7 System Error.
    2017-18 additionally: -3 Skip Logic Failure, -11 Suppressed Data.
    Mask all negatives so later-year codes also cannot enter arithmetic;
    their meanings must be checked against their own year's manual.
    """
    num = pd.to_numeric(series, errors="coerce")
    return num.mask(num < 0)


def yes_no(series: pd.Series) -> pd.Series:
    """Normalize flags; all reserved codes and other non-Yes/No values are NA."""
    s = series.astype(str).str.strip().str.lower()
    return s.map({"yes": "Yes", "no": "No", "y": "Yes", "n": "No"})


def first_present(df: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series(pd.NA, index=df.index)


def add_pair(df: pd.DataFrame, a: str, b: str, extra: str | None = None) -> pd.Series:
    total = to_numeric_reserved_as_na(first_present(df, [a])) + to_numeric_reserved_as_na(
        first_present(df, [b])
    )
    if extra and extra in df.columns:
        x = to_numeric_reserved_as_na(df[extra])
        total = total + x.fillna(0)
    return total


YEAR_PATHS = {
    "2021-22": {
        "rebuild_combokey": False,
        "drop_restraint_schid": False,
        "char": RAW / "2021-22-crdc-data/SCH/School Characteristics.csv",
        "enroll": RAW / "2021-22-crdc-data/SCH/Enrollment.csv",
        "restraint": RAW / "2021-22-crdc-data/SCH/Restraint and Seclusion.csv",
        "support": RAW / "2021-22-crdc-data/SCH/School Support.csv",
        "lea": RAW / "2021-22-crdc-data/LEA/LEA Characteristics.csv",
        "covid": RAW / "2021-22-crdc-data/SCH/COVID Directional Indicators.csv",
        "wide": None,
    },
    "2020-21": {
        "rebuild_combokey": False,
        "drop_restraint_schid": False,
        "char": RAW / "2020-21-crdc-data/CRDC/School/School Characteristics.csv",
        "enroll": RAW / "2020-21-crdc-data/CRDC/School/Enrollment.csv",
        "restraint": RAW / "2020-21-crdc-data/CRDC/School/Restraint and Seclusion.csv",
        "support": RAW / "2020-21-crdc-data/CRDC/School/School Support.csv",
        "lea": RAW / "2020-21-crdc-data/CRDC/LEA/LEA Characteristics.csv",
        "covid": RAW / "2020-21-crdc-data/CRDC/School/COVID Directional Indicators.csv",
        "wide": None,
    },
    "2017-18": {
        "rebuild_combokey": False,
        "drop_restraint_schid": True,
        "char": RAW
        / "2017-18-crdc-data-corrected-publication 2/2017-18 Public-Use Files/Data/SCH/CRDC/CSV/School Characteristics.csv",
        "enroll": RAW
        / "2017-18-crdc-data-corrected-publication 2/2017-18 Public-Use Files/Data/SCH/CRDC/CSV/Enrollment.csv",
        "restraint": RAW
        / "2017-18-crdc-data-corrected-publication 2/2017-18 Public-Use Files/Data/SCH/CRDC/CSV/Restraint and Seclusion.csv",
        "support": RAW
        / "2017-18-crdc-data-corrected-publication 2/2017-18 Public-Use Files/Data/SCH/CRDC/CSV/School Support.csv",
        "lea": RAW
        / "2017-18-crdc-data-corrected-publication 2/2017-18 Public-Use Files/Data/LEA/CRDC/CSV/LEA Characteristics.csv",
        "covid": None,
        "wide": None,
    },
    "2015-16": {
        "rebuild_combokey": True,
        "drop_restraint_schid": False,
        "char": None,
        "enroll": None,
        "restraint": None,
        "support": None,
        "lea": RAW / "2015-16-crdc-data/Data Files and Layouts/CRDC 2015-16 LEA Data.csv",
        "covid": None,
        "wide": RAW / "2015-16-crdc-data/Data Files and Layouts/CRDC 2015-16 School Data.csv",
    },
}

CHAR_COLS = [
    "LEA_STATE",
    "LEA_STATE_NAME",
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
    "SCH_VIRT_IND",
    "SCH_JUST_IND",
    "SCH_GRADE_PS",
    "SCH_GRADE_KG",
    "SCH_GRADE_G01",
    "SCH_GRADE_G06",
    "SCH_GRADE_G09",
    "SCH_GRADE_G12",
]
ENROLL_COLS = [
    "COMBOKEY",
    "TOT_ENR_M",
    "TOT_ENR_F",
    "TOT_ENR_X",
    "SCH_ENR_IDEA_M",
    "SCH_ENR_IDEA_F",
    "SCH_ENR_IDEA_X",
    "SCH_ENR_504_M",
    "SCH_ENR_504_F",
    "SCH_ENR_504_X",
    "SCH_ENR_EL_M",
    "SCH_ENR_EL_F",
    "SCH_ENR_EL_X",
    "SCH_ENR_LEP_M",
    "SCH_ENR_LEP_F",
]
RESTRAINT_COLS = [
    "COMBOKEY",
    "LEAID",
    "SCHID",
    "SCH_RSINSTANCES_SECL_WODIS",
    "SCH_RSINSTANCES_SECL_IDEA",
    "SCH_RSINSTANCES_SECL_504",
    "TOT_RS_NONIDEA_SECL_M",
    "TOT_RS_NONIDEA_SECL_F",
    "TOT_RS_IDEA_SECL_M",
    "TOT_RS_IDEA_SECL_F",
]
SUPPORT_COLS = [
    "COMBOKEY",
    "SCH_FTETEACH_TOT",
    "SCH_FTETEACH_CERT",
    "SCH_FTECOUNSELORS",
    "SCH_FTESERVICES_NUR",
    "SCH_FTESERVICES_PSY",
    "SCH_FTESERVICES_SOC",
    "SCH_FTESECURITY_LEO",
    "SCH_FTESECURITY_GUA",
]
LEA_COLS = ["LEAID", "LEA_ENR", "LEA_SCHOOLS"]
COVID_COLS = [
    "COMBOKEY",
    "SCH_DIND_INSTRUCTIONTYPE",
    "SCH_DIND_VIRTUALTYPE",
    "SCH_DIND_REMOTETYPE",
    "SCH_DIND_REMOTEAMOUNT",
    "SCH_DIND_REMOTEPERCT",
]
WIDE_COLS = list(
    dict.fromkeys(
        CHAR_COLS
        + [c for c in ENROLL_COLS if c != "COMBOKEY"]
        + [c for c in RESTRAINT_COLS if c not in {"COMBOKEY", "LEAID", "SCHID"}]
        + [c for c in SUPPORT_COLS if c != "COMBOKEY"]
    )
)


def load_year(year: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = YEAR_PATHS[year]
    if cfg["wide"] is not None:
        school = read_csv(cfg["wide"], WIDE_COLS)
        school = standardize_ids(school, rebuild_combokey=True, drop_schid=False)
        lea = standardize_ids(read_csv(cfg["lea"], LEA_COLS), rebuild_combokey=False, drop_schid=False)
        return school, lea

    char = standardize_ids(
        read_csv(cfg["char"], CHAR_COLS),
        rebuild_combokey=False,
        drop_schid=False,
    )
    enroll = standardize_ids(
        read_csv(cfg["enroll"], ENROLL_COLS),
        rebuild_combokey=False,
        drop_schid=False,
    )
    restraint = standardize_ids(
        read_csv(cfg["restraint"], RESTRAINT_COLS),
        rebuild_combokey=False,
        drop_schid=cfg["drop_restraint_schid"],
    )
    support = standardize_ids(
        read_csv(cfg["support"], SUPPORT_COLS),
        rebuild_combokey=False,
        drop_schid=False,
    )
    lea = standardize_ids(read_csv(cfg["lea"], LEA_COLS), rebuild_combokey=False, drop_schid=False)

    school = char.merge(enroll, on="COMBOKEY", how="inner", suffixes=("", "_enr"))
    school = school.merge(restraint, on="COMBOKEY", how="inner", suffixes=("", "_rs"))
    school = school.merge(support, on="COMBOKEY", how="inner", suffixes=("", "_sup"))
    if cfg["covid"] is not None and cfg["covid"].exists():
        covid = standardize_ids(
            read_csv(cfg["covid"], COVID_COLS),
            rebuild_combokey=False,
            drop_schid=False,
        )
        school = school.merge(covid, on="COMBOKEY", how="left", suffixes=("", "_covid"))
    return school, lea


def build_analysis_table(year: str, school: pd.DataFrame, lea: pd.DataFrame) -> pd.DataFrame:
    df = school.copy()
    df["year"] = year

    df["jj"] = yes_no(first_present(df, ["JJ"]))
    df["sch_status_sped"] = yes_no(first_present(df, ["SCH_STATUS_SPED"]))
    df["sch_status_magnet"] = yes_no(first_present(df, ["SCH_STATUS_MAGNET"]))
    df["sch_status_charter"] = yes_no(first_present(df, ["SCH_STATUS_CHARTER"]))
    df["sch_status_alt"] = yes_no(first_present(df, ["SCH_STATUS_ALT"]))
    df["sch_virt_ind"] = yes_no(first_present(df, ["SCH_VIRT_IND"]))
    df["sch_just_ind"] = yes_no(first_present(df, ["SCH_JUST_IND", "JJ"]))

    df["enr_male"] = to_numeric_reserved_as_na(first_present(df, ["TOT_ENR_M"]))
    df["enr_female"] = to_numeric_reserved_as_na(first_present(df, ["TOT_ENR_F"]))
    df["enr_nonbinary"] = to_numeric_reserved_as_na(first_present(df, ["TOT_ENR_X"]))
    df["enrollment_total"] = df["enr_male"] + df["enr_female"] + df["enr_nonbinary"].fillna(0)

    df["enr_idea"] = add_pair(df, "SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F", "SCH_ENR_IDEA_X")
    df["enr_504"] = add_pair(df, "SCH_ENR_504_M", "SCH_ENR_504_F", "SCH_ENR_504_X")
    if any(c in df.columns for c in ["SCH_ENR_EL_M", "SCH_ENR_EL_F"]):
        df["enr_el"] = add_pair(df, "SCH_ENR_EL_M", "SCH_ENR_EL_F", "SCH_ENR_EL_X")
    else:
        df["enr_el"] = add_pair(df, "SCH_ENR_LEP_M", "SCH_ENR_LEP_F")

    df["seclusion_instances_wodis"] = to_numeric_reserved_as_na(
        first_present(df, ["SCH_RSINSTANCES_SECL_WODIS"])
    )
    df["seclusion_instances_idea"] = to_numeric_reserved_as_na(
        first_present(df, ["SCH_RSINSTANCES_SECL_IDEA"])
    )
    df["seclusion_instances_504"] = to_numeric_reserved_as_na(
        first_present(df, ["SCH_RSINSTANCES_SECL_504"])
    )
    df["seclusion_instances"] = (
        df["seclusion_instances_wodis"]
        + df["seclusion_instances_idea"]
        + df["seclusion_instances_504"]
    )
    df["students_seclusion_nonidea"] = add_pair(
        df, "TOT_RS_NONIDEA_SECL_M", "TOT_RS_NONIDEA_SECL_F"
    )
    df["students_seclusion_idea"] = add_pair(df, "TOT_RS_IDEA_SECL_M", "TOT_RS_IDEA_SECL_F")

    df["fte_teachers"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTETEACH_TOT"]))
    df["fte_teachers_cert"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTETEACH_CERT"]))
    df["fte_counselors"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTECOUNSELORS"]))
    df["fte_nurses"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTESERVICES_NUR"]))
    df["fte_psych"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTESERVICES_PSY"]))
    df["fte_social"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTESERVICES_SOC"]))
    df["fte_leo"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTESECURITY_LEO"]))
    df["fte_guards"] = to_numeric_reserved_as_na(first_present(df, ["SCH_FTESECURITY_GUA"]))

    outlier = pd.Series(False, index=df.index)
    for col, cap in FTE_OUTLIER_CAPS.items():
        too_high = df[col] > cap
        outlier = outlier | too_high.fillna(False)
        df.loc[too_high, col] = pd.NA
    df["flag_fte_outlier"] = outlier

    df["seclusion_rate_per_100"] = pd.NA
    valid_rate = df["seclusion_instances"].notna() & df["enrollment_total"].gt(0)
    df.loc[valid_rate, "seclusion_rate_per_100"] = (
        100 * df.loc[valid_rate, "seclusion_instances"] / df.loc[valid_rate, "enrollment_total"]
    )

    df["counselors_per_100"] = pd.NA
    df["support_fte_per_100"] = pd.NA
    df["teachers_per_100"] = pd.NA
    has_enr = df["enrollment_total"].gt(0)
    c_mask = has_enr & df["fte_counselors"].notna()
    df.loc[c_mask, "counselors_per_100"] = (
        100 * df.loc[c_mask, "fte_counselors"] / df.loc[c_mask, "enrollment_total"]
    )
    t_mask = has_enr & df["fte_teachers"].notna()
    df.loc[t_mask, "teachers_per_100"] = (
        100 * df.loc[t_mask, "fte_teachers"] / df.loc[t_mask, "enrollment_total"]
    )
    support = df["fte_nurses"].fillna(0) + df["fte_psych"].fillna(0) + df["fte_social"].fillna(0)
    s_mask = has_enr & (
        df["fte_nurses"].notna() | df["fte_psych"].notna() | df["fte_social"].notna()
    )
    df.loc[s_mask, "support_fte_per_100"] = (
        100 * support.loc[s_mask] / df.loc[s_mask, "enrollment_total"]
    )

    lea_keep = lea[["LEAID", "LEA_ENR", "LEA_SCHOOLS"]].copy()
    lea_keep["lea_enrollment"] = to_numeric_reserved_as_na(lea_keep["LEA_ENR"])
    lea_keep["lea_schools"] = to_numeric_reserved_as_na(lea_keep["LEA_SCHOOLS"])
    df = df.merge(lea_keep[["LEAID", "lea_enrollment", "lea_schools"]], on="LEAID", how="left")

    df["flag_missing_seclusion"] = df["seclusion_instances"].isna()
    df["flag_missing_enrollment"] = df["enrollment_total"].isna() | df["enr_male"].isna() | df[
        "enr_female"
    ].isna()
    df["flag_small_enrollment"] = df["enrollment_total"].fillna(0).lt(SMALL_ENROLLMENT)
    df["flag_zero_enrollment"] = df["enrollment_total"].eq(0)
    df["flag_analysis_ready"] = (
        ~df["flag_missing_seclusion"]
        & ~df["flag_missing_enrollment"]
        & df["enrollment_total"].gt(0)
    )

    if "SCH_DIND_INSTRUCTIONTYPE" in df.columns:
        df["covid_instruction_type"] = df["SCH_DIND_INSTRUCTIONTYPE"]
    else:
        df["covid_instruction_type"] = pd.NA
    if "SCH_DIND_VIRTUALTYPE" in df.columns:
        df["covid_virtual_type"] = df["SCH_DIND_VIRTUALTYPE"]
    elif "SCH_DIND_REMOTETYPE" in df.columns:
        df["covid_virtual_type"] = df["SCH_DIND_REMOTETYPE"]
    else:
        df["covid_virtual_type"] = pd.NA

    keep = [
        "year",
        "COMBOKEY",
        "LEAID",
        "SCHID",
        "LEA_STATE",
        "LEA_STATE_NAME",
        "SCH_NAME",
        "LEA_NAME",
        "jj",
        "sch_just_ind",
        "sch_virt_ind",
        "sch_status_sped",
        "sch_status_magnet",
        "sch_status_charter",
        "sch_status_alt",
        "enr_male",
        "enr_female",
        "enr_nonbinary",
        "enrollment_total",
        "enr_idea",
        "enr_504",
        "enr_el",
        "seclusion_instances_wodis",
        "seclusion_instances_idea",
        "seclusion_instances_504",
        "seclusion_instances",
        "seclusion_rate_per_100",
        "students_seclusion_nonidea",
        "students_seclusion_idea",
        "fte_teachers",
        "fte_teachers_cert",
        "fte_counselors",
        "fte_nurses",
        "fte_psych",
        "fte_social",
        "fte_leo",
        "fte_guards",
        "teachers_per_100",
        "counselors_per_100",
        "support_fte_per_100",
        "lea_enrollment",
        "lea_schools",
        "covid_instruction_type",
        "covid_virtual_type",
        "flag_missing_seclusion",
        "flag_missing_enrollment",
        "flag_small_enrollment",
        "flag_zero_enrollment",
        "flag_fte_outlier",
        "flag_analysis_ready",
    ]
    out = df[keep].copy()
    out = out.rename(
        columns={
            "COMBOKEY": "combokey",
            "LEAID": "leaid",
            "SCHID": "schid",
            "LEA_STATE": "lea_state",
            "LEA_STATE_NAME": "lea_state_name",
            "SCH_NAME": "sch_name",
            "LEA_NAME": "lea_name",
        }
    )
    out = out.sort_values(["lea_state", "leaid", "combokey"]).reset_index(drop=True)
    return out


def validate(year: str, raw_n: int, out: pd.DataFrame) -> dict:
    dups = int(out["combokey"].duplicated().sum())
    return {
        "year": year,
        "rows_in": raw_n,
        "rows_out": int(len(out)),
        "unique_combokey": int(out["combokey"].nunique()),
        "duplicate_combokey": dups,
        "unique_leaid": int(out["leaid"].nunique()),
        "n_analysis_ready": int(out["flag_analysis_ready"].sum()),
        "n_missing_seclusion": int(out["flag_missing_seclusion"].sum()),
        "n_missing_enrollment": int(out["flag_missing_enrollment"].sum()),
        "n_small_enrollment": int(out["flag_small_enrollment"].sum()),
        "n_fte_outlier": int(out["flag_fte_outlier"].sum()),
        "n_positive_seclusion": int((out["seclusion_instances"] > 0).sum()),
        "seclusion_rate_p50": None
        if out.loc[out["flag_analysis_ready"], "seclusion_rate_per_100"].empty
        else float(out.loc[out["flag_analysis_ready"], "seclusion_rate_per_100"].median()),
        "id_lengths_ok": bool(
            out["combokey"].str.len().eq(12).all()
            and out["leaid"].str.len().eq(7).all()
            and out["schid"].str.len().eq(5).all()
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    frames = []
    for year in ("2021-22", "2020-21", "2017-18", "2015-16"):
        print(f"Cleaning {year}...", flush=True)
        school, lea = load_year(year)
        raw_n = len(school)
        out = build_analysis_table(year, school, lea)
        summary = validate(year, raw_n, out)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
        if summary["duplicate_combokey"] != 0:
            raise SystemExit(f"Duplicate combokey after cleaning {year}")
        if not summary["id_lengths_ok"]:
            raise SystemExit(f"ID padding failed for {year}")

        year_slug = year.replace("-", "")
        full_path = OUT / f"schools_{year_slug}.csv"
        ready_path = OUT / f"schools_{year_slug}_analysis.csv"
        out.to_csv(full_path, index=False)
        out.loc[out["flag_analysis_ready"]].to_csv(ready_path, index=False)
        frames.append(out)

    stacked = pd.concat(frames, ignore_index=True)
    stacked.to_csv(OUT / "schools_all_years.csv", index=False)
    (OUT / "cleaning_validation.json").write_text(json.dumps(summaries, indent=2))
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
