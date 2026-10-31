"""Tests for scripts/baseline_features.py.

Unit tests use tiny hand-built frames, so every expected value can be checked by eye.
"""

from __future__ import annotations

from pathlib import Path

import baseline_features as bf
import numpy as np
import pandas as pd
import pytest
import synthetic_schools


def school(**overrides) -> dict:
    """One plausible school row with every column the pipeline reads."""
    row = {
        "year": "2017-18",
        "combokey": "010000100001",
        "leaid": "0100001",
        "schid": "00001",
        "lea_state": "AL",
        "sch_name": "A",
        "lea_name": "D",
        "jj": "No",
        "seclusion_instances_wodis": 0.0,
        "seclusion_instances_idea": 0.0,
        "seclusion_instances_504": 0.0,
        "seclusion_instances": 0.0,
        "seclusion_rate": 0.0,
        "enrollment_total": 500.0,
        "sch_status_sped": "No",
        "sch_status_charter": "No",
        "sch_status_alt": "No",
        "sch_status_magnet": "No",
        "grade_band": "elementary",
        "fte_teachers": 30.0,
        "fte_counselors": 1.0,
        "fte_nurses": 1.0,
        "fte_psych": 0.5,
        "fte_social": 0.5,
        "fte_leo": 0.0,
        "fte_guards": 0.0,
        "pct_idea": 12.0,
        "pct_504": 2.0,
        "pct_el": 5.0,
        "lea_enrollment": 10000.0,
        "flag_missing_seclusion": False,
        "flag_analysis_ready": True,
    }
    row.update(overrides)
    return row


def frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_filter_drops_not_analysis_ready():
    data = frame(school(), school(flag_analysis_ready=False))
    kept, report = bf.apply_modeling_filters(data)
    assert len(kept) == 1
    assert report["input"] == 2 and report["analysis_ready"] == 1


def test_filter_accepts_text_flags_and_missing_flag_column():
    text_flags = frame(school(flag_analysis_ready="True"), school(flag_analysis_ready="False"))
    assert len(bf.apply_modeling_filters(text_flags)[0]) == 1
    no_flag = frame(school(), school()).drop(columns="flag_analysis_ready")
    kept, report = bf.apply_modeling_filters(no_flag)
    assert len(kept) == 2 and report["analysis_ready"] == 2


def test_filter_drops_missing_outcome_even_without_flag_column():
    data = frame(school(), school(seclusion_instances=np.nan)).drop(columns="flag_analysis_ready")
    kept, report = bf.apply_modeling_filters(data)
    assert len(kept) == 1 and kept["seclusion_instances"].notna().all()
    assert report["analysis_ready"] == 2 and report["outcome_present"] == 1


def test_make_target_rejects_missing_outcome():
    data = frame(school(seclusion_instances=2.0), school(seclusion_instances=np.nan))
    with pytest.raises(bf.BaselineDataError, match="seclusion_instances"):
        bf.make_target(data)


def test_filter_enrollment_at_least_30():
    data = frame(
        school(enrollment_total=29.0, fte_teachers=2.0, fte_psych=0.0, fte_social=0.0),
        school(enrollment_total=30.0, fte_teachers=2.0, fte_psych=0.0, fte_social=0.0),
        school(enrollment_total=np.nan),
    )
    kept, report = bf.apply_modeling_filters(data)
    assert kept["enrollment_total"].tolist() == [30.0]
    assert report["enrollment_ge_30"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"fte_leo": 600.0},  # FTE above enrollment
        {"fte_guards": 501.0},
        {"fte_counselors": 60.0, "fte_nurses": 41.0},  # support 20.2 per 100 (+1 psych/social)
        {"fte_teachers": 251.0},  # teachers 50.2 per 100
    ],
)
def test_filter_drops_implausible_staffing(overrides):
    kept, report = bf.apply_modeling_filters(frame(school(), school(**overrides)))
    assert len(kept) == 1
    assert report["plausible_staffing"] == 1


def test_filter_support_sum_treats_nan_as_zero():
    # counselors 99 + nurses NaN + psych 0.5 + social 0.5 = 100 FTE -> 20 per 100: kept.
    at_limit = school(fte_counselors=99.0, fte_nurses=np.nan)
    # 101 FTE -> 20.2 per 100: dropped even though nurses is missing.
    over = school(fte_counselors=100.0, fte_nurses=np.nan)
    kept, _ = bf.apply_modeling_filters(frame(at_limit, over))
    assert kept["fte_counselors"].tolist() == [99.0]


def test_filter_nan_staffing_never_drops():
    all_nan = {name: np.nan for name in bf.FTE_COLUMNS}
    kept, report = bf.apply_modeling_filters(frame(school(**all_nan), school()))
    assert len(kept) == 2 and report["plausible_staffing"] == 2


def test_filter_exclude_states():
    data = frame(school(lea_state="HI"), school(lea_state="AL"), school(lea_state="PR"))
    kept, report = bf.apply_modeling_filters(data, exclude_states=["hi", "PR"])
    assert kept["lea_state"].tolist() == ["AL"]
    assert report["after_exclude_states"] == 1
    assert "after_exclude_states" not in bf.apply_modeling_filters(data)[1]


def test_make_target():
    data = frame(*(school(seclusion_instances=v) for v in [0.0, 1.0, 37.0, 0.5]))
    target = bf.make_target(data)
    assert target.tolist() == [0, 1, 1, 0]
    assert target.dtype.kind == "i"


# ---------------------------------------------------------------------------
# FeatureBuilder
# ---------------------------------------------------------------------------


def test_transform_before_fit_raises():
    with pytest.raises(RuntimeError, match="fit"):
        bf.FeatureBuilder().transform(frame(school()))


def test_caps_learned_from_train_only():
    train = frame(*(school(fte_psych=float(i) / 10) for i in range(1, 101)))
    builder = bf.FeatureBuilder().fit(train)
    expected_cap = np.percentile(100 * np.arange(1, 101) / 10 / 500, 99.5)
    assert builder.caps_["psych_p100"] == pytest.approx(expected_cap)

    test = frame(school(fte_psych=400.0, fte_social=400.0), school(fte_psych=0.5))
    features = builder.transform(test)
    assert features["psych_p100"].iloc[0] == pytest.approx(expected_cap)
    assert features["social_p100"].iloc[0] == pytest.approx(builder.caps_["social_p100"])
    assert features["psych_p100"].iloc[1] == pytest.approx(0.1)
    # Refitting on the extreme frame would give a different cap: the test rows were not used.
    assert bf.FeatureBuilder().fit(test).caps_["psych_p100"] > expected_cap


def test_state_one_hots_and_unseen_state():
    builder = bf.FeatureBuilder(include_state=True).fit(
        frame(school(lea_state="AL"), school(lea_state="ca"), school(lea_state=np.nan))
    )
    assert builder.states_ == ["AL", "CA"]
    features = builder.transform(frame(school(lea_state="CA"), school(lea_state="TX")))
    assert features[["st_AL", "st_CA"]].to_numpy().tolist() == [[0, 1], [0, 0]]
    assert "st_TX" not in features.columns


def test_fixed_column_order_and_no_leaks():
    data = frame(school(), school(grade_band=np.nan, sch_status_sped="Yes", pct_504=np.nan))
    plain = bf.FeatureBuilder().fit(data).transform(data)
    assert list(plain.columns) == list(bf.BASE_FEATURES)
    with_state = bf.FeatureBuilder(include_state=True).fit(data).transform(data)
    assert list(with_state.columns) == [*bf.BASE_FEATURES, "st_AL"]
    shuffled = bf.FeatureBuilder().fit(data).transform(data[data.columns[::-1]])
    assert list(shuffled.columns) == list(bf.BASE_FEATURES)
    for columns in (plain.columns, with_state.columns):
        assert bf.leak_or_id_columns(columns) == []
        assert not any(name.startswith("seclusion_") for name in columns)
    assert all(dtype.kind == "f" for dtype in plain.dtypes)


def test_feature_values():
    data = frame(
        school(),
        school(grade_band=np.nan, sch_status_sped="Yes", pct_504=np.nan, jj="Maybe"),
    )
    features = bf.FeatureBuilder().fit(data).transform(data)
    assert features["log_enrollment"].iloc[0] == pytest.approx(np.log1p(500))
    assert features["gb_elementary"].tolist() == [1.0, 0.0]
    assert features["gb_na"].tolist() == [0.0, 1.0]
    assert features["is_sped"].tolist() == [0.0, 1.0]
    assert features["is_jj"].iloc[0] == 0.0 and np.isnan(features["is_jj"].iloc[1])
    assert features["pct_504_na"].tolist() == [0.0, 1.0]
    assert np.isnan(features["pct_504"].iloc[1])
    assert features["log_lea_enrollment"].iloc[0] == pytest.approx(np.log1p(10000))


def test_leak_check_catches_any_seclusion_prefix():
    assert bf.leak_or_id_columns(["pct_idea", "seclusion_new", "leaid", "year"]) == [
        "seclusion_new",
        "leaid",
        "year",
    ]


# ---------------------------------------------------------------------------
# load_year
# ---------------------------------------------------------------------------


def test_load_year_missing_file_message(tmp_path: Path):
    with pytest.raises(bf.BaselineDataError) as error:
        bf.load_year("201718", tmp_path)
    message = str(error.value)
    assert str(tmp_path / "201718" / "schools_201718_analysis.csv") in message
    assert str(tmp_path / "schools_201718_analysis.csv") in message


def test_load_year_reads_ids_as_text(tmp_path: Path):
    data = synthetic_schools.make_synthetic_year("201718", n_schools=200, seed=1)
    path = tmp_path / "schools_201718_analysis.csv"  # flat fallback location
    data.to_csv(path, index=False)
    loaded = bf.load_year("201718", tmp_path)
    for column in ("combokey", "leaid", "schid"):
        assert loaded[column].map(type).eq(str).all()
    assert loaded["leaid"].str.len().eq(7).all()
    assert loaded["combokey"].str.startswith("0").any()  # leading zeros kept
    assert loaded["combokey"].tolist() == data["combokey"].tolist()


def test_load_year_missing_column(tmp_path: Path):
    data = synthetic_schools.make_synthetic_year("202122", n_schools=50, seed=1)
    (tmp_path / "202122").mkdir()
    data.drop(columns="pct_el").to_csv(tmp_path / "202122" / "schools_202122_analysis.csv")
    with pytest.raises(bf.BaselineDataError, match="pct_el"):
        bf.load_year("202122", tmp_path)


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


def test_synthetic_year_shape_and_overlap():
    first = synthetic_schools.make_synthetic_year("201718", n_schools=1000, seed=7)
    again = synthetic_schools.make_synthetic_year("201718", n_schools=1000, seed=7)
    later = synthetic_schools.make_synthetic_year("202122", n_schools=1000, seed=7)
    pd.testing.assert_frame_equal(first, again)
    assert list(first.columns) == synthetic_schools.OUTPUT_COLUMNS and first.shape[1] == 50
    assert (first["combokey"] == first["leaid"] + first["schid"]).all()
    assert 0.03 < bf.make_target(bf.apply_modeling_filters(first)[0]).mean() < 0.12
    shared = len(set(first["combokey"]) & set(later["combokey"])) / len(first)
    assert 0.8 < shared < 0.95
    assert first["pct_504"].isna().any() and (first["enrollment_total"] < 30).any()
    assert first["leaid"].value_counts().max() > 1 and first["lea_state"].nunique() > 3


def test_synthetic_missing_coding_shift_and_unready_rows():
    older = synthetic_schools.make_synthetic_year("201718", n_schools=2000, seed=3)
    newer = synthetic_schools.make_synthetic_year("202122", n_schools=2000, seed=3)
    assert older["pct_504"].isna().mean() < 0.02 and older["pct_el"].isna().mean() < 0.02
    assert newer["pct_504"].isna().mean() > 0.18 and newer["pct_el"].isna().mean() > 0.14
    for data in (older, newer):
        unready = ~data["flag_analysis_ready"]
        assert 0.01 < unready.mean() < 0.05
        assert data.loc[unready, "seclusion_instances"].isna().all()
        assert data.loc[unready, "flag_missing_seclusion"].all()
        assert data.loc[~unready, "seclusion_instances"].notna().all()
