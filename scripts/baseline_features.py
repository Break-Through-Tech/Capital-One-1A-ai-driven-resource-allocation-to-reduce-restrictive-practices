"""Load cleaned CRDC years and turn them into model features for the baseline.

This module is used by scripts/train_baseline.py; it has no command line of its own. It
follows docs/AI_CONTEXT.md (section A4 for the 50 shared columns, A7 for the modeling rules)
and docs/eda/feature_shortlist_202122.csv for the feature list.

The file reads top to bottom:

    Constants and errors
    Loading one year (load_year)
    Row filters (apply_modeling_filters) and the target (make_target)
    FeatureBuilder: learns caps and states from training rows only, then builds features

Typical use:

    from baseline_features import FeatureBuilder, apply_modeling_filters, load_year, make_target

    train, _ = apply_modeling_filters(load_year("201718"))
    builder = FeatureBuilder(include_state=False).fit(train)
    features = builder.transform(train)
    target = make_target(train)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("baseline_features")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "processed"

YEAR_CODES = ("201516", "201718", "202021", "202122")
ID_DTYPES = {"combokey": str, "leaid": str, "schid": str}

# The outcome and every column used to build it (AI_CONTEXT A7). Any other column whose name
# starts with "seclusion_" is treated as a leak too.
LEAK_COLUMNS = (
    "seclusion_instances",
    "seclusion_instances_wodis",
    "seclusion_instances_idea",
    "seclusion_instances_504",
    "seclusion_rate",
    "flag_missing_seclusion",
    "flag_analysis_ready",
)
LEAK_PREFIX = "seclusion_"
# Identifiers and labels are never features. leaid is only used to group the CV folds.
ID_COLUMNS = ("year", "combokey", "leaid", "schid", "sch_name", "lea_name", "lea_state")

FTE_COLUMNS = (
    "fte_teachers",
    "fte_counselors",
    "fte_nurses",
    "fte_psych",
    "fte_social",
    "fte_leo",
    "fte_guards",
)
SUPPORT_FTE_COLUMNS = ("fte_counselors", "fte_nurses", "fte_psych", "fte_social")
YES_NO_FEATURES = {
    "is_sped": "sch_status_sped",
    "is_alt": "sch_status_alt",
    "is_charter": "sch_status_charter",
    "is_jj": "jj",
    "is_magnet": "sch_status_magnet",
}
PERCENT_FEATURES = ("pct_idea", "pct_504", "pct_el")
GRADE_BANDS = ("elementary", "middle", "high", "span", "other")
CAPPED_RATIOS = {"psych_p100": "fte_psych", "social_p100": "fte_social"}

# Columns this pipeline reads. load_year stops with a clear message if any is missing.
REQUIRED_COLUMNS = (
    "combokey",
    "leaid",
    "lea_state",
    "seclusion_instances",
    "enrollment_total",
    "grade_band",
    *YES_NO_FEATURES.values(),
    *PERCENT_FEATURES,
    *FTE_COLUMNS,
    "lea_enrollment",
)

# Row filters (EDA rule from docs/eda/data_issues_202122.csv, issue 3).
MIN_ENROLLMENT = 30
MAX_SUPPORT_PER_100 = 20.0
MAX_TEACHERS_PER_100 = 50.0
CAP_PERCENTILE = 99.5

BASE_FEATURES = (
    "log_enrollment",
    *(f"gb_{band}" for band in GRADE_BANDS),
    "gb_na",
    *YES_NO_FEATURES,
    *PERCENT_FEATURES,
    *(f"{name}_na" for name in PERCENT_FEATURES),
    *CAPPED_RATIOS,
    "log_lea_enrollment",
)
STATE_PREFIX = "st_"


class BaselineDataError(Exception):
    """Raised when an input file is missing or does not have the expected columns."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _as_float(values: pd.Series) -> pd.Series:
    """Numbers as plain float64 with NaN for missing, whatever the input dtype."""
    numbers = pd.to_numeric(values, errors="coerce")
    return pd.Series(
        np.asarray(numbers.to_numpy(dtype="float64", na_value=np.nan)), index=values.index
    )


def _as_bool(values: pd.Series) -> pd.Series:
    """Read a True/False flag column (bool, text or NA) as plain bool; NA counts as False."""
    if values.dtype == bool:
        return values
    text = values.astype("string").str.strip().str.lower()
    return text.isin(["true", "1", "1.0"]).fillna(False).astype(bool)


def _yes_no(values: pd.Series) -> pd.Series:
    """"Yes" -> 1, "No" -> 0, anything else (including NA) -> NaN."""
    text = values.astype("string").str.strip().str.lower()
    out = pd.Series(np.nan, index=values.index, dtype="float64")
    out[(text == "yes").fillna(False).to_numpy()] = 1.0
    out[(text == "no").fillna(False).to_numpy()] = 0.0
    return out


def _per_100(numerator: pd.Series, enrollment: pd.Series) -> pd.Series:
    """100 * numerator / enrollment, NaN when either is missing or enrollment is not above 0."""
    num = _as_float(numerator)
    den = _as_float(enrollment)
    ratio = 100.0 * num / den.where(den > 0)
    return ratio.replace([np.inf, -np.inf], np.nan)


def leak_or_id_columns(columns: Iterable[str]) -> list[str]:
    """Names in `columns` that are outcome leaks or identifiers."""
    banned = set(LEAK_COLUMNS) | set(ID_COLUMNS)
    return [name for name in columns if name in banned or name.startswith(LEAK_PREFIX)]


# ---------------------------------------------------------------------------
# Loading one year
# ---------------------------------------------------------------------------


def year_file_candidates(code: str, data_dir: Path) -> list[Path]:
    """Where a year's analysis file may live, in the order they are tried."""
    name = f"schools_{code}_analysis.csv"
    return [Path(data_dir) / code / name, Path(data_dir) / name]


def load_year(code: str, data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Read data/processed/{code}/schools_{code}_analysis.csv (or the flat fallback).

    IDs are read as text and numbers exactly as written (AI_CONTEXT A6). Raises
    BaselineDataError when the file is missing or lacks a column in REQUIRED_COLUMNS.
    """
    if code not in YEAR_CODES:
        raise BaselineDataError(f"Unknown year code {code!r}; expected one of {YEAR_CODES}")
    candidates = year_file_candidates(code, data_dir)
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        tried = "\n".join(f"  - {candidate}" for candidate in candidates)
        raise BaselineDataError(
            f"Cleaned file for {code} not found. Put schools_{code}_analysis.csv here:\n"
            f"{tried}\n(the first location is preferred), or pass --data-dir."
        )
    frame = pd.read_csv(path, dtype=ID_DTYPES, float_precision="round_trip")
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise BaselineDataError(f"{path} is missing required columns: {', '.join(missing)}")
    LOGGER.info("Loaded %s rows for %s from %s", f"{len(frame):,}", code, path)
    return frame


# ---------------------------------------------------------------------------
# Row filters and target
# ---------------------------------------------------------------------------


def implausible_staffing(frame: pd.DataFrame) -> pd.Series:
    """True for schools that fail the EDA staffing plausibility rules (data_issues #3).

    A school is implausible if any FTE exceeds enrollment, if counselors + nurses +
    psychologists + social workers exceed 20 per 100 students (missing FTEs count as 0 in
    this sum), or if teachers exceed 50 per 100 students. Missing values never mark a row.
    """
    enrollment = _as_float(frame["enrollment_total"])
    bad = pd.Series(False, index=frame.index)
    for name in FTE_COLUMNS:
        bad |= (_as_float(frame[name]) > enrollment).fillna(False)
    support = sum(_as_float(frame[name]).fillna(0.0) for name in SUPPORT_FTE_COLUMNS)
    bad |= (_per_100(support, enrollment) > MAX_SUPPORT_PER_100).fillna(False)
    bad |= (_per_100(frame["fte_teachers"], enrollment) > MAX_TEACHERS_PER_100).fillna(False)
    return bad


def apply_modeling_filters(
    frame: pd.DataFrame, exclude_states: Iterable[str] | None = None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Keep the rows used for modeling and report the row count after each step.

    Steps: (1) flag_analysis_ready is True, when the column exists (a warning is logged
    when it does not); (2) seclusion_instances is not missing, so an unknown outcome is
    never treated as "no seclusion"; (3) enrollment_total >= 30 (missing enrollment is
    dropped); (4) drop implausible staffing; (5) optionally drop the states in
    `exclude_states`.
    """
    report: dict[str, int] = {"input": len(frame)}
    kept = frame
    if "flag_analysis_ready" in kept.columns:
        kept = kept[_as_bool(kept["flag_analysis_ready"]).to_numpy()]
    else:
        LOGGER.warning("flag_analysis_ready column not found; relying on the other filters")
    report["analysis_ready"] = len(kept)
    kept = kept[_as_float(kept["seclusion_instances"]).notna().to_numpy()]
    report["outcome_present"] = len(kept)
    kept = kept[(_as_float(kept["enrollment_total"]) >= MIN_ENROLLMENT).to_numpy()]
    report[f"enrollment_ge_{MIN_ENROLLMENT}"] = len(kept)
    kept = kept[~implausible_staffing(kept).to_numpy()]
    report["plausible_staffing"] = len(kept)
    states = sorted({str(state).upper() for state in exclude_states or []})
    if states:
        kept = kept[~kept["lea_state"].astype("string").str.upper().isin(states).fillna(False)]
        report["after_exclude_states"] = len(kept)
    return kept.reset_index(drop=True), report


def make_target(frame: pd.DataFrame) -> pd.Series:
    """any_seclusion: 1 if seclusion_instances >= 1, else 0.

    Raises BaselineDataError if any seclusion_instances is missing: an unknown outcome must
    not be counted as "no seclusion". apply_modeling_filters removes those rows first.
    """
    instances = _as_float(frame["seclusion_instances"])
    missing = int(instances.isna().sum())
    if missing:
        raise BaselineDataError(
            f"{missing:,} rows have a missing seclusion_instances; "
            "run apply_modeling_filters first"
        )
    return (instances >= 1).astype(int).rename("any_seclusion")


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


class FeatureBuilder:
    """Build the baseline feature table.

    fit() learns from training rows only: the 99.5th percentile caps for psych_p100 and
    social_p100, and (with include_state) the list of training states. transform() can then
    be applied to any frame, so validation and test rows never influence the features.
    """

    def __init__(self, include_state: bool = False) -> None:
        self.include_state = include_state
        self.caps_: dict[str, float] | None = None
        self.states_: list[str] = []

    @property
    def is_fitted(self) -> bool:
        return self.caps_ is not None

    @property
    def feature_names(self) -> list[str]:
        if not self.is_fitted:
            raise RuntimeError("FeatureBuilder must be fitted before use; call fit(train) first")
        return [*BASE_FEATURES, *(f"{STATE_PREFIX}{state}" for state in self.states_)]

    def fit(self, train: pd.DataFrame) -> FeatureBuilder:
        caps = {}
        for feature, column in CAPPED_RATIOS.items():
            values = _per_100(train[column], train["enrollment_total"]).dropna()
            caps[feature] = (
                float(np.percentile(values, CAP_PERCENTILE)) if len(values) else float("inf")
            )
        self.caps_ = caps
        if self.include_state:
            states = train["lea_state"].dropna().astype(str).str.strip().str.upper()
            self.states_ = sorted(state for state in states.unique() if state)
        else:
            self.states_ = []
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self.is_fitted:
            raise RuntimeError("FeatureBuilder must be fitted before transform; call fit first")
        out = pd.DataFrame(index=frame.index)
        out["log_enrollment"] = np.log1p(_as_float(frame["enrollment_total"]).clip(lower=0))

        band = frame["grade_band"].astype("string").str.strip().str.lower()
        for name in GRADE_BANDS:
            out[f"gb_{name}"] = (band == name).fillna(False).astype(float)
        out["gb_na"] = (~band.isin(GRADE_BANDS)).fillna(True).astype(float)

        for feature, column in YES_NO_FEATURES.items():
            out[feature] = _yes_no(frame[column])
        for name in PERCENT_FEATURES:
            out[name] = _as_float(frame[name])
        for name in PERCENT_FEATURES:
            out[f"{name}_na"] = out[name].isna().astype(float)
        for feature, column in CAPPED_RATIOS.items():
            ratio = _per_100(frame[column], frame["enrollment_total"])
            out[feature] = ratio.clip(upper=self.caps_[feature])
        out["log_lea_enrollment"] = np.log1p(_as_float(frame["lea_enrollment"]).clip(lower=0))

        if self.include_state:
            state = frame["lea_state"].astype("string").str.strip().str.upper()
            for code in self.states_:
                out[f"{STATE_PREFIX}{code}"] = (state == code).fillna(False).astype(float)

        out = out[self.feature_names]
        banned = leak_or_id_columns(out.columns)
        assert not banned, f"Leak or ID columns in features: {banned}"
        return out
