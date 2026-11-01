"""Shared fixtures that read the real cleaned CRDC files in data/processed/.

The files are not in git. Tests that need them are skipped, not failed, when they are absent;
see docs/modeling/README_baseline.md for where to put them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
SAMPLE_DISTRICTS = 400


def real_file(code: str) -> Path:
    return REAL_DATA_DIR / code / f"schools_{code}_analysis.csv"


@pytest.fixture(scope="session")
def real_year():
    """Load a cleaned year (e.g. "201718") once per session, or skip if it is not here."""
    import baseline_features as bf

    cache: dict[str, pd.DataFrame] = {}

    def load(code: str) -> pd.DataFrame:
        if not real_file(code).is_file():
            pytest.skip(f"real data not found: {real_file(code)}")
        if code not in cache:
            cache[code] = bf.load_year(code, REAL_DATA_DIR)
        return cache[code].copy()

    return load


@pytest.fixture(scope="session")
def real_sample_dir(real_year, tmp_path_factory) -> Path:
    """The real 2017-18 and 2021-22 files cut to the same random districts, in the real layout.

    Small enough for a quick end-to-end run; sampling whole districts keeps GroupKFold, the
    returning and new schools, and the 2021-22 missing pct_504 / pct_el shift intact.
    """
    older, newer = real_year("201718"), real_year("202122")
    districts = np.random.default_rng(0).choice(
        sorted(set(older["leaid"]) & set(newer["leaid"])), SAMPLE_DISTRICTS, replace=False
    )
    out = tmp_path_factory.mktemp("real_sample")
    for code, frame in (("201718", older), ("202122", newer)):
        (out / code).mkdir()
        frame[frame["leaid"].isin(districts)].to_csv(
            out / code / real_file(code).name, index=False
        )
    return out
