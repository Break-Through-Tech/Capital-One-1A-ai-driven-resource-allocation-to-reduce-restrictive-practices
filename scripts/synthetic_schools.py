#!/usr/bin/env python
"""Make fake CRDC school years in the team's 50-column format (AI_CONTEXT A4).

The numbers are invented. They exist only so the baseline pipeline and its tests can run
before the real cleaned files are on this machine. Never report results computed on them.

Run it from the repository root to write one fake year to a folder:

    python scripts/synthetic_schools.py --year 201718 --n-schools 5000 --out-dir /tmp/fake

What the fake data contains, so the pipeline has something to find and to filter:

    - about 7% of schools with any seclusion, driven by a known signal: pct_idea, special-
      education status, grade band, charter status, size and a state effect;
    - missing pct_504 / pct_el, much more often in 2020-21 and 2021-22 than in older years
      (the real coding shift, data_issues_202122.csv #2), a few tiny schools (under 30
      students) and a few schools with impossible staffing;
    - about 2.5% of rows with no seclusion data (flag_analysis_ready False), so the first
      modeling filter has something to drop;
    - several states, and districts with several schools;
    - with the same seed, about 85% of combokeys appear in every year.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("synthetic_schools")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

# Same order as scripts/clean_202122.py OUTPUT_COLUMNS (AI_CONTEXT A4).
OUTPUT_COLUMNS = [
    "year", "combokey", "leaid", "schid", "lea_state", "sch_name", "lea_name", "jj",
    "seclusion_instances_wodis", "seclusion_instances_idea", "seclusion_instances_504",
    "seclusion_instances", "enrollment_total", "enr_nonbinary", "enr_idea", "enr_504",
    "enr_el", "seclusion_rate", "sch_status_sped", "sch_status_charter", "sch_status_alt",
    "sch_status_magnet", "sch_virt_ind", "grade_band", "fte_teachers", "fte_counselors",
    "fte_nurses", "fte_psych", "fte_social", "fte_leo", "fte_guards", "counselors_per_100",
    "teachers_per_100", "support_fte_per_100", "pct_idea", "pct_504", "pct_el",
    "lea_enrollment", "lea_schools", "flag_missing_seclusion", "flag_missing_enrollment",
    "flag_small_enrollment", "flag_fte_outlier", "flag_partial_enrollment",
    "flag_partial_idea", "flag_partial_504", "flag_partial_el", "flag_missing_module",
    "flag_missing_lea", "flag_analysis_ready",
]  # fmt: skip

# State code -> (FIPS prefix for leaid, effect on the log-odds of any seclusion).
STATES = {
    "AL": ("01", 0.3),
    "CA": ("06", -1.0),
    "GA": ("13", -0.8),
    "IA": ("19", 0.9),
    "NY": ("36", -0.6),
    "OH": ("39", 0.6),
    "PA": ("42", 0.2),
    "TX": ("48", -1.1),
    "WI": ("55", 0.8),
    "HI": ("15", -3.0),
}
GRADE_BAND_SHARES = {"elementary": 0.52, "middle": 0.17, "high": 0.18, "span": 0.11, "other": 0.02}
GRADE_BAND_EFFECT = {"elementary": 0.5, "middle": 0.1, "high": -0.6, "span": 0.0, "other": -0.3}
INTERCEPT = -3.55
# Share of rows with missing enr_504 / enr_el per year. Real CRDC: under 0.3% in 2017-18,
# 22.6% / 18.8% in 2021-22 (data_issues_202122.csv #2). The 2015-16 and 2020-21 rates are
# guesses that copy the nearest known year.
MISSING_504_EL = {
    "201516": (0.005, 0.005),
    "201718": (0.005, 0.005),
    "202021": (0.226, 0.188),
    "202122": (0.226, 0.188),
}
MISSING_SECLUSION_SHARE = 0.025  # rows that fail flag_analysis_ready
SHARED_SHARE = 0.85  # share of each year's schools taken from the shared core
SCHOOLS_PER_DISTRICT = 6


def year_label(code: str) -> str:
    """'201718' -> '2017-18'."""
    return f"{code[:4]}-{code[4:]}"


# ---------------------------------------------------------------------------
# School pool (stable across years for one seed)
# ---------------------------------------------------------------------------


def _school_pool(n_schools: int, seed: int) -> pd.DataFrame:
    """Stable school attributes. The first SHARED_SHARE * n_schools rows appear every year."""
    rng = np.random.default_rng(seed)
    core = int(round(SHARED_SHARE * n_schools))
    size = core + 4 * (n_schools - core) + 1
    n_districts = max(size // SCHOOLS_PER_DISTRICT, 4)
    state_codes = np.array(list(STATES))
    district_state = rng.choice(state_codes, size=n_districts)
    district = rng.integers(0, n_districts, size=size)
    state = district_state[district]
    fips = np.array([STATES[code][0] for code in state])
    leaid = np.char.add(fips, np.char.zfill((district + 1).astype(str), 5))
    schid = np.char.zfill((np.arange(size) + 1).astype(str), 5)
    bands = rng.choice(
        list(GRADE_BAND_SHARES), size=size, p=list(GRADE_BAND_SHARES.values())
    ).astype(object)
    bands[rng.random(size) < 0.01] = None
    return pd.DataFrame(
        {
            "leaid": leaid,
            "schid": schid,
            "combokey": np.char.add(leaid, schid),
            "lea_state": state,
            "district": district,
            "grade_band": bands,
            "base_enrollment": np.exp(rng.normal(6.1, 0.7, size=size)),
            "sped": rng.random(size) < 0.03,
            "alt": rng.random(size) < 0.04,
            "charter": rng.random(size) < 0.07,
            "jj": rng.random(size) < 0.01,
            "magnet": rng.random(size) < 0.03,
            "idea_share": rng.beta(2.5, 15, size=size),
            "core": np.arange(size) < core,
        }
    )


def _select_year(pool: pd.DataFrame, n_schools: int, rng: np.random.Generator) -> pd.DataFrame:
    """The shared core plus a year-specific random draw from the rest of the pool."""
    extra_pool = pool.index[~pool["core"]]
    n_extra = n_schools - int(pool["core"].sum())
    extra = rng.choice(extra_pool, size=n_extra, replace=False) if n_extra > 0 else []
    chosen = pool.loc[pool["core"]].index.append(pd.Index(extra))
    return pool.loc[chosen].reset_index(drop=True)


# ---------------------------------------------------------------------------
# One year
# ---------------------------------------------------------------------------


def make_synthetic_year(code: str, n_schools: int = 5000, seed: int = 42) -> pd.DataFrame:
    """One fake school year in the 50-column team format. Deterministic for (code, seed)."""
    pool = _school_pool(n_schools, seed)
    rng = np.random.default_rng([seed, int(code)])
    frame = _select_year(pool, n_schools, rng)
    n = len(frame)

    # Size: stable per school, with yearly noise; about 3% tiny schools (under 30).
    enrollment = np.round(frame["base_enrollment"].to_numpy() * np.exp(rng.normal(0, 0.08, n)))
    tiny = rng.random(n) < 0.03
    enrollment[tiny] = rng.integers(3, 30, size=tiny.sum())
    enrollment = np.maximum(enrollment, 1.0)

    idea_share = np.clip(frame["idea_share"] + rng.normal(0, 0.01, n), 0, 1)
    idea_share = np.where(frame["sped"], np.clip(idea_share + 0.6, 0, 1), idea_share)
    enr_idea = np.round(enrollment * idea_share)
    enr_504 = np.round(enrollment * rng.beta(2, 60, n))
    enr_el = np.round(enrollment * rng.beta(1.2, 10, n))
    missing_504, missing_el = MISSING_504_EL.get(code, (0.15, 0.12))
    enr_504[rng.random(n) < missing_504] = np.nan
    enr_el[rng.random(n) < missing_el] = np.nan
    enr_idea[rng.random(n) < 0.03] = np.nan

    fte = {
        "fte_teachers": np.round(enrollment / rng.uniform(12, 20, n), 1),
        "fte_counselors": np.round(enrollment / rng.uniform(300, 600, n), 2),
        "fte_nurses": np.round(enrollment / rng.uniform(400, 1000, n), 2),
        "fte_psych": np.round(rng.gamma(2.0, 0.15, n) * enrollment / 500, 2),
        "fte_social": np.round(rng.gamma(1.5, 0.2, n) * enrollment / 500, 2),
        "fte_leo": np.round(rng.binomial(1, 0.3, n) * rng.uniform(0.2, 1.5, n), 1),
        "fte_guards": np.round(rng.binomial(1, 0.2, n) * rng.uniform(0.5, 3.0, n), 1),
    }
    for name in ("fte_nurses", "fte_psych", "fte_social"):
        fte[name][rng.random(n) < 0.02] = np.nan
    bad_rows = rng.choice(n, size=max(n // 200, 3), replace=False)
    fte["fte_leo"][bad_rows] = 100.0  # implausible: more officers than students, mostly
    fte["fte_teachers"][bad_rows[::2]] = enrollment[bad_rows[::2]] * 3

    # Known signal for "any seclusion".
    pct_idea = 100 * enr_idea / enrollment
    state_effect = frame["lea_state"].map(lambda code: STATES[code][1]).to_numpy()
    band_effect = frame["grade_band"].map(GRADE_BAND_EFFECT).fillna(0.0).to_numpy()
    logit = (
        INTERCEPT
        + 0.07 * (np.nan_to_num(pct_idea, nan=13.0) - 13.0)
        + 1.3 * frame["sped"].to_numpy()
        - 1.0 * frame["charter"].to_numpy()
        + 0.6 * frame["alt"].to_numpy()
        + band_effect
        + state_effect
        + 0.4 * (np.log(enrollment) - 6.1)
        + rng.normal(0, 0.3, n)
    )
    positive = rng.random(n) < 1 / (1 + np.exp(-logit))
    instances = np.where(positive, 1 + rng.poisson(4, n), 0).astype(float)
    sec_idea = np.round(instances * rng.uniform(0.6, 1.0, n))
    sec_504 = np.minimum(np.round(instances * rng.uniform(0, 0.1, n)), instances - sec_idea)
    sec_wodis = instances - sec_idea - sec_504
    no_seclusion_data = rng.random(n) < MISSING_SECLUSION_SHARE
    for values in (instances, sec_idea, sec_504, sec_wodis):
        values[no_seclusion_data] = np.nan

    def yes_no(mask: np.ndarray) -> np.ndarray:
        return np.where(mask, "Yes", "No").astype(object)

    district_size = frame.groupby("leaid")["leaid"].transform("size").to_numpy()
    lea_enrollment = np.round(enrollment * district_size * rng.uniform(1.0, 1.5, n))

    def per_100(values: np.ndarray) -> np.ndarray:
        return 100 * values / enrollment

    support = fte["fte_nurses"] + fte["fte_psych"] + fte["fte_social"]
    false = np.zeros(n, dtype=bool)
    out = pd.DataFrame(
        {
            "year": year_label(code),
            "combokey": frame["combokey"],
            "leaid": frame["leaid"],
            "schid": frame["schid"],
            "lea_state": frame["lea_state"],
            "sch_name": "Synthetic School " + frame["schid"],
            "lea_name": "Synthetic District " + frame["leaid"],
            "jj": yes_no(frame["jj"].to_numpy()),
            "seclusion_instances_wodis": sec_wodis,
            "seclusion_instances_idea": sec_idea,
            "seclusion_instances_504": sec_504,
            "seclusion_instances": instances,
            "enrollment_total": enrollment.astype(float),
            "enr_nonbinary": np.nan,
            "enr_idea": enr_idea,
            "enr_504": enr_504,
            "enr_el": enr_el,
            "seclusion_rate": per_100(instances),
            "sch_status_sped": yes_no(frame["sped"].to_numpy()),
            "sch_status_charter": yes_no(frame["charter"].to_numpy()),
            "sch_status_alt": yes_no(frame["alt"].to_numpy()),
            "sch_status_magnet": yes_no(frame["magnet"].to_numpy()),
            "sch_virt_ind": "No",
            "grade_band": frame["grade_band"],
            **fte,
            "counselors_per_100": per_100(fte["fte_counselors"]),
            "teachers_per_100": per_100(fte["fte_teachers"]),
            "support_fte_per_100": per_100(support),
            "pct_idea": pct_idea,
            "pct_504": 100 * enr_504 / enrollment,
            "pct_el": 100 * enr_el / enrollment,
            "lea_enrollment": lea_enrollment,
            "lea_schools": district_size.astype(float),
            "flag_missing_seclusion": no_seclusion_data,
            "flag_missing_enrollment": false,
            "flag_small_enrollment": enrollment < 10,
            "flag_fte_outlier": false,
            "flag_partial_enrollment": false,
            "flag_partial_idea": false,
            "flag_partial_504": false,
            "flag_partial_el": false,
            "flag_missing_module": false,
            "flag_missing_lea": false,
            "flag_analysis_ready": ~no_seclusion_data,
        }
    )
    out = out[OUTPUT_COLUMNS].sort_values("combokey", kind="stable").reset_index(drop=True)
    return out


def write_synthetic_year(
    code: str, out_dir: Path, n_schools: int = 5000, seed: int = 42
) -> Path:
    """Write one fake year as {out_dir}/{code}/schools_{code}_analysis.csv."""
    path = Path(out_dir) / code / f"schools_{code}_analysis.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    make_synthetic_year(code, n_schools, seed).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write one fake CRDC year (for testing only).")
    parser.add_argument("--year", required=True, help="year code, for example 201718")
    parser.add_argument("--n-schools", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    path = write_synthetic_year(args.year, args.out_dir, args.n_schools, args.seed)
    LOGGER.warning("Wrote SYNTHETIC data (not real CRDC) to %s", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
