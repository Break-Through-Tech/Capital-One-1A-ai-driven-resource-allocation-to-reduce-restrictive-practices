"""Tests for scripts/train_baseline.py: metrics, folds and one end-to-end run.

The fold and end-to-end tests use the real cleaned files (see conftest.py) and skip when
they are absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import baseline_features as bf
import pytest
import train_baseline as tb
from sklearn.base import clone

OUTPUT_FILES = (
    "metrics_cv.csv",
    "metrics_summary.csv",
    "metrics_test_new_schools.csv",
    "metrics_test_by_missing_504_el.csv",
    "calibration_test.csv",
    "coefficients_M1.csv",
    "filter_report.json",
    "run_info.json",
)


def test_recall_at_top10_hand_checked():
    # 20 rows -> top ceil(2.0) = 2 scores. Positives at rows 0, 5, 9 (3 in all).
    # The two highest scores are rows 5 (0.99) and 3 (0.95): 1 of 3 positives captured.
    y_true = np.zeros(20, dtype=int)
    y_true[[0, 5, 9]] = 1
    scores = np.linspace(0.0, 0.5, 20)
    scores[5], scores[3] = 0.99, 0.95
    assert tb.recall_at_top(y_true, scores) == pytest.approx(1 / 3)
    # 21 rows -> ceil(2.1) = 3 rows, so the next-highest (row 20, a positive) also counts.
    y_true21 = np.append(y_true, 1)
    scores21 = np.append(scores, 0.9)
    assert tb.recall_at_top(y_true21, scores21) == pytest.approx(2 / 4)
    assert tb.compute_metrics(y_true, scores)["recall_at_top10"] == pytest.approx(1 / 3)


def test_recall_at_top10_constant_score_is_no_skill():
    # Positives packed at the front: a row-order tie-break would give 1.0 here.
    y_true = np.zeros(1000, dtype=int)
    y_true[:80] = 1
    assert tb.recall_at_top(y_true, np.full(1000, 0.08)) == pytest.approx(0.10)
    assert tb.recall_at_top(y_true[::-1], np.full(1000, 0.08)) == pytest.approx(0.10)


def test_recall_at_top10_partial_ties_at_cutoff():
    # 20 rows -> k = 2: one clear top row (negative) and 4 rows tied at 0.5 (2 positive)
    # for the last slot -> expected positives found = 2 * 1/4 = 0.5 of 2 positives.
    y_true = np.zeros(20, dtype=int)
    y_true[[1, 2]] = 1
    scores = np.zeros(20)
    scores[0] = 0.9
    scores[[1, 2, 3, 4]] = 0.5
    assert tb.recall_at_top(y_true, scores) == pytest.approx(0.25)


def test_recall_at_top10_no_positives_is_nan():
    assert np.isnan(tb.recall_at_top(np.zeros(5, dtype=int), np.arange(5)))


def test_dummy_model_scores():
    rng = np.random.default_rng(0)
    y = (rng.random(1000) < 0.08).astype(int)
    features = pd.DataFrame({"x": rng.random(1000)})
    m0 = next(spec for spec in tb.build_models(fast=True) if spec.model_id == "M0")
    scores = m0.estimator.fit(features, y).predict_proba(features)[:, 1]
    metrics = tb.compute_metrics(y, scores)
    assert metrics["roc_auc"] == pytest.approx(0.5)
    assert metrics["pr_auc"] == pytest.approx(y.mean())
    assert metrics["pr_auc_lift"] == pytest.approx(1.0)
    assert metrics["recall_at_top10"] == pytest.approx(0.10)
    assert metrics["positive_rate"] == pytest.approx(y.mean())
    assert metrics["n"] == 1000 and metrics["positives"] == y.sum()


def test_calibration_table_bins():
    table = tb.calibration_table([0, 1, 1, 0], [0.05, 0.15, 0.19, 1.0])
    assert len(table) == 10 and table["count"].sum() == 4
    assert table.loc[1, "count"] == 2 and table.loc[1, "observed_rate"] == 1.0
    assert table.loc[9, "count"] == 1  # p = 1.0 goes in the last bin
    assert np.isnan(table.loc[5, "mean_predicted"])


def test_group_folds_keep_districts_apart():
    groups = pd.Series(np.repeat([f"{i:07d}" for i in range(23)], 7))
    folds = tb.group_folds(groups, 5)
    assert len(folds) == 5
    seen_valid = []
    for fit_idx, valid_idx in folds:
        assert not set(groups.iloc[fit_idx]) & set(groups.iloc[valid_idx])
        seen_valid.extend(valid_idx)
    assert sorted(seen_valid) == list(range(len(groups)))
    assert [v.tolist() for _, v in tb.group_folds(groups, 5)] == [v.tolist() for _, v in folds]


def test_group_folds_too_few_districts():
    with pytest.raises(ValueError, match="districts"):
        tb.group_folds(pd.Series(["a", "a", "b"]), 5)


def test_group_folds_missing_leaid_names_the_problem():
    groups = pd.Series(["a", "b", "c", "d", "e", "f", np.nan, np.nan, None])
    with pytest.raises(bf.BaselineDataError, match="3 training rows have a missing leaid"):
        tb.group_folds(groups, 5)


def test_boosting_rounds_fixed_above_early_stopping_threshold():
    # sklearn's early_stopping="auto" switches on above 10,000 rows; it must stay off.
    rng = np.random.default_rng(0)
    features = pd.DataFrame({"x": rng.random(10_500), "z": rng.random(10_500)})
    y = (rng.random(10_500) < features["x"] * 0.3).astype(int)
    for spec in tb.build_models(fast=True):
        if spec.model_id in ("M4", "M5"):
            hgb = clone(spec.estimator).fit(features, y).named_steps["model"]
            assert hgb.do_early_stopping_ is False
            assert hgb.n_iter_ == hgb.max_iter


def test_cross_validate_refits_builder_per_fold_on_same_folds(monkeypatch, real_year):
    data = real_year("201718").sample(400, random_state=1)
    frame, _ = bf.apply_modeling_filters(data)
    frame = frame.assign(row_id=np.arange(len(frame)))
    train = tb.YearData(frame, bf.make_target(frame), {})
    folds = tb.group_folds(frame["leaid"], 5)
    specs = [s for s in tb.build_models(fast=True) if s.model_id in ("M0", "M1", "M2")]

    fitted_on: list[list[int]] = []
    original_fit = bf.FeatureBuilder.fit

    def recording_fit(self, rows):
        fitted_on.append(sorted(rows["row_id"].tolist()))
        return original_fit(self, rows)

    monkeypatch.setattr(bf.FeatureBuilder, "fit", recording_fit)
    cv = tb.cross_validate(specs, train, folds)

    assert len(cv) == len(specs) * len(folds)
    assert len(fitted_on) == len(specs) * len(folds)
    for model_index in range(len(specs)):
        for fold, (fit_idx, valid_idx) in enumerate(folds):
            rows = fitted_on[model_index * len(folds) + fold]
            assert rows == sorted(fit_idx.tolist())
            assert not set(rows) & set(valid_idx.tolist())
    per_model = [fitted_on[i * len(folds) : (i + 1) * len(folds)] for i in range(len(specs))]
    assert all(calls == per_model[0] for calls in per_model)


def test_missing_real_data_exits_with_message(tmp_path: Path, caplog):
    code = tb.main(["--data-dir", str(tmp_path), "--out-dir", str(tmp_path / "out")])
    assert code == 1
    assert "schools_201718_analysis.csv" in caplog.text
    assert not (tmp_path / "out").exists()


def test_end_to_end_real_sample(tmp_path: Path, real_sample_dir: Path):
    out_dir = tmp_path / "out"
    model_dir = tmp_path / "models"
    code = tb.main(
        [
            "--data-dir",
            str(real_sample_dir),
            "--fast",
            "--out-dir",
            str(out_dir),
            "--model-dir",
            str(model_dir),
        ]
    )
    assert code == 0
    for name in OUTPUT_FILES:
        assert (out_dir / name).is_file(), name
    for model_id in ("M0", "M1", "M2", "M3", "M4", "M5"):
        assert (model_dir / f"{model_id}.joblib").is_file()

    info = json.loads((out_dir / "run_info.json").read_text())
    assert info["train_years"] == ["201718"] and info["test_year"] == "202122"
    assert info["cv_folds"] == 5
    assert any(name.startswith("st_") for name in info["features"]["M2"])
    assert not any(name.startswith("st_") for name in info["features"]["M1"])
    assert set(info["versions"]) == {"python", "pandas", "numpy", "sklearn"}
    # 2021-22 leaves pct_504 / pct_el blank far more often than 2017-18.
    assert info["test_rows_504_or_el_missing"] / info["test_rows"] > 0.2
    assert info["train_rows_504_or_el_missing"] / info["train_rows"] < 0.05

    filters = json.loads((out_dir / "filter_report.json").read_text())
    for code in ("201718", "202122"):
        assert filters[code]["analysis_ready"] <= filters[code]["input"]

    summary = pd.read_csv(out_dir / "metrics_summary.csv")
    test_pr = summary[summary["metric"] == "pr_auc"].set_index("model")["test"]
    assert test_pr.drop("M0").max() > test_pr["M0"] + 0.05
    cv = pd.read_csv(out_dir / "metrics_cv.csv")
    assert len(cv) == 6 * 5
    calibration = pd.read_csv(out_dir / "calibration_test.csv")
    assert len(calibration) == 6 * 10
    assert calibration.groupby("model")["count"].sum().eq(info["test_rows"]).all()
    new = pd.read_csv(out_dir / "metrics_test_new_schools.csv")
    assert new["n"].eq(info["test_new_school_rows"]).all() and (new["n"] > 0).all()
    by_missing = pd.read_csv(out_dir / "metrics_test_by_missing_504_el.csv")
    assert len(by_missing) == 6 * 2
    assert by_missing.groupby("model")["n"].sum().eq(info["test_rows"]).all()
    m0 = summary[(summary["model"] == "M0") & (summary["metric"] == "recall_at_top10")]
    assert m0["test"].iloc[0] == pytest.approx(0.10, abs=0.01)
