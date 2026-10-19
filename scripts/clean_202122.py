#!/usr/bin/env python
"""Clean the 2021-22 CRDC school and district data.

This script follows docs/cleaning_feature_playbook.md. Run it from the repository root:

    python scripts/clean_202122.py --raw-dir data/raw/2021-22 --out-dir data/processed/202122

Each step is a small function, so teammates can copy the file for another year and change
the constants. The file reads top to bottom:

    Part A: cleaning (stop reading here to understand what happens to the data)
        Constants, errors and small helpers
        Quality log (quality_detail_<year>.csv)
        Steps 1 to 4: reading, IDs, numbers, categories
        Steps 5 and 6: joins
        Steps 7 to 10: features
        Step 11: output files and validation
    Part B: documentation outputs
        Mapping file (docs/cleaning/mapping_<year>.csv)
        QA report (docs/cleaning/qa_<year>.md)
    Runner: pipeline, run() and the command line
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import platform
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("clean_202122")

# ===========================================================================
# Part A: cleaning
# ===========================================================================

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
YEAR_LABEL = "2021-22"
YEAR_CODE = "202122"
PACKAGE_NAME = "2021-22-crdc-data"
MANUAL_FILE = "2021-22 User's Manual.pdf"
APPENDIX_FILE = "2021-22 Appendix Workbook.xlsx"

DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "2021-22"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "processed" / YEAR_CODE
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "cleaning"

# The playbook allows utf-8-sig and cp1252. latin-1 is only used after a manual check.
ENCODINGS = ("utf-8-sig", "cp1252")

LEAID_WIDTH = 7
SCHID_WIDTH = 5
COMBOKEY_WIDTH = LEAID_WIDTH + SCHID_WIDTH
ID_PLACEHOLDERS = frozenset({"NAN", "NONE", "NULL", "NA", "N/A"})

# User's Manual section 5.4, Table 1. The playbook also lists -2 and -11 from the audit, but
# the 2021-22 manual does not define them, so any such value is logged as unexpected_negative.
RESERVED_CODES: dict[int, str] = {
    -3: "Skip logic or processing failure",
    -4: "Missing optional data",
    -5: "Action plan or quick plan",
    -6: "Force certified",
    -9: "Not applicable or skipped",
    -12: "Suppressed for privacy protection",
    -13: "Missing skip logic flag",
}
RESERVED_MEANING = {
    float(code): f"User's Manual 5.4 Table 1: {meaning}" for code, meaning in RESERVED_CODES.items()
}
NUMERIC_ISSUE_EVIDENCE = {
    "blank_value": "Value was blank in the source file",
    "parse_failure": "Value is not a number",
    "non_finite": "Infinite values are treated as missing (playbook step 3)",
    "unexpected_negative": "Negative value is not a reserve code in the 2021-22 manual",
    "fractional_count": "Counts must be whole numbers (playbook step 3)",
}

SMALL_ENROLLMENT = 10
TEACHER_FTE_REVIEW = 2000
OTHER_FTE_REVIEW = 200
TOP_N_FTE = 10
FTE_TOP_ISSUE = f"fte_review_top{TOP_N_FTE}"

# Hand-checked comparison figures from docs/data_audit.md. They are never used to change results.
AUDIT_ROSTER_SCHOOLS = 98_010
AUDIT_RESERVED_INSTANCE_SCHOOLS = 4_905

GRADE_COLUMNS = ["SCH_GRADE_KG"] + [f"SCH_GRADE_G{number:02d}" for number in range(1, 13)]
ELEMENTARY_GRADES = GRADE_COLUMNS[:6]  # KG to grade 5
MIDDLE_GRADES = GRADE_COLUMNS[6:9]  # grades 6 to 8
HIGH_GRADES = GRADE_COLUMNS[9:]  # grades 9 to 12

CATEGORY_COLUMNS = {
    "jj": "JJ",
    "sch_virt_ind": "SCH_VIRT_IND",
    "sch_status_sped": "SCH_STATUS_SPED",
    "sch_status_charter": "SCH_STATUS_CHARTER",
    "sch_status_alt": "SCH_STATUS_ALT",
    "sch_status_magnet": "SCH_STATUS_MAGNET",
}
JUSTICE_COLUMN = "SCH_JUST_IND"

# Output column -> raw (male, female, nonbinary) columns.
ENROLLMENT_PARTS = {
    "enrollment_total": ("TOT_ENR_M", "TOT_ENR_F", "TOT_ENR_X"),
    "enr_idea": ("SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F", "SCH_ENR_IDEA_X"),
    "enr_504": ("SCH_ENR_504_M", "SCH_ENR_504_F", "SCH_ENR_504_X"),
    "enr_el": ("SCH_ENR_EL_M", "SCH_ENR_EL_F", "SCH_ENR_EL_X"),
}
PARTIAL_FLAGS = {
    "enrollment_total": "flag_partial_enrollment",
    "enr_idea": "flag_partial_idea",
    "enr_504": "flag_partial_504",
    "enr_el": "flag_partial_el",
}
PERCENT_COLUMNS = {"enr_idea": "pct_idea", "enr_504": "pct_504", "enr_el": "pct_el"}

SECLUSION_COLUMNS = {
    "seclusion_instances_wodis": "SCH_RSINSTANCES_SECL_WODIS",
    "seclusion_instances_idea": "SCH_RSINSTANCES_SECL_IDEA",
    "seclusion_instances_504": "SCH_RSINSTANCES_SECL_504",
}
FTE_COLUMNS = {
    "fte_teachers": "SCH_FTETEACH_TOT",
    "fte_counselors": "SCH_FTECOUNSELORS",
    "fte_nurses": "SCH_FTESERVICES_NUR",
    "fte_psych": "SCH_FTESERVICES_PSY",
    "fte_social": "SCH_FTESERVICES_SOC",
    "fte_leo": "SCH_FTESECURITY_LEO",
    "fte_guards": "SCH_FTESECURITY_GUA",
}
# Appendix Sheet B question for each raw column above (used only by the mapping file).
SECLUSION_QUESTIONS = {
    "SCH_RSINSTANCES_SECL_WODIS": "RSTR-1.7",
    "SCH_RSINSTANCES_SECL_IDEA": "RSTR-1.8",
    "SCH_RSINSTANCES_SECL_504": "RSTR-1.9",
}
FTE_QUESTIONS = {
    "SCH_FTETEACH_TOT": "STAF-1.1",
    "SCH_FTECOUNSELORS": "STAF-6",
    "SCH_FTESERVICES_NUR": "STAF-7.1",
    "SCH_FTESERVICES_PSY": "STAF-7.2",
    "SCH_FTESERVICES_SOC": "STAF-7.3",
    "SCH_FTESECURITY_LEO": "SECR-1.1",
    "SCH_FTESECURITY_GUA": "SECR-1.2",
}
# Kindergarten is SCHR-3.2 (3.1 is preschool, which grade_band leaves out).
FIRST_GRADE_QUESTION = 2
# First Appendix Sheet B number (ENRL-1.<n>) of each M, F, X triple.
ENROLLMENT_QUESTION_START = {"enr_el": 22, "enr_idea": 25, "enr_504": 28}
ENROLLMENT_GROUP_LABELS = {"enr_el": "EL", "enr_idea": "IDEA", "enr_504": "Section 504 only"}
SUPPORT_FTE_COLUMNS = ["fte_nurses", "fte_psych", "fte_social"]
LEA_COUNT_COLUMNS = {"lea_enrollment": "LEA_ENR", "lea_schools": "LEA_SCHOOLS"}

# Section 3.1 of the playbook: exact column order of the shared output.
OUTPUT_COLUMNS = [
    "year",
    "combokey",
    "leaid",
    "schid",
    "lea_state",
    "sch_name",
    "lea_name",
    "jj",
    "seclusion_instances_wodis",
    "seclusion_instances_idea",
    "seclusion_instances_504",
    "seclusion_instances",
    "enrollment_total",
    "enr_nonbinary",
    "enr_idea",
    "enr_504",
    "enr_el",
    "seclusion_rate",
    "sch_status_sped",
    "sch_status_charter",
    "sch_status_alt",
    "sch_status_magnet",
    "sch_virt_ind",
    "grade_band",
    "fte_teachers",
    "fte_counselors",
    "fte_nurses",
    "fte_psych",
    "fte_social",
    "fte_leo",
    "fte_guards",
    "counselors_per_100",
    "teachers_per_100",
    "support_fte_per_100",
    "pct_idea",
    "pct_504",
    "pct_el",
    "lea_enrollment",
    "lea_schools",
    "flag_missing_seclusion",
    "flag_missing_enrollment",
    "flag_small_enrollment",
    "flag_fte_outlier",
    "flag_partial_enrollment",
    "flag_partial_idea",
    "flag_partial_504",
    "flag_partial_el",
    "flag_missing_module",
    "flag_missing_lea",
    "flag_analysis_ready",
]
STRING_COLUMNS = [
    "year",
    "combokey",
    "leaid",
    "schid",
    "lea_state",
    "sch_name",
    "lea_name",
    "jj",
    "sch_status_sped",
    "sch_status_charter",
    "sch_status_alt",
    "sch_status_magnet",
    "sch_virt_ind",
    "grade_band",
]
BOOLEAN_COLUMNS = [name for name in OUTPUT_COLUMNS if name.startswith("flag_")]
FLOAT_COLUMNS = [
    name for name in OUTPUT_COLUMNS if name not in STRING_COLUMNS and name not in BOOLEAN_COLUMNS
]
NONNEGATIVE_COLUMNS = [
    *SECLUSION_COLUMNS,
    "seclusion_instances",
    "enrollment_total",
    "enr_nonbinary",
    "enr_idea",
    "enr_504",
    "enr_el",
    *FTE_COLUMNS,
    "lea_enrollment",
    "lea_schools",
]
RATE_COLUMNS = [
    "seclusion_rate",
    "counselors_per_100",
    "teachers_per_100",
    "support_fte_per_100",
    "pct_idea",
    "pct_504",
    "pct_el",
]

QUALITY_COLUMNS = [
    "year",
    "source_file",
    "source_row",
    "combokey",
    "leaid",
    "raw_column",
    "raw_value",
    "issue",
    "action",
    "cleaned_value",
    "evidence",
]

# Mapping file (Part B).
MAPPING_COLUMNS = [
    "source_file",
    "source_column",
    "shared_output_column",
    "transformation",
    "units_population_period",
    "manual_reference",
    "verification_status",
]
VERIFIED = "verified"
UNRESOLVED = "unresolved"
PERIOD = f"{YEAR_LABEL} school year"
MANUAL_IDS = "User's Manual 5.5.3 Table 3"
NOT_DEFINED = "Descriptive field. Not defined in the manual or Appendix Sheet B"

ID_ERROR_ISSUES = frozenset(
    {
        "blank_id",
        "invalid_id_characters",
        "id_too_long",
        "bad_id_length",
        "component_mismatch",
        "duplicate_id",
    }
)
ID_ISSUE_EVIDENCE = {
    "blank_id": "Playbook step 2: IDs must not be blank",
    "invalid_id_characters": "Playbook step 2: only digits or uppercase letters are allowed",
    "id_too_long": "Playbook step 2: ID is longer than its fixed width",
    "bad_id_length": "Playbook step 2: non-digit ID does not have its fixed width",
    "padded_id": "Playbook step 2: digit-only ID padded with leading zeros",
    "non_digit_id": "User's Manual 5.5.3: CRDC-issued ID kept as reported, needs team decision",
    "component_mismatch": "Playbook step 2: LEAID plus SCHID must equal COMBOKEY",
    "duplicate_id": "Playbook step 2: IDs must be unique within a module",
}


@dataclass(frozen=True)
class ModuleSpec:
    """One input file and the raw columns the cleaning needs from it."""

    key: str
    relative_path: str
    columns: tuple[str, ...]
    has_school_ids: bool = True

    @property
    def file_name(self) -> str:
        """The file name without its folder, as written in logs and reports."""
        return Path(self.relative_path).name


_SCHOOL_IDS = ("LEAID", "SCHID", "COMBOKEY")

MODULES = {
    "char": ModuleSpec(
        "char",
        "SCH/School Characteristics.csv",
        (
            "LEA_STATE",
            *_SCHOOL_IDS,
            "LEA_NAME",
            "SCH_NAME",
            *CATEGORY_COLUMNS.values(),
            JUSTICE_COLUMN,
            *GRADE_COLUMNS,
        ),
    ),
    "enrollment": ModuleSpec(
        "enrollment",
        "SCH/Enrollment.csv",
        (*_SCHOOL_IDS, *[c for parts in ENROLLMENT_PARTS.values() for c in parts]),
    ),
    "restraint": ModuleSpec(
        "restraint",
        "SCH/Restraint and Seclusion.csv",
        (*_SCHOOL_IDS, *SECLUSION_COLUMNS.values()),
    ),
    "support": ModuleSpec(
        "support",
        "SCH/School Support.csv",
        (*_SCHOOL_IDS, *FTE_COLUMNS.values()),
    ),
    "lea": ModuleSpec(
        "lea",
        "LEA/LEA Characteristics.csv",
        ("LEA_STATE", "LEAID", "LEA_NAME", *LEA_COUNT_COLUMNS.values()),
        has_school_ids=False,
    ),
}
SCHOOL_MODULE_KEYS = ("enrollment", "restraint", "support")


class CleaningError(Exception):
    """Base class for errors that stop the pipeline."""


class MissingFileError(CleaningError):
    """An expected source file is not in the raw data folder."""


class MissingColumnError(CleaningError):
    """An expected raw column is missing from a source file."""


class IdValidationError(CleaningError):
    """Blank, invalid, mismatched or duplicate IDs were found."""


class JoinValidationError(CleaningError):
    """A join changed the roster size or would create ambiguous columns."""


class OutputValidationError(CleaningError):
    """The final tables break a playbook rule."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _truthy(mask: pd.Series) -> pd.Series:
    """Turn a boolean series that may hold NA into a plain bool series."""
    return mask.fillna(False).astype(bool)


def _format_number(values: pd.Series) -> pd.Series:
    """Format numbers for the quality log, for example 1074.0 becomes 1074."""
    floats = values.astype("float64")
    return floats.map(lambda value: "" if np.isnan(value) else f"{value:.15g}").astype(object)


def src_row_col(key: str) -> str:
    """Name of the column that keeps a module's original row number after joins."""
    return f"src_row_{key}"


def make_context(
    frame: pd.DataFrame,
    row_column: str = "source_row",
    *,
    combokey: str | None = "combokey",
    leaid: str | None = "leaid",
) -> pd.DataFrame:
    """Build the identifying columns `QualityLog.add` needs (source_row, combokey, leaid).

    Pass `None` for an ID that does not exist for these rows, for example `combokey=None`
    for district rows. It is logged as missing.
    """
    missing = pd.Series(pd.NA, index=frame.index, dtype="object")
    return pd.DataFrame(
        {
            "source_row": frame[row_column],
            "combokey": missing if combokey is None else frame[combokey],
            "leaid": missing if leaid is None else frame[leaid],
        }
    )


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    """Show a path relative to the repository when possible, so reports are portable."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Quality log (quality_detail_{year}.csv)
# ---------------------------------------------------------------------------


class QualityLog:
    """Collects one long table of every value that was flagged, changed or kept."""

    def __init__(self) -> None:
        self._parts: list[pd.DataFrame] = []
        # Routine corrections that are counted instead of logged row by row.
        self.summaries: list[tuple[str, str, str, int]] = []

    def add_summary(self, source_file: str, column: str, issue: str, rows: int) -> None:
        """Count a routine correction, such as zero-padding, without writing one row each."""
        if rows:
            self.summaries.append((source_file, column, issue, rows))

    def add(
        self,
        *,
        source_file: str,
        context: pd.DataFrame,
        mask: pd.Series,
        raw_column: str,
        raw_value: pd.Series,
        issue: str | pd.Series,
        action: str | pd.Series,
        evidence: str | pd.Series,
        cleaned_value: pd.Series | None = None,
    ) -> None:
        """Log the rows of `context` selected by `mask`.

        `context` needs the columns source_row, combokey and leaid. Series arguments
        must share the index of `context`.
        """
        mask = _truthy(mask)
        if not mask.any():
            return

        def pick(value: str | pd.Series | None) -> object:
            if value is None:
                return pd.NA
            if isinstance(value, pd.Series):
                return value.loc[mask].to_numpy(dtype=object)
            return value

        selected = context.loc[mask]
        self._parts.append(
            pd.DataFrame(
                {
                    "year": YEAR_LABEL,
                    "source_file": source_file,
                    "source_row": selected["source_row"].to_numpy(),
                    "combokey": selected["combokey"].to_numpy(dtype=object),
                    "leaid": selected["leaid"].to_numpy(dtype=object),
                    "raw_column": raw_column,
                    "raw_value": raw_value.loc[mask].to_numpy(dtype=object),
                    "issue": pick(issue),
                    "action": pick(action),
                    "cleaned_value": pick(cleaned_value),
                    "evidence": pick(evidence),
                }
            )
        )

    def to_frame(self) -> pd.DataFrame:
        """All logged rows in one table, sorted so reruns give identical files."""
        if not self._parts:
            return pd.DataFrame(columns=QUALITY_COLUMNS)
        frame = pd.concat(self._parts, ignore_index=True)[QUALITY_COLUMNS]
        frame["source_row"] = frame["source_row"].astype("Int64")
        order = ["source_file", "raw_column", "source_row", "issue"]
        return frame.sort_values(order, kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 1: reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceInfo:
    """Facts about one input file for the QA report."""

    name: str
    relative_path: str
    sha256: str
    encoding: str
    rows_parsed: int
    rows_kept: int


def _read_columns(path: Path, columns: Sequence[str]) -> tuple[pd.DataFrame, str]:
    """Read the named columns as strings, trying each allowed encoding in order."""
    for encoding in ENCODINGS:
        try:
            header = pd.read_csv(path, nrows=0, encoding=encoding)
            missing = [name for name in columns if name not in header.columns]
            if missing:
                raise MissingColumnError(f"{path.name} is missing columns: {missing}")
            frame = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                skip_blank_lines=False,  # keeps source_row equal to the data row number
                encoding=encoding,
                usecols=list(columns),
            )
            return frame[list(columns)], encoding
        except UnicodeDecodeError:
            LOGGER.warning("%s is not valid %s, trying the next encoding", path.name, encoding)
    raise CleaningError(
        f"Could not decode {path.name} with {ENCODINGS}. Inspect the file before using latin-1."
    )


def read_module(
    raw_dir: Path, spec: ModuleSpec, log: QualityLog
) -> tuple[pd.DataFrame, SourceInfo]:
    """Read one module, strip whitespace, turn blanks into NA and drop empty rows.

    A row is dropped only when every column the cleaning reads is empty. Each dropped row
    is written to the quality log with its original row number.
    """
    path = raw_dir / spec.relative_path
    if not path.is_file():
        raise MissingFileError(f"Missing input file: {path}")
    frame, encoding = _read_columns(path, spec.columns)
    rows_parsed = len(frame)
    columns = list(spec.columns)
    frame[columns] = frame[columns].apply(lambda column: column.str.strip())
    frame[columns] = frame[columns].replace("", pd.NA)
    frame.insert(0, "source_row", np.arange(1, rows_parsed + 1))
    empty = frame[columns].isna().all(axis=1)
    log.add(
        source_file=spec.file_name,
        context=make_context(frame, combokey=None, leaid=None),
        mask=empty,
        raw_column="(whole row)",
        raw_value=pd.Series(pd.NA, index=frame.index, dtype="object"),
        issue="empty_row",
        action="dropped",
        evidence="Playbook step 1: rows are dropped only when completely empty",
    )
    frame = frame[~empty].reset_index(drop=True)
    info = SourceInfo(
        name=spec.file_name,
        relative_path=spec.relative_path,
        sha256=sha256_of(path),
        encoding=encoding,
        rows_parsed=rows_parsed,
        rows_kept=len(frame),
    )
    LOGGER.info("Read %s (%s rows, %s)", spec.file_name, f"{rows_parsed:,}", encoding)
    return frame, info


# ---------------------------------------------------------------------------
# Step 2: IDs
# ---------------------------------------------------------------------------


def clean_id_column(raw: pd.Series, width: int) -> tuple[pd.Series, pd.Series]:
    """Validate and pad one ID column without ever going through floats.

    Returns the cleaned IDs and an issue label per row (an empty string means no issue).
    Digit-only IDs shorter than `width` are zero-padded. IDs that mix digits and capital
    letters (CRDC-issued state program IDs) are kept as reported when they have the right
    width. The literal text "nan" and similar placeholders are invalid.
    """
    text = raw.astype("string")
    present = text.notna()
    value = text.fillna("")
    is_placeholder = _truthy(value.str.upper().isin(ID_PLACEHOLDERS))
    valid_chars = _truthy(value.str.fullmatch(r"[0-9A-Z]+")) & ~is_placeholder
    digits_only = _truthy(value.str.fullmatch(r"\d+"))
    length = value.str.len()
    too_short = _truthy(length < width)
    # Order is priority: np.select gives each row the first label whose condition is true.
    checks = [
        ("blank_id", ~present),
        ("invalid_id_characters", ~valid_chars),
        ("id_too_long", _truthy(length > width)),
        ("padded_id", digits_only & too_short),
        ("bad_id_length", ~digits_only & too_short),
        ("non_digit_id", ~digits_only),
    ]
    issue = pd.Series(
        np.select(
            [condition.to_numpy() for _, condition in checks],
            [label for label, _ in checks],
            default="",
        ),
        index=raw.index,
    )
    cleaned = value.where(present, pd.NA)
    padded = issue.eq("padded_id")
    cleaned = cleaned.mask(padded, value.str.zfill(width))
    return cleaned, issue


def clean_module_ids(frame: pd.DataFrame, *, spec: ModuleSpec, log: QualityLog) -> pd.DataFrame:
    """Add cleaned `leaid`, `schid` and `combokey` columns and check them.

    Problems are written to the quality log first. Errors (blank, invalid, mismatched or
    duplicate IDs) then stop the run, because no row may be deleted without a decision.
    """
    frame = frame.copy()
    id_columns = _id_columns(spec)
    context = make_context(
        frame, combokey="COMBOKEY" if spec.has_school_ids else None, leaid="LEAID"
    )
    error_counts: dict[str, int] = {}

    for raw_column, width, new_column in id_columns:
        cleaned, issue = clean_id_column(frame[raw_column], width)
        for label in sorted(set(issue) - {""}):
            mask = issue.eq(label)
            if _is_routine_padding(spec, raw_column, label):
                # Module files store SCHID without leading zeros. Count it, do not log each row.
                log.add_summary(spec.file_name, raw_column, label, int(mask.sum()))
            else:
                error_counts |= _log_id_issue(
                    log, spec, context, frame, mask, raw_column, label, cleaned
                )
        frame[new_column] = cleaned

    error_counts |= _check_keys(frame, spec, context, log)
    error_counts = {key: count for key, count in error_counts.items() if count}
    if error_counts:
        raise IdValidationError(f"{spec.file_name}: {error_counts}")
    return frame.drop(columns=[raw for raw, _, _ in id_columns])


def _id_columns(spec: ModuleSpec) -> list[tuple[str, int, str]]:
    """(raw column, fixed width, cleaned column) for each ID this module carries."""
    columns = [("LEAID", LEAID_WIDTH, "leaid")]
    if spec.has_school_ids:
        columns += [("SCHID", SCHID_WIDTH, "schid"), ("COMBOKEY", COMBOKEY_WIDTH, "combokey")]
    return columns


def _is_routine_padding(spec: ModuleSpec, raw_column: str, issue: str) -> bool:
    """True for SCHID padding in module files, which is expected and only counted."""
    return issue == "padded_id" and raw_column == "SCHID" and spec.key != "char"


def _log_id_issue(
    log: QualityLog,
    spec: ModuleSpec,
    context: pd.DataFrame,
    frame: pd.DataFrame,
    mask: pd.Series,
    column: str,
    issue: str,
    cleaned: pd.Series | None = None,
) -> dict[str, int]:
    """Log one kind of ID problem. Returns {"COLUMN:issue": rows} when it is a stopping error."""
    log.add(
        source_file=spec.file_name,
        context=context,
        mask=mask,
        raw_column=column,
        raw_value=frame[column],
        issue=issue,
        action="padded" if issue == "padded_id" else "kept_as_reported",
        evidence=ID_ISSUE_EVIDENCE[issue],
        cleaned_value=cleaned,
    )
    if issue in ID_ERROR_ISSUES:
        return {f"{column}:{issue}": int(_truthy(mask).sum())}
    return {}


def _check_keys(
    frame: pd.DataFrame, spec: ModuleSpec, context: pd.DataFrame, log: QualityLog
) -> dict[str, int]:
    """Log duplicate keys and LEAID + SCHID != COMBOKEY. Returns the stopping error counts."""
    key_column = "combokey" if spec.has_school_ids else "leaid"
    duplicated = frame[key_column].duplicated(keep=False) & frame[key_column].notna()
    errors = _log_id_issue(
        log, spec, context, frame, duplicated, key_column.upper(), "duplicate_id"
    )
    if spec.has_school_ids:
        both_present = frame[["leaid", "schid", "combokey"]].notna().all(axis=1)
        mismatch = both_present & (frame["leaid"] + frame["schid"] != frame["combokey"])
        errors |= _log_id_issue(
            log, spec, context, frame, mismatch, "COMBOKEY", "component_mismatch"
        )
    return errors


# ---------------------------------------------------------------------------
# Step 3: counts and FTEs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedNumeric:
    """Result of parsing one numeric column."""

    values: pd.Series  # Float64, NA where the raw value was not a valid count or FTE
    issue: pd.Series  # label per row, empty string when the value is fine
    evidence: pd.Series


def parse_numeric(raw: pd.Series, *, whole_number: bool) -> ParsedNumeric:
    """Convert raw strings to valid numbers.

    Reserved codes and other negatives, parse failures, infinite values and (for counts)
    fractions become NA. Zero stays zero. Nothing is filled in.
    """
    number = pd.to_numeric(raw.astype(object), errors="coerce").astype("float64")
    array = number.to_numpy()
    blank = raw.isna().to_numpy()
    finite = np.isfinite(array)
    negative = array < 0
    reserved = number.isin(list(RESERVED_CODES)).to_numpy()
    with np.errstate(invalid="ignore"):
        fractional = whole_number & finite & (array % 1 != 0)

    # Order is priority: np.select gives each row the first label whose condition is true.
    checks = [
        ("blank_value", blank),
        ("parse_failure", np.isnan(array) & ~blank),
        ("non_finite", np.isinf(array)),
        ("reserved_code", negative & reserved),
        ("unexpected_negative", negative),
        ("fractional_count", fractional),
    ]
    issue = pd.Series(
        np.select(
            [condition for _, condition in checks],
            [label for label, _ in checks],
            default="",
        ),
        index=raw.index,
    )

    evidence = issue.map(NUMERIC_ISSUE_EVIDENCE).fillna("")
    code_meaning = number.where(issue.eq("reserved_code")).map(RESERVED_MEANING).fillna("")
    evidence = evidence.where(issue.ne("reserved_code"), code_meaning)
    values = number.where(issue.eq("")).astype("Float64")
    return ParsedNumeric(values=values, issue=issue, evidence=evidence)


def clean_numeric_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    whole_number: bool,
    source_file: str,
    log: QualityLog,
) -> pd.DataFrame:
    """Parse each numeric column and log every value that became NA."""
    frame = frame.copy()
    context = make_context(frame)
    for column in columns:
        parsed = parse_numeric(frame[column], whole_number=whole_number)
        flagged = parsed.issue.ne("")
        action = parsed.issue.map({"blank_value": "left_missing"}).fillna("set_to_NA")
        log.add(
            source_file=source_file,
            context=context,
            mask=flagged,
            raw_column=column,
            raw_value=frame[column],
            issue=parsed.issue,
            action=action,
            evidence=parsed.evidence,
        )
        frame[column] = parsed.values
    return frame


# ---------------------------------------------------------------------------
# Step 4: categories
# ---------------------------------------------------------------------------


def normalize_yes_no(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Standardize Yes and No. Anything else becomes NA and is reported."""
    text = raw.astype("string").str.strip().str.lower()
    cleaned = text.map({"yes": "Yes", "no": "No"}).astype("string")
    unexpected = text.notna() & cleaned.isna()
    # Order is priority: np.select gives each row the first label whose condition is true.
    checks = [
        ("blank_value", raw.isna().to_numpy()),
        ("unexpected_category", _truthy(unexpected).to_numpy()),
    ]
    issue = pd.Series(
        np.select(
            [condition for _, condition in checks],
            [label for label, _ in checks],
            default="",
        ),
        index=raw.index,
    )
    return cleaned, issue


def clean_categories(
    frame: pd.DataFrame, columns: Iterable[str], *, source_file: str, log: QualityLog
) -> pd.DataFrame:
    """Normalize Yes/No columns and log unexpected or blank values."""
    frame = frame.copy()
    context = make_context(frame)
    for column in columns:
        cleaned, issue = normalize_yes_no(frame[column])
        log.add(
            source_file=source_file,
            context=context,
            mask=issue.ne(""),
            raw_column=column,
            raw_value=frame[column],
            issue=issue,
            action="set_to_NA",
            evidence="Playbook step 4: only Yes and No are accepted, missing is never No",
        )
        frame[column] = cleaned
    return frame


def log_justice_conflicts(frame: pd.DataFrame, *, source_file: str, log: QualityLog) -> None:
    """Compare JJ with SCH_JUST_IND. JJ stays the main source (playbook section 5)."""
    both = frame["JJ"].notna() & frame[JUSTICE_COLUMN].notna()
    conflict = both & (frame["JJ"] != frame[JUSTICE_COLUMN])
    pair = "JJ=" + frame["JJ"].astype("string") + ";SCH_JUST_IND=" + frame[JUSTICE_COLUMN]
    log.add(
        source_file=source_file,
        context=make_context(frame),
        mask=conflict,
        raw_column="JJ|SCH_JUST_IND",
        raw_value=pair,
        issue="category_conflict",
        action="kept_JJ",
        cleaned_value=frame["JJ"],
        evidence="Playbook section 5: log disagreements and keep JJ pending resolution",
    )


def derive_grade_band(grades: pd.DataFrame) -> pd.Series:
    """Apply the playbook grade-band rule to Yes/No grade columns.

    Any unknown grade flag gives NA. Otherwise two or three of elementary, middle and
    high give "span", one gives its own label, and none gives "other".
    """
    known = grades[GRADE_COLUMNS].notna().all(axis=1)
    enrolled = grades[GRADE_COLUMNS].eq("Yes")
    levels = pd.DataFrame(
        {
            "elementary": enrolled[ELEMENTARY_GRADES].any(axis=1),
            "middle": enrolled[MIDDLE_GRADES].any(axis=1),
            "high": enrolled[HIGH_GRADES].any(axis=1),
        }
    ).astype(bool)
    count = levels.sum(axis=1)
    single = levels.idxmax(axis=1)
    band = pd.Series(
        np.select(
            [count.ge(2).to_numpy(), count.eq(1).to_numpy()],
            ["span", single.to_numpy()],
            default="other",
        ),
        index=grades.index,
    )
    return band.where(known, pd.NA).astype("string")


# ---------------------------------------------------------------------------
# Steps 5 and 6: joins
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JoinReport:
    """Key comparison for one join, for the QA report."""

    name: str
    key: str
    left_rows: int
    right_rows: int
    missing_keys: int
    extra_keys: int
    matched_rows: int


def _log_key_gaps(
    roster: pd.DataFrame,
    other: pd.DataFrame,
    *,
    key: str,
    source_file: str,
    other_row_column: str,
    roster_row_column: str,
    roster_file: str,
    log: QualityLog,
) -> tuple[pd.Series, pd.Series]:
    """Log roster keys missing from `other` and extra keys in `other`. Returns both masks."""
    roster_keys = set(roster[key].dropna())
    other_keys = set(other[key].dropna())
    is_missing = ~roster[key].isin(other_keys) & ~roster[key].duplicated()
    is_extra = ~other[key].isin(roster_keys) & ~other[key].duplicated()

    log.add(
        source_file=roster_file,
        context=make_context(roster, roster_row_column),
        mask=is_missing,
        raw_column=key.upper(),
        raw_value=roster[key],
        issue="missing_key_in_module",
        action="left_missing",
        evidence=f"Playbook steps 5 and 6: roster key has no row in {source_file}",
    )
    log.add(
        source_file=source_file,
        context=make_context(
            other,
            other_row_column,
            combokey="combokey" if "combokey" in other else None,
            leaid="leaid" if "leaid" in other else None,
        ),
        mask=is_extra,
        raw_column=key.upper(),
        raw_value=other[key],
        issue="extra_key_in_module",
        action="ignored",
        evidence="Playbook steps 5 and 6: module key is not in the roster",
    )
    return is_missing, is_extra


def left_join_validated(
    roster: pd.DataFrame,
    other: pd.DataFrame,
    *,
    key: str,
    validate: str,
    name: str,
    source_file: str,
    other_row_column: str,
    roster_row_column: str,
    roster_file: str,
    log: QualityLog,
) -> tuple[pd.DataFrame, JoinReport]:
    """Left-join `other` onto `roster` and prove the roster did not change.

    Key sets are compared first, and missing and extra keys go to the quality log. The
    result gets a boolean column `has_<name>` that says whether the row found a match.
    `roster_row_column` and `roster_file` say where roster rows came from, for the log.
    """
    overlap = (set(roster.columns) & set(other.columns)) - {key}
    if overlap:
        raise JoinValidationError(f"{name}: columns exist on both sides: {sorted(overlap)}")

    is_missing, is_extra = _log_key_gaps(
        roster,
        other,
        key=key,
        source_file=source_file,
        other_row_column=other_row_column,
        roster_row_column=roster_row_column,
        roster_file=roster_file,
        log=log,
    )

    marker = f"has_{name}"
    try:
        merged = roster.merge(other.assign(**{marker: True}), how="left", on=key, validate=validate)
    except pd.errors.MergeError as error:
        raise JoinValidationError(f"{name}: {error}") from error
    if len(merged) != len(roster):
        raise JoinValidationError(f"{name}: roster changed from {len(roster)} to {len(merged)}")
    merged[marker] = _truthy(merged[marker])
    report = JoinReport(
        name=name,
        key=key,
        left_rows=len(roster),
        right_rows=len(other),
        missing_keys=int(is_missing.sum()),
        extra_keys=int(is_extra.sum()),
        matched_rows=int(merged[marker].sum()),
    )
    return merged, report


def log_lea_conflicts(roster: pd.DataFrame, *, source_file: str, log: QualityLog) -> None:
    """Log districts whose name or state differs between the school and LEA files."""
    pairs = roster.drop_duplicates(["leaid", "LEA_NAME", "LEA_STATE"])
    pairs = pairs[pairs["has_lea"]]
    context = make_context(pairs, src_row_col("lea"), combokey=None)
    # (raw school column, school value compared, LEA file value, issue, action, value kept)
    comparisons = (
        (
            "LEA_NAME",
            "LEA_NAME",
            "lea_name",
            "lea_name_conflict",
            "used_LEA_file_value",
            "lea_name",
        ),
        (
            "LEA_STATE",
            "lea_state",
            "lea_state_file",
            "lea_state_conflict",
            "kept_school_file_value",
            "lea_state",
        ),
    )
    for raw_column, school_value, file_value, issue, action, kept in comparisons:
        differs = pairs[school_value].fillna("") != pairs[file_value].fillna("")
        log.add(
            source_file=source_file,
            context=context,
            mask=differs,
            raw_column=raw_column,
            raw_value=pairs[raw_column],
            issue=issue,
            action=action,
            cleaned_value=pairs[kept],
            evidence="Playbook step 6: ID or name disagreement between school and LEA files",
        )


# ---------------------------------------------------------------------------
# Steps 7 to 10: features
# ---------------------------------------------------------------------------


def strict_sum(columns: pd.DataFrame) -> pd.Series:
    """Add columns row by row. Any missing part makes the whole sum NA."""
    all_valid = columns.notna().all(axis=1)
    return columns.sum(axis=1, skipna=True).astype("Float64").where(all_valid)


def component_total(
    male: pd.Series, female: pd.Series, nonbinary: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """Total students from M, F and optional X.

    The total is NA unless both M and F are valid. A valid X is added. A missing X is not
    treated as zero in the flag: `partial` is True whenever X is unavailable.
    """
    total = (male + female) + nonbinary.fillna(0)
    return total.astype("Float64"), nonbinary.isna()


def rate_per_100(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """100 * numerator / denominator, NA unless both are valid and denominator > 0."""
    positive = denominator.where(_truthy(denominator > 0))
    return (100 * numerator / positive).astype("Float64")


def subgroup_exceeds_total(subgroup: pd.Series, total: pd.Series) -> pd.Series:
    """True where both counts are valid and the subgroup is larger than the total."""
    return _truthy(subgroup.notna() & total.notna() & (subgroup > total))


def derive_percentage(subgroup: pd.Series, total: pd.Series) -> pd.Series:
    """Subgroup share of total in percent. NA when the subgroup is larger than the total."""
    share = rate_per_100(subgroup, total).where(~subgroup_exceeds_total(subgroup, total))
    return share.astype("Float64")


def fte_review_threshold(output_column: str) -> int:
    """Playbook step 10: teachers above 2,000, any other core FTE above 200."""
    return TEACHER_FTE_REVIEW if output_column == "fte_teachers" else OTHER_FTE_REVIEW


def fte_review_mask(table: pd.DataFrame) -> pd.Series:
    """True where any core FTE meets a playbook review trigger."""
    triggered = pd.Series(False, index=table.index)
    for column in FTE_COLUMNS:
        triggered = triggered | _truthy(table[column] > fte_review_threshold(column))
    return triggered


def analysis_ready_mask(table: pd.DataFrame) -> pd.Series:
    """True for schools with a valid seclusion rate and positive enrollment (one shared rule)."""
    return _truthy(table["seclusion_rate"].notna() & (table["enrollment_total"] > 0))


def build_school_table(roster: pd.DataFrame) -> pd.DataFrame:
    """Build the shared output table from the joined roster (playbook sections 3 and 4)."""
    table = pd.DataFrame(index=roster.index)
    table["year"] = YEAR_LABEL
    for column in ("combokey", "leaid", "schid", "sch_name", "lea_state"):
        table[column] = roster[column]
    table["lea_name"] = roster["lea_name"]
    for output, raw in CATEGORY_COLUMNS.items():
        table[output] = roster[raw]
    table["grade_band"] = derive_grade_band(roster)

    for output, raw in SECLUSION_COLUMNS.items():
        table[output] = roster[raw]
    table["seclusion_instances"] = strict_sum(table[list(SECLUSION_COLUMNS)])

    for output, (male, female, nonbinary) in ENROLLMENT_PARTS.items():
        table[output], table[PARTIAL_FLAGS[output]] = component_total(
            roster[male], roster[female], roster[nonbinary]
        )
    table["enr_nonbinary"] = roster["TOT_ENR_X"]

    for output, raw in FTE_COLUMNS.items():
        table[output] = roster[raw]
    for output, raw in LEA_COUNT_COLUMNS.items():
        table[output] = roster[raw]

    enrollment = table["enrollment_total"]
    table["seclusion_rate"] = rate_per_100(table["seclusion_instances"], enrollment)
    table["counselors_per_100"] = rate_per_100(table["fte_counselors"], enrollment)
    table["teachers_per_100"] = rate_per_100(table["fte_teachers"], enrollment)
    table["support_fte_per_100"] = rate_per_100(strict_sum(table[SUPPORT_FTE_COLUMNS]), enrollment)
    for subgroup, output in PERCENT_COLUMNS.items():
        table[output] = derive_percentage(table[subgroup], enrollment)

    table["flag_missing_seclusion"] = table["seclusion_instances"].isna()
    table["flag_missing_enrollment"] = _truthy(enrollment.isna() | (enrollment <= 0))
    table["flag_small_enrollment"] = _truthy(enrollment < SMALL_ENROLLMENT)
    table["flag_fte_outlier"] = fte_review_mask(table)
    table["flag_missing_module"] = ~roster[[f"has_{key}" for key in SCHOOL_MODULE_KEYS]].all(axis=1)
    table["flag_missing_lea"] = ~roster["has_lea"]
    table["flag_analysis_ready"] = analysis_ready_mask(table)
    return table


def log_subgroup_conflicts(roster: pd.DataFrame, table: pd.DataFrame, log: QualityLog) -> None:
    """Log schools where IDEA, 504 or EL enrollment is larger than total enrollment.

    The matching percentage is NA. The counts stay, and nothing is clipped to 100.
    """
    context = make_context(roster, src_row_col("enrollment"))
    for subgroup in PERCENT_COLUMNS:
        log.add(
            source_file=MODULES["enrollment"].file_name,
            context=context,
            mask=subgroup_exceeds_total(table[subgroup], table["enrollment_total"]),
            raw_column=subgroup,
            raw_value=_format_number(table[subgroup]),
            issue="subgroup_exceeds_total",
            action="percentage_set_to_NA",
            evidence="Playbook section 4: subgroup above total is a review issue, not clipped",
        )


def log_fte_review(roster: pd.DataFrame, table: pd.DataFrame, log: QualityLog) -> None:
    """Log FTE values that meet a review trigger and the largest values per FTE.

    Nothing is changed: the playbook says to keep values unless documentation or a team
    decision supports a change.
    """
    context = make_context(roster, src_row_col("support"))
    for output, raw in FTE_COLUMNS.items():
        values = table[output]
        threshold = fte_review_threshold(output)
        top_rows = values.dropna().sort_values(ascending=False, kind="stable").index[:TOP_N_FTE]
        for issue, mask, note in (
            (
                "fte_review_threshold",
                _truthy(values > threshold),
                f"Playbook step 10: value above {threshold:,}, kept pending review",
            ),
            (
                FTE_TOP_ISSUE,
                table.index.isin(top_rows),
                f"Playbook step 10: one of the {TOP_N_FTE} largest values, kept",
            ),
        ):
            log.add(
                source_file=MODULES["support"].file_name,
                context=context,
                mask=pd.Series(mask, index=table.index),
                raw_column=raw,
                raw_value=_format_number(values),
                issue=issue,
                action="retained",
                cleaned_value=_format_number(values),
                evidence=note,
            )


# ---------------------------------------------------------------------------
# Step 11: output files
# ---------------------------------------------------------------------------


def enforce_schema(table: pd.DataFrame) -> pd.DataFrame:
    """Return the table with the exact playbook columns, order and data types."""
    result = table[OUTPUT_COLUMNS].copy()
    for column in STRING_COLUMNS:
        result[column] = result[column].astype("string")
    for column in FLOAT_COLUMNS:
        result[column] = result[column].astype("Float64")
    for column in BOOLEAN_COLUMNS:
        result[column] = result[column].astype("boolean")
    return result


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a CSV in the team format: UTF-8, header, no index, empty cells for NA."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", na_rep="", lineterminator="\n")


def read_clean_csv(path: Path) -> pd.DataFrame:
    """Read a cleaned school table back with explicit types (IDs stay strings)."""
    dtypes: dict[str, str] = {name: "string" for name in STRING_COLUMNS}
    dtypes.update({name: "Float64" for name in FLOAT_COLUMNS})
    dtypes.update({name: "boolean" for name in BOOLEAN_COLUMNS})
    return pd.read_csv(path, dtype=dtypes, keep_default_na=False, na_values=[""], encoding="utf-8")


def validate_tables(full: pd.DataFrame, analysis: pd.DataFrame, roster_rows: int) -> None:
    """Check the playbook section 6 rules on the final tables."""
    problems: list[str] = []
    if list(full.columns) != OUTPUT_COLUMNS:
        problems.append("columns or column order differ from section 3.1")
    if len(full) != roster_rows:
        problems.append(f"full table has {len(full)} rows, roster has {roster_rows}")
    if full["combokey"].duplicated().any():
        problems.append("duplicate combokey values")
    for column, width in (
        ("combokey", COMBOKEY_WIDTH),
        ("leaid", LEAID_WIDTH),
        ("schid", SCHID_WIDTH),
    ):
        # A missing ID gives NA here, which must fail the check instead of passing it.
        if not _truthy(full[column].str.len() == width).all():
            problems.append(f"{column} is missing or not {width} characters for some rows")
    if not (full["combokey"] == full["leaid"] + full["schid"]).all():
        problems.append("combokey is not leaid + schid for every row")
    for column in NONNEGATIVE_COLUMNS:
        if (full[column].dropna() < 0).any():
            problems.append(f"negative values in {column}")
    for column in [*NONNEGATIVE_COLUMNS, *RATE_COLUMNS]:
        if not np.isfinite(full[column].dropna().astype("float64")).all():
            problems.append(f"non-finite values in {column}")
    if full[BOOLEAN_COLUMNS].isna().any().any():
        problems.append("a flag column holds NA")
    enrollment = full["enrollment_total"]
    for column in RATE_COLUMNS:
        # A rate needs a valid, positive enrollment. Anything else must stay NA.
        no_enrollment = enrollment.isna() | _truthy(enrollment <= 0)
        if full.loc[no_enrollment, column].notna().any():
            problems.append(f"{column} has a value where enrollment is missing or not positive")
    ready = analysis_ready_mask(full)
    if not (full["flag_analysis_ready"] == ready).all():
        problems.append("flag_analysis_ready does not match seclusion_rate and enrollment")
    expected = full[ready].reset_index(drop=True)
    if not expected.equals(analysis.reset_index(drop=True)):
        problems.append("analysis table is not the full table filtered by the analysis rule")
    if problems:
        raise OutputValidationError("; ".join(problems))


def verify_reload(full: pd.DataFrame, path: Path) -> None:
    """Reload the written CSV and confirm values, missing cells and types survived."""
    reloaded = read_clean_csv(path)
    try:
        pd.testing.assert_frame_equal(reloaded, full, check_dtype=True)
    except AssertionError as error:
        message = f"{path.name} does not reload to the same table: {error}"
        raise OutputValidationError(message) from error


# ===========================================================================
# Part B: documentation outputs (the mapping file and the QA report)
# ===========================================================================

# ---------------------------------------------------------------------------
# Mapping file (docs/cleaning/mapping_{year}.csv)
# ---------------------------------------------------------------------------


def _sheet_b(question: str) -> str:
    """Cite an Appendix Workbook Sheet B question."""
    return f"Appendix Sheet B, {question}"


def build_mapping() -> pd.DataFrame:
    """One row per input field, including fields left out on purpose."""
    rows: list[tuple[str, str, str, str, str, str, str]] = []

    def add(module: str, column: str, output: str, how: str, units: str, ref: str, status: str):
        rows.append((MODULES[module].relative_path, column, output, how, units, ref, status))

    for module in ("char", *SCHOOL_MODULE_KEYS):
        leaid_how = f"Validate, zero-pad to {LEAID_WIDTH}"
        add(module, "LEAID", "leaid", leaid_how, "District ID", MANUAL_IDS, VERIFIED)
        schid_how = f"Validate, zero-pad to {SCHID_WIDTH}"
        add(module, "SCHID", "schid", schid_how, "School ID", MANUAL_IDS, VERIFIED)
        add(
            module,
            "COMBOKEY",
            "combokey",
            "Validate, must equal LEAID + SCHID, join key",
            "School ID",
            MANUAL_IDS,
            VERIFIED,
        )
    add(
        "lea",
        "LEAID",
        "leaid",
        f"Validate, zero-pad to {LEAID_WIDTH}, join key",
        "District ID",
        MANUAL_IDS,
        VERIFIED,
    )

    add("char", "LEA_STATE", "lea_state", "Trim, uppercase", "State code", NOT_DEFINED, UNRESOLVED)
    add("char", "SCH_NAME", "sch_name", "Trim", "School name", NOT_DEFINED, UNRESOLVED)
    add(
        "char",
        "LEA_NAME",
        "",
        "Compared with the LEA file, not output",
        "District name",
        NOT_DEFINED,
        UNRESOLVED,
    )
    add("lea", "LEA_NAME", "lea_name", "Trim", "District name", NOT_DEFINED, UNRESOLVED)
    add(
        "lea",
        "LEA_STATE",
        "",
        "Compared with the school file, not output",
        "State code",
        NOT_DEFINED,
        UNRESOLVED,
    )
    add(
        "char",
        "JJ",
        "jj",
        "Yes/No/NA, main justice-facility source",
        "School",
        "Not listed in Appendix Sheet B. SCH_JUST_IND (SCHR-2) is the listed field",
        UNRESOLVED,
    )
    add(
        "char",
        JUSTICE_COLUMN,
        "",
        "Yes/No/NA, compared with JJ, disagreements logged",
        "School",
        _sheet_b("SCHR-2"),
        VERIFIED,
    )
    add(
        "char",
        "SCH_VIRT_IND",
        "sch_virt_ind",
        "Yes/No/NA",
        "School, fully virtual",
        _sheet_b("SCHR-1"),
        VERIFIED,
    )
    for output, raw, question in (
        ("sch_status_sped", "SCH_STATUS_SPED", "SCHR-5.1"),
        ("sch_status_magnet", "SCH_STATUS_MAGNET", "SCHR-5.2"),
        ("sch_status_charter", "SCH_STATUS_CHARTER", "SCHR-5.3"),
        ("sch_status_alt", "SCH_STATUS_ALT", "SCHR-5.4"),
    ):
        add("char", raw, output, "Yes/No/NA", "School", _sheet_b(question), VERIFIED)
    add(
        "char",
        "SCH_GRADE_PS",
        "",
        "Left out of grade_band",
        "Preschool flag",
        _sheet_b("SCHR-3.1"),
        VERIFIED,
    )
    add(
        "char",
        "SCH_GRADE_UG",
        "",
        "Left out of grade_band",
        "Ungraded flag",
        _sheet_b("SCHR-3.15"),
        VERIFIED,
    )
    for index, raw in enumerate(GRADE_COLUMNS):
        add(
            "char",
            raw,
            "grade_band",
            "Yes/No/NA, combined by the grade-band rule",
            "Grade offered",
            _sheet_b(f"SCHR-3.{index + FIRST_GRADE_QUESTION}"),
            VERIFIED,
        )

    for output, (male, female, nonbinary) in ENROLLMENT_PARTS.items():
        if output == "enrollment_total":
            for raw in (male, female, nonbinary):
                add(
                    "enrollment",
                    raw,
                    output if raw != nonbinary else "enr_nonbinary; enrollment_total",
                    "Calculated total; M+F strict, X added only when valid",
                    "Students, overall (preschool coverage not stated)",
                    "Appendix Sheet C and User's Manual 5.5.2. Preschool inclusion is not stated",
                    UNRESOLVED,
                )
            continue
        first = ENROLLMENT_QUESTION_START[output]
        label = ENROLLMENT_GROUP_LABELS[output]
        for offset, raw in enumerate((male, female, nonbinary)):
            add(
                "enrollment",
                raw,
                output,
                "Count; M+F strict, X added only when valid",
                f"Students, {label}",
                _sheet_b(f"ENRL-1.{first + offset}"),
                VERIFIED,
            )

    for output, raw in SECLUSION_COLUMNS.items():
        add(
            "restraint",
            raw,
            output,
            "Count; summed with the other two groups, NA if any is NA",
            "Instances of seclusion (not students)",
            _sheet_b(SECLUSION_QUESTIONS[raw]),
            VERIFIED,
        )
    for output, raw in FTE_COLUMNS.items():
        add(
            "support",
            raw,
            output,
            "Numeric FTE, fractions kept",
            "FTE (decimal)",
            _sheet_b(FTE_QUESTIONS[raw]),
            VERIFIED,
        )
    add(
        "lea",
        "LEA_ENR",
        "lea_enrollment",
        "Count",
        "Students in district",
        _sheet_b("SSPR-1"),
        VERIFIED,
    )
    add(
        "lea",
        "LEA_SCHOOLS",
        "lea_schools",
        "Count",
        "Public schools in district",
        _sheet_b("SSPR-3"),
        VERIFIED,
    )

    mapping = pd.DataFrame(rows, columns=MAPPING_COLUMNS)
    mapping["units_population_period"] = mapping["units_population_period"] + f", {PERIOD}"
    return mapping


# ---------------------------------------------------------------------------
# QA report (docs/cleaning/qa_{year}.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QaContext:
    """Everything the QA report needs."""

    sources: list[SourceInfo]
    reference_files: list[tuple[str, str]]
    joins: list[JoinReport]
    full: pd.DataFrame
    analysis: pd.DataFrame
    quality: pd.DataFrame
    mapping: pd.DataFrame
    summaries: list[tuple[str, str, str, int]]
    rerun_command: str


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    """Render a markdown table as a list of lines."""
    names = [str(header) for header in headers]
    lines = ["| " + " | ".join(names) + " |", "|" + "|".join("---" for _ in names) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return [*lines, ""]


def _qa_sources(ctx: QaContext) -> list[str]:
    """Section: input files, their hashes, encodings and row counts."""
    lines = [
        "## Sources",
        "",
        f"Package: {PACKAGE_NAME}. Paths are relative to the raw data folder.",
        "",
    ]
    lines += _md_table(
        ["File", "Encoding", "Rows parsed", "Rows kept", "SHA-256"],
        [
            (s.relative_path, s.encoding, f"{s.rows_parsed:,}", f"{s.rows_kept:,}", s.sha256)
            for s in ctx.sources
        ],
    )
    lines += ["Reference files used for definitions:", ""]
    lines += _md_table(["File", "SHA-256"], ctx.reference_files)
    return lines


def _qa_counts(ctx: QaContext) -> list[str]:
    """Section: reserved codes and row counts compared with the audit figures."""
    reserved = ctx.quality[ctx.quality["issue"] == "reserved_code"]
    reserved_instances = reserved[reserved["raw_column"].isin(SECLUSION_COLUMNS.values())]
    reserved_schools = reserved_instances["source_row"].nunique()
    lines = ["## Row counts", ""]
    lines += _md_table(
        ["Item", "Count", "Audit comparison"],
        [
            ("Roster schools (full table)", f"{len(ctx.full):,}", f"{AUDIT_ROSTER_SCHOOLS:,}"),
            ("Analysis-ready schools", f"{len(ctx.analysis):,}", "Recomputed, not matched"),
            (
                "Schools with a reserved seclusion instance value",
                f"{reserved_schools:,}",
                f"{AUDIT_RESERVED_INSTANCE_SCHOOLS:,}",
            ),
        ],
    )
    return lines


def _qa_ids(ctx: QaContext) -> list[str]:
    """Section: ID padding and the IDs kept as reported."""
    non_digit = ctx.quality[ctx.quality["issue"] == "non_digit_id"]
    lines = ["## IDs", ""]
    if non_digit.empty:
        lines += ["Every ID is a digit string of the expected length.", ""]
    else:
        summary = non_digit.groupby(["source_file", "raw_column"]).size().reset_index()
        lines += [
            "Some IDs contain capital letters, for example 24SOP02. They belong to "
            "state-operated programs and CRDC issued them. They have the right length, so "
            "they were kept as reported and every one is in the quality detail file. "
            "The team needs to decide whether to keep them.",
            "",
        ]
        lines += _md_table(["File", "Column", "Rows"], summary.itertuples(index=False, name=None))
    if ctx.summaries:
        lines += [
            "These module files store SCHID without leading zeros. The values were padded "
            "to 5 digits before joining. The Joins section shows how many keys then matched "
            "the roster.",
            "",
        ]
        lines += _md_table(
            ["File", "Column", "Rows padded"],
            [(file, column, f"{rows:,}") for file, column, _, rows in ctx.summaries],
        )
    sample_rows = np.linspace(0, len(ctx.full) - 1, 5, dtype=int)
    samples = ctx.full.iloc[sample_rows]
    lines += ["Five sample keys:", ""]
    lines += _md_table(
        ["combokey", "Length", "leaid", "Length", "schid", "Length"],
        [
            (row.combokey, len(row.combokey), row.leaid, len(row.leaid), row.schid, len(row.schid))
            for row in samples.itertuples()
        ],
    )
    return lines


def _qa_joins(ctx: QaContext) -> list[str]:
    """Section: key comparison and match counts for each join."""
    lines = ["## Joins", ""]
    lines += _md_table(
        [
            "Join",
            "Key",
            "Roster rows",
            "Module rows",
            "Roster keys missing",
            "Extra keys",
            "Matched",
        ],
        [
            (
                j.name,
                j.key,
                f"{j.left_rows:,}",
                f"{j.right_rows:,}",
                f"{j.missing_keys:,}",
                f"{j.extra_keys:,}",
                f"{j.matched_rows:,}",
            )
            for j in ctx.joins
        ],
    )
    kept = all(j.left_rows == len(ctx.full) for j in ctx.joins)
    lines += [
        "Every join kept the roster row count." if kept else "A join changed the roster rows.",
        "Missing and extra keys are listed one by one in the quality detail file.",
        "",
    ]
    return lines


def _qa_missingness(ctx: QaContext) -> list[str]:
    """Section: missing values in each output column."""
    lines = ["## Missing values by output column", ""]
    rows = []
    for column in OUTPUT_COLUMNS:
        missing = int(ctx.full[column].isna().sum())
        if missing:
            rows.append((column, f"{missing:,}", f"{100 * missing / len(ctx.full):.1f}%"))
    lines += _md_table(["Column", "Missing rows", "Share"], rows)
    reserved = ctx.quality[ctx.quality["issue"] == "reserved_code"]
    if not reserved.empty:
        codes = reserved["raw_value"].astype(float).astype(int)
        counts = pd.crosstab(reserved["raw_column"], codes)
        lines += ["Reserved codes by raw column (counts of values set to NA):", ""]
        lines += _md_table(
            ["Raw column", *counts.columns],
            [(name, *[f"{value:,}" for value in row]) for name, row in counts.iterrows()],
        )
    return lines


def _qa_issue_summary(ctx: QaContext) -> list[str]:
    """Section: rows in the quality log per issue and action."""
    summary = ctx.quality.groupby(["issue", "action"]).size().reset_index(name="rows")
    lines = ["## Quality log summary", ""]
    lines += _md_table(
        ["Issue", "Action", "Rows"],
        [(r.issue, r.action, f"{r.rows:,}") for r in summary.itertuples()],
    )
    return lines


def _qa_groups(ctx: QaContext) -> list[str]:
    """Section: school groups in the full and analysis tables."""
    full, analysis = ctx.full, ctx.analysis
    groups: list[tuple[str, pd.Series, pd.Series]] = []
    for value in ("Yes", "No"):
        groups.append((f"jj = {value}", full["jj"].eq(value), analysis["jj"].eq(value)))
    groups.append(("jj missing", full["jj"].isna(), analysis["jj"].isna()))
    for flag in (
        "flag_small_enrollment",
        "flag_partial_enrollment",
        "flag_partial_idea",
        "flag_partial_504",
        "flag_partial_el",
        "flag_fte_outlier",
        "flag_missing_seclusion",
        "flag_missing_enrollment",
        "flag_missing_module",
        "flag_missing_lea",
    ):
        groups.append((f"{flag} = True", full[flag], analysis[flag]))
    lines = ["## Counts by group", ""]
    lines += _md_table(
        ["Group", "Full table", "Analysis table"],
        [(name, f"{int(a.sum()):,}", f"{int(b.sum()):,}") for name, a, b in groups],
    )
    lines += [
        "A partial flag means the nonbinary count (X) was unavailable, so that total holds "
        "only the reported male and female students and may be incomplete.",
        "",
    ]
    return lines


def _qa_fte(ctx: QaContext) -> list[str]:
    """Section: FTE values that meet a review trigger and the largest values."""
    review = ctx.quality[ctx.quality["issue"].isin(["fte_review_threshold", FTE_TOP_ISSUE])]
    lines = ["## FTE review", ""]
    lines += [
        f"Schools with flag_fte_outlier: {int(ctx.full['flag_fte_outlier'].sum()):,}. "
        "No value was changed or capped. The team decides what to do with them.",
        "",
    ]
    top = review[review["issue"] == FTE_TOP_ISSUE].copy()
    top["value"] = top["raw_value"].astype(float)
    rows = []
    for column, group in top.groupby("raw_column"):
        largest = group.sort_values(["value", "combokey"], ascending=[False, True], kind="stable")
        listed = ", ".join(f"{r.value:g} ({r.combokey})" for r in largest.itertuples())
        rows.append((column, listed))
    lines += _md_table(["Raw column", f"Largest {TOP_N_FTE} values (combokey)"], rows)
    return lines


def _qa_unresolved(ctx: QaContext) -> list[str]:
    """Section: open questions the team still has to decide."""
    unresolved = int((ctx.mapping["verification_status"] == UNRESOLVED).sum())
    odd_negatives = int((ctx.quality["issue"] == "unexpected_negative").sum())
    notes = [
        f"{unresolved} mapping rows are marked unresolved. See mapping_{YEAR_CODE}.csv.",
        "TOT_ENR_M, TOT_ENR_F and TOT_ENR_X are calculated totals. The appendix does not say "
        "whether they include preschool students, so rates that use them need that check. "
        "The manual says totals were built by treating reserve codes as zero, so a total can "
        "be a partial sum.",
        "JJ is not listed in Appendix Sheet B. JJ was kept as the main source and compared "
        "with SCH_JUST_IND.",
        f"Negative values that are not 2021-22 reserve codes: {odd_negatives:,}.",
        "flag_analysis_ready uses the data rules only: a valid seclusion total and positive "
        "enrollment. The enrollment coverage question above is still open.",
        "Public-use student counts were perturbed by one case (manual 5.2.1), so small counts "
        "are slightly noisy.",
        "The playbook names grade columns SCH_GRADE_G1 to G12. The real headers are "
        "zero-padded (SCH_GRADE_G01 to SCH_GRADE_G12), and the script uses those.",
    ]
    return ["## Unresolved issues and notes", "", *[f"- {note}" for note in notes], ""]


def render_qa_report(ctx: QaContext) -> str:
    """Assemble the QA markdown. It has no timestamps, so reruns give identical text."""
    environment = (
        f"Python {platform.python_version()}, pandas {pd.__version__}, numpy {np.__version__}"
    )
    lines = [
        f"# QA report for {YEAR_LABEL} CRDC cleaning",
        "",
        "This file is written by `scripts/clean_202122.py`. Do not edit it by hand.",
        "",
        "## How to rerun",
        "",
        "```text",
        ctx.rerun_command,
        "```",
        "",
        f"Dependencies are listed in requirements.txt. This run used {environment}.",
        "",
    ]
    for section in (
        _qa_sources,
        _qa_counts,
        _qa_ids,
        _qa_joins,
        _qa_missingness,
        _qa_issue_summary,
        _qa_groups,
        _qa_fte,
        _qa_unresolved,
    ):
        lines += section(ctx)
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineResult:
    full: pd.DataFrame
    analysis: pd.DataFrame
    quality: pd.DataFrame
    joins: list[JoinReport]
    summaries: list[tuple[str, str, str, int]]


def _prepare_school_module(frame: pd.DataFrame, spec: ModuleSpec, log: QualityLog) -> pd.DataFrame:
    """Validate IDs and numbers of one school module and keep only what the join needs."""
    frame = clean_module_ids(frame, spec=spec, log=log)
    raw_columns = [c for c in spec.columns if c not in _SCHOOL_IDS]
    fte_columns = [c for c in raw_columns if c in FTE_COLUMNS.values()]
    count_columns = [c for c in raw_columns if c not in fte_columns]
    for columns, whole_number in ((count_columns, True), (fte_columns, False)):
        frame = clean_numeric_columns(
            frame, columns, whole_number=whole_number, source_file=spec.file_name, log=log
        )
    keep = ["combokey", "source_row", *raw_columns]
    return frame[keep].rename(columns={"source_row": src_row_col(spec.key)})


def _prepare_roster(frame: pd.DataFrame, spec: ModuleSpec, log: QualityLog) -> pd.DataFrame:
    """Validate IDs and categories of School Characteristics, the roster."""
    frame = clean_module_ids(frame, spec=spec, log=log)
    categories = [*CATEGORY_COLUMNS.values(), JUSTICE_COLUMN, *GRADE_COLUMNS]
    frame = clean_categories(frame, categories, source_file=spec.file_name, log=log)
    log_justice_conflicts(frame, source_file=spec.file_name, log=log)
    frame["lea_state"] = frame["LEA_STATE"].str.upper()
    frame["sch_name"] = frame["SCH_NAME"]
    return frame.rename(columns={"source_row": src_row_col(spec.key)})


def _prepare_lea(frame: pd.DataFrame, spec: ModuleSpec, log: QualityLog) -> pd.DataFrame:
    """Validate IDs and counts of the LEA file and give its columns distinct names."""
    frame = frame.assign(combokey=pd.Series(pd.NA, index=frame.index, dtype="string"))
    frame = clean_module_ids(frame, spec=spec, log=log)
    counts = list(LEA_COUNT_COLUMNS.values())
    frame = clean_numeric_columns(
        frame, counts, whole_number=True, source_file=spec.file_name, log=log
    )
    frame["lea_state_file"] = frame["LEA_STATE"].str.upper()
    row_column = src_row_col(spec.key)
    return frame.rename(columns={"source_row": row_column, "LEA_NAME": "lea_name"})[
        ["leaid", row_column, "lea_name", "lea_state_file", *counts]
    ]


def run_pipeline(raw_dir: Path, log: QualityLog) -> tuple[PipelineResult, list[SourceInfo]]:
    """Read, clean, join and derive the school table. Writes nothing."""
    sources: list[SourceInfo] = []
    frames: dict[str, pd.DataFrame] = {}
    for key, spec in MODULES.items():
        frames[key], info = read_module(raw_dir, spec, log)
        sources.append(info)

    roster = _prepare_roster(frames["char"], MODULES["char"], log)
    roster_rows = len(roster)
    joins: list[JoinReport] = []
    for key in SCHOOL_MODULE_KEYS:
        spec = MODULES[key]
        module = _prepare_school_module(frames[key], spec, log)
        roster, report = left_join_validated(
            roster,
            module,
            key="combokey",
            validate="one_to_one",
            name=key,
            source_file=spec.file_name,
            other_row_column=src_row_col(key),
            roster_row_column=src_row_col("char"),
            roster_file=MODULES["char"].file_name,
            log=log,
        )
        joins.append(report)
    lea_spec = MODULES["lea"]
    lea = _prepare_lea(frames["lea"], lea_spec, log)
    roster, report = left_join_validated(
        roster,
        lea,
        key="leaid",
        validate="many_to_one",
        name="lea",
        source_file=lea_spec.file_name,
        other_row_column=src_row_col("lea"),
        roster_row_column=src_row_col("char"),
        roster_file=MODULES["char"].file_name,
        log=log,
    )
    joins.append(report)
    log_lea_conflicts(roster, source_file=lea_spec.file_name, log=log)

    table = build_school_table(roster)
    log_subgroup_conflicts(roster, table, log)
    log_fte_review(roster, table, log)
    full = enforce_schema(table).sort_values("combokey", kind="stable").reset_index(drop=True)
    analysis = full[full["flag_analysis_ready"]].reset_index(drop=True)
    validate_tables(full, analysis, roster_rows)
    return PipelineResult(full, analysis, log.to_frame(), joins, log.summaries), sources


def run(raw_dir: Path, out_dir: Path, docs_dir: Path) -> PipelineResult:
    """Run the whole cleaning and write the data files and the two reports."""
    log = QualityLog()
    quality_path = out_dir / f"quality_detail_{YEAR_CODE}.csv"
    full_path = out_dir / f"schools_{YEAR_CODE}.csv"
    analysis_path = out_dir / f"schools_{YEAR_CODE}_analysis.csv"
    mapping_path = docs_dir / f"mapping_{YEAR_CODE}.csv"
    qa_path = docs_dir / f"qa_{YEAR_CODE}.md"
    try:
        result, sources = run_pipeline(raw_dir, log)
    except CleaningError:
        # Old outputs from an earlier good run must not be mistaken for this run's results.
        for stale in (full_path, analysis_path, mapping_path, qa_path):
            stale.unlink(missing_ok=True)
        write_csv(log.to_frame(), quality_path)
        LOGGER.error("Stopped. Problems so far are in %s", display_path(quality_path))
        raise

    write_csv(result.full, full_path)
    write_csv(result.analysis, analysis_path)
    write_csv(result.quality, quality_path)
    verify_reload(result.full, full_path)

    mapping = build_mapping()
    write_csv(mapping, mapping_path)
    reference_files = [
        (name, sha256_of(raw_dir / name))
        for name in (MANUAL_FILE, APPENDIX_FILE)
        if (raw_dir / name).is_file()
    ]
    context = QaContext(
        sources=sources,
        reference_files=reference_files,
        joins=result.joins,
        full=result.full,
        analysis=result.analysis,
        quality=result.quality,
        summaries=result.summaries,
        mapping=mapping,
        rerun_command=(
            f"python scripts/clean_{YEAR_CODE}.py --raw-dir {display_path(raw_dir)} "
            f"--out-dir {display_path(out_dir)} --docs-dir {display_path(docs_dir)}"
        ),
    )
    qa_path.write_text(render_qa_report(context), encoding="utf-8", newline="\n")
    LOGGER.info(
        "Wrote %s schools (%s analysis-ready) to %s",
        f"{len(result.full):,}",
        f"{len(result.analysis):,}",
        display_path(out_dir),
    )
    return result


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Clean the {YEAR_LABEL} CRDC data.")
    parser.add_argument(
        "--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="folder with SCH/ and LEA/"
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="folder for the CSV outputs"
    )
    parser.add_argument(
        "--docs-dir", type=Path, default=DEFAULT_DOCS_DIR, help="folder for mapping and QA files"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point. Returns the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    try:
        run(args.raw_dir, args.out_dir, args.docs_dir)
    except CleaningError as error:
        LOGGER.error("%s: %s", type(error).__name__, error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
