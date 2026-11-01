#!/usr/bin/env python
"""Train and evaluate the baseline models for "did this school report any seclusion?".

Run it from the repository root, with the cleaned files in
data/processed/{code}/schools_{code}_analysis.csv:

    python scripts/train_baseline.py --train-years 201718 --test-year 202122

What it does, top to bottom:

    1. Load the training years and the test year, apply the modeling filters
       (baseline_features.apply_modeling_filters) and build the target any_seclusion.
    2. Cross-validate six fixed models on the training years with 5-fold GroupKFold grouped by
       district (leaid). The folds are computed once and reused for every model, and the
       feature caps are re-learned inside each fold from the fold's training rows only.
    3. Refit every model on all training rows and score the test year once.
    4. Write the metric tables, calibration table, M1 coefficients, filter report and run
       info to --out-dir, and the fitted (FeatureBuilder, model) pairs to --model-dir.

No class weights are used: the models then predict calibrated probabilities, and the
comparison uses ranking metrics (PR-AUC, ROC-AUC, recall in the top 10%) that do not depend
on a cutoff. Hyperparameters are fixed this round; there is no tuning.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import baseline_features as bf
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

LOGGER = logging.getLogger("train_baseline")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "baseline"
DEFAULT_MODEL_DIR = REPO_ROOT / "models" / "baseline"
DEFAULT_TRAIN_YEARS = ("201718",)
DEFAULT_TEST_YEAR = "202122"
DEFAULT_CV_FOLDS = 5
DEFAULT_SEED = 42

TOP_SHARE = 0.10
CALIBRATION_BINS = 10
DROP_METRICS = ("pr_auc", "pr_auc_lift", "roc_auc")
METRIC_NAMES = (
    "pr_auc",
    "pr_auc_lift",
    "roc_auc",
    "recall_at_top10",
    "brier",
    "n",
    "positives",
    "positive_rate",
)
# Test-year subsets by whether pct_504 or pct_el is missing. These are far more often missing
# in 2021-22 than in 2017-18 (data_issues_202122.csv #2), so the test score mixes that coding
# shift with any real change; scoring the two groups apart shows how much.
MISSING_SUBSET_COLUMNS = ("pct_504", "pct_el")

@dataclass(frozen=True)
class ModelSpec:
    """One baseline model: an ID, a short description, state on/off and an estimator."""

    model_id: str
    description: str
    include_state: bool
    estimator: Pipeline


@dataclass
class YearData:
    """Filtered rows, target and filter report for a set of years."""

    frame: pd.DataFrame
    target: pd.Series
    filter_reports: dict[str, dict[str, int]]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def build_models(seed: int = DEFAULT_SEED, fast: bool = False) -> list[ModelSpec]:
    """The six fixed baseline models, as unfitted sklearn Pipelines."""
    n_trees = 60 if fast else 300
    n_iter = 80 if fast else 300

    def logistic() -> Pipeline:
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(max_iter=2000)),
            ]
        )

    def boosting() -> Pipeline:
        return Pipeline(
            [
                (
                    "model",
                    # early_stopping=False: sklearn's "auto" turns it on above 10,000 rows,
                    # which would hold out a random (not district-grouped) 10% and pick the
                    # number of rounds from the data. The round count stays fixed instead.
                    HistGradientBoostingClassifier(
                        learning_rate=0.05,
                        max_iter=n_iter,
                        early_stopping=False,
                        random_state=seed,
                    ),
                )
            ]
        )

    forest = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=n_trees, min_samples_leaf=20, n_jobs=-1, random_state=seed
                ),
            ),
        ]
    )
    dummy = Pipeline([("model", DummyClassifier(strategy="prior"))])
    return [
        ModelSpec("M0", "No-skill baseline (predicts the training positive rate)", False, dummy),
        ModelSpec("M1", "Logistic regression, no state", False, logistic()),
        ModelSpec("M2", "Logistic regression, with state", True, logistic()),
        ModelSpec("M3", "Random forest, no state", False, forest),
        ModelSpec("M4", "Gradient boosting, no state", False, boosting()),
        ModelSpec("M5", "Gradient boosting, with state", True, boosting()),
    ]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def recall_at_top(y_true: np.ndarray, y_score: np.ndarray, share: float = TOP_SHARE) -> float:
    """Share of all positives found among the ceil(share * n) highest scores.

    Scores tied at the cutoff get partial credit: the expected recall if the remaining slots
    were filled at random from the tied rows. The result therefore does not depend on row
    order, and a constant score gives about `share` (the no-skill value).
    """
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    positives = y_true.sum()
    if len(y_true) == 0 or positives == 0:
        return float("nan")
    k = math.ceil(share * len(y_true))
    cutoff = np.sort(y_score)[::-1][k - 1]
    above = y_score > cutoff
    tied = y_score == cutoff
    slots_left = k - int(above.sum())
    found = y_true[above].sum() + y_true[tied].sum() * slots_left / int(tied.sum())
    return float(found / positives)


def compute_metrics(y_true: Sequence[int], y_score: Sequence[float]) -> dict[str, float]:
    """pr_auc, pr_auc_lift, roc_auc, recall_at_top10, brier, n, positives, positive_rate.

    pr_auc_lift = pr_auc / positive_rate. PR-AUC's no-skill value is the positive rate, so the
    lift (1 = no skill) can be compared across years with different positive rates.
    Ranking metrics are NaN when only one class is present.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    n = len(y_true)
    positives = int(y_true.sum())
    both_classes = 0 < positives < n
    pr_auc = float(average_precision_score(y_true, y_score)) if both_classes else np.nan
    return {
        "pr_auc": pr_auc,
        "pr_auc_lift": pr_auc / (positives / n) if both_classes else np.nan,
        "roc_auc": float(roc_auc_score(y_true, y_score)) if both_classes else np.nan,
        "recall_at_top10": recall_at_top(y_true, y_score, TOP_SHARE),
        "brier": float(brier_score_loss(y_true, y_score)) if n else np.nan,
        "n": n,
        "positives": positives,
        "positive_rate": positives / n if n else np.nan,
    }


def calibration_table(y_true: Sequence[int], y_score: Sequence[float]) -> pd.DataFrame:
    """10 equal-width bins of predicted probability: mean predicted, observed rate, count."""
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    bins = np.minimum((y_score * CALIBRATION_BINS).astype(int), CALIBRATION_BINS - 1)
    rows = []
    for index in range(CALIBRATION_BINS):
        in_bin = bins == index
        count = int(in_bin.sum())
        rows.append(
            {
                "bin": index,
                "bin_lower": index / CALIBRATION_BINS,
                "bin_upper": (index + 1) / CALIBRATION_BINS,
                "mean_predicted": float(y_score[in_bin].mean()) if count else np.nan,
                "observed_rate": float(y_true[in_bin].mean()) if count else np.nan,
                "count": count,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def prepare_years(
    codes: Sequence[str], data_dir: Path, exclude_states: Sequence[str] | None
) -> YearData:
    """Load, filter and stack the given years; build the target."""
    frames, reports = [], {}
    for code in codes:
        filtered, report = bf.apply_modeling_filters(bf.load_year(code, data_dir), exclude_states)
        frames.append(filtered)
        reports[code] = report
        LOGGER.info("%s after filters: %s", code, report)
    frame = pd.concat(frames, ignore_index=True)
    return YearData(frame, bf.make_target(frame), reports)


def group_folds(groups: pd.Series, n_folds: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """GroupKFold splits by district, computed once and reused for every model.

    Raises BaselineDataError if any leaid is missing: the row could not be kept apart from
    its district, and GroupKFold would fail with an unhelpful "Input contains NaN".
    """
    missing = groups.isna()
    if missing.any():
        raise bf.BaselineDataError(
            f"{int(missing.sum()):,} training rows have a missing leaid (district ID); "
            "every row needs one to build the district-grouped CV folds"
        )
    n_groups = groups.nunique()
    if n_groups < n_folds:
        raise ValueError(f"Only {n_groups} districts in training data; need >= {n_folds}")
    dummy = np.zeros(len(groups))
    return list(GroupKFold(n_splits=n_folds).split(dummy, groups=groups.to_numpy()))


def fit_predict(
    spec: ModelSpec, train: pd.DataFrame, y_train: pd.Series, score: pd.DataFrame
) -> tuple[bf.FeatureBuilder, Pipeline, np.ndarray]:
    """Fit a fresh FeatureBuilder and model on `train`, return probabilities for `score`."""
    builder = bf.FeatureBuilder(include_state=spec.include_state).fit(train)
    model = clone(spec.estimator).fit(builder.transform(train), y_train.to_numpy())
    return builder, model, model.predict_proba(builder.transform(score))[:, 1]


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def cross_validate(
    specs: Sequence[ModelSpec], train: YearData, folds: Sequence[tuple[np.ndarray, np.ndarray]]
) -> pd.DataFrame:
    """One row per (model, fold) with every metric on the fold's validation rows."""
    rows = []
    for spec in specs:
        for fold, (fit_idx, valid_idx) in enumerate(folds):
            fold_train = train.frame.iloc[fit_idx]
            fold_valid = train.frame.iloc[valid_idx]
            _, _, scores = fit_predict(spec, fold_train, train.target.iloc[fit_idx], fold_valid)
            metrics = compute_metrics(train.target.iloc[valid_idx], scores)
            rows.append({"model": spec.model_id, "fold": fold, **metrics})
        LOGGER.info("CV done for %s", spec.model_id)
    return pd.DataFrame(rows)


def summarize(cv: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Long table: model, metric, cv_mean, cv_std, test, drop (cv_mean - test).

    drop is filled for pr_auc, pr_auc_lift and roc_auc. The pr_auc drop also moves with the
    positive rate of each year; pr_auc_lift removes that part.
    """
    rows = []
    for model_id, group in cv.groupby("model", sort=False):
        test_row = test.set_index("model").loc[model_id]
        for metric in METRIC_NAMES:
            cv_mean = float(group[metric].mean())
            test_value = float(test_row[metric])
            rows.append(
                {
                    "model": model_id,
                    "metric": metric,
                    "cv_mean": cv_mean,
                    "cv_std": float(group[metric].std(ddof=1)),
                    "test": test_value,
                    "drop": cv_mean - test_value if metric in DROP_METRICS else np.nan,
                }
            )
    return pd.DataFrame(rows)


def standardized_coefficients(builder: bf.FeatureBuilder, model: Pipeline) -> pd.DataFrame:
    """M1 coefficients on standardized features, largest absolute value first."""
    coef = model.named_steps["model"].coef_.ravel()
    table = pd.DataFrame({"feature": builder.feature_names, "coefficient": coef})
    table["abs_coefficient"] = table["coefficient"].abs()
    return table.sort_values("abs_coefficient", ascending=False, kind="stable").reset_index(
        drop=True
    )


def summary_table(summary: pd.DataFrame, new_schools: pd.DataFrame) -> pd.DataFrame:
    """Wide, readable table for the console: one row per model."""
    wide = summary.pivot(index="model", columns="metric", values=["cv_mean", "cv_std", "test"])
    table = pd.DataFrame(index=wide.index)
    table["cv_pr_auc"] = [
        f"{m:.3f} ± {s:.3f}"
        for m, s in zip(wide[("cv_mean", "pr_auc")], wide[("cv_std", "pr_auc")], strict=True)
    ]
    table["test_pr_auc"] = wide[("test", "pr_auc")].round(3)
    table["drop_pr"] = (wide[("cv_mean", "pr_auc")] - wide[("test", "pr_auc")]).round(3)
    table["test_pr_lift"] = wide[("test", "pr_auc_lift")].round(2)
    table["cv_roc_auc"] = wide[("cv_mean", "roc_auc")].round(3)
    table["test_roc_auc"] = wide[("test", "roc_auc")].round(3)
    table["test_recall@10%"] = wide[("test", "recall_at_top10")].round(3)
    table["test_brier"] = wide[("test", "brier")].round(4)
    table["new_sch_pr_auc"] = new_schools.set_index("model")["pr_auc"].round(3)
    return table


def _json_ready(value):
    """Turn numpy scalars into plain Python for json.dump."""
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Not JSON serializable: {type(value)}")


def write_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, default=_json_ready) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> pd.DataFrame:
    """Run the whole baseline and write every output. Returns the console summary table."""
    train_years = list(dict.fromkeys(args.train_years))
    if args.test_year in train_years:
        raise ValueError(f"Test year {args.test_year} is also a training year")
    out_dir = Path(args.out_dir or DEFAULT_OUT_DIR)
    model_dir = Path(args.model_dir or DEFAULT_MODEL_DIR)
    data_dir = Path(args.data_dir)

    train = prepare_years(train_years, data_dir, args.exclude_states)
    test = prepare_years([args.test_year], data_dir, args.exclude_states)
    # Created only now, so a failed load leaves no empty output folder behind.
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = build_models(args.seed, args.fast)

    folds = group_folds(train.frame["leaid"], args.cv_folds)
    cv = cross_validate(specs, train, folds)

    train_keys = set(train.frame["combokey"])
    new_mask = ~test.frame["combokey"].isin(train_keys).to_numpy()
    missing_mask = (
        test.frame[list(MISSING_SUBSET_COLUMNS)].apply(pd.to_numeric).isna().any(axis=1)
    ).to_numpy()
    subsets = {
        "pct_504_or_el_missing": missing_mask,
        "pct_504_and_el_present": ~missing_mask,
    }
    model_dir.mkdir(parents=True, exist_ok=True)
    test_rows, new_rows, missing_rows, calibration, features = [], [], [], [], {}
    coefficients = None
    for spec in specs:
        builder, model, scores = fit_predict(spec, train.frame, train.target, test.frame)
        test_rows.append({"model": spec.model_id, **compute_metrics(test.target, scores)})
        new_rows.append(
            {
                "model": spec.model_id,
                "subset": "new_schools",
                **compute_metrics(test.target[new_mask], scores[new_mask]),
            }
        )
        for subset, mask in subsets.items():
            missing_rows.append(
                {
                    "model": spec.model_id,
                    "subset": subset,
                    **compute_metrics(test.target[mask], scores[mask]),
                }
            )
        calibration.append(calibration_table(test.target, scores).assign(model=spec.model_id))
        features[spec.model_id] = builder.feature_names
        if spec.model_id == "M1":
            coefficients = standardized_coefficients(builder, model)
        joblib.dump((builder, model), model_dir / f"{spec.model_id}.joblib")

    test_metrics = pd.DataFrame(test_rows)
    new_schools = pd.DataFrame(new_rows)
    by_missing = pd.DataFrame(missing_rows)
    summary = summarize(cv, test_metrics)
    calibration_frame = pd.concat(calibration, ignore_index=True)
    calibration_frame = calibration_frame[["model", *calibration_frame.columns[:-1]]]

    cv.to_csv(out_dir / "metrics_cv.csv", index=False)
    summary.to_csv(out_dir / "metrics_summary.csv", index=False)
    new_schools.to_csv(out_dir / "metrics_test_new_schools.csv", index=False)
    by_missing.to_csv(out_dir / "metrics_test_by_missing_504_el.csv", index=False)
    calibration_frame.to_csv(out_dir / "calibration_test.csv", index=False)
    coefficients.to_csv(out_dir / "coefficients_M1.csv", index=False)
    write_json(
        {**train.filter_reports, **test.filter_reports},
        out_dir / "filter_report.json",
    )
    write_json(
        {
            "target": "any_seclusion = seclusion_instances >= 1",
            "train_years": train_years,
            "test_year": args.test_year,
            "train_rows": len(train.frame),
            "train_positives": int(train.target.sum()),
            "test_rows": len(test.frame),
            "test_positives": int(test.target.sum()),
            "test_new_school_rows": int(new_mask.sum()),
            "test_rows_504_or_el_missing": int(missing_mask.sum()),
            "train_rows_504_or_el_missing": int(
                train.frame[list(MISSING_SUBSET_COLUMNS)]
                .apply(pd.to_numeric)
                .isna()
                .any(axis=1)
                .sum()
            ),
            "cv_folds": args.cv_folds,
            "cv_groups": "leaid",
            "train_districts": int(train.frame["leaid"].nunique()),
            "seed": args.seed,
            "fast": bool(args.fast),
            "exclude_states": sorted(args.exclude_states or []),
            "data_dir": str(data_dir),
            "model_dir": str(model_dir),
            "models": {spec.model_id: spec.description for spec in specs},
            "features": features,
            "versions": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "sklearn": sklearn.__version__,
            },
        },
        out_dir / "run_info.json",
    )

    table = summary_table(summary, new_schools)
    banner = "=" * 78
    print(banner)
    print(
        f"Baseline: train {'+'.join(train_years)} ({len(train.frame):,} schools, "
        f"{int(train.target.sum()):,} positive) -> test {args.test_year} "
        f"({len(test.frame):,} schools, {int(test.target.sum()):,} positive, "
        f"{int(new_mask.sum()):,} new)"
    )
    print(f"CV: {args.cv_folds}-fold GroupKFold by leaid. Outputs in {out_dir}")
    print(table.to_string())
    print(banner)
    return table


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the any-seclusion baseline models.")
    parser.add_argument(
        "--train-years", nargs="+", default=list(DEFAULT_TRAIN_YEARS), choices=bf.YEAR_CODES
    )
    parser.add_argument("--test-year", default=DEFAULT_TEST_YEAR, choices=bf.YEAR_CODES)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="default reports/baseline",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="default models/baseline",
    )
    parser.add_argument("--cv-folds", type=int, default=DEFAULT_CV_FOLDS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--exclude-states", nargs="*", default=None, help="for example HI PR")
    parser.add_argument("--fast", action="store_true", help="fewer trees/iterations (tests)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point. Returns the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    try:
        run(args)
    except (bf.BaselineDataError, ValueError) as error:
        LOGGER.error("%s: %s", type(error).__name__, error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
