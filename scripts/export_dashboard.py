#!/usr/bin/env python
"""Publish validated, aggregate-only experiment snapshots; never loads fitted models."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dashboard/data/runs"
METRICS = (
    "pr_auc",
    "pr_auc_lift",
    "roc_auc",
    "recall_at_top10",
    "brier",
    "n",
    "positives",
    "positive_rate",
)
# Explicit allowlists keep IDs, paths, features, and school-level data out of the website.
INFO_FIELDS = (
    "target",
    "train_years",
    "test_year",
    "train_rows",
    "train_positives",
    "test_rows",
    "test_positives",
    "test_new_school_rows",
    "cv_folds",
    "cv_groups",
    "seed",
    "fast",
    "exclude_states",
    "models",
    "versions",
    "input_sha256",
    "training_code_sha256",
)
TABLES = {
    "summary": (
        "metrics_summary.csv",
        ["model", "metric", "cv_mean", "cv_std", "test", "drop"],
    ),
    "cv": ("metrics_cv.csv", ["model", "fold", *METRICS]),
    "new_schools": ("metrics_test_new_schools.csv", ["model", "subset", *METRICS]),
    "missingness": (
        "metrics_test_by_missing_504_el.csv",
        ["model", "subset", *METRICS],
    ),
    "calibration": (
        "calibration_test.csv",
        [
            "model",
            "bin",
            "bin_lower",
            "bin_upper",
            "mean_predicted",
            "observed_rate",
            "count",
        ],
    ),
}


def records(frame):
    return json.loads(frame.to_json(orient="records"))


def export_run(
    report_dir: Path,
    output_dir: Path = DEFAULT_OUTPUT,
    provenance: str = "See the recorded input hashes and cleaning QA reports.",
) -> Path:
    """Validate every required table before atomically publishing an immutable snapshot."""
    report_dir, output_dir = Path(report_dir), Path(output_dir)
    info_path = report_dir / "run_info.json"
    info = json.loads(info_path.read_text())
    if info.get("synthetic", False):
        raise ValueError("Synthetic runs cannot be published as CRDC results")
    if not info["train_years"] or info["test_year"] in info["train_years"]:
        raise ValueError("Training and test years must be disjoint")
    models = set(info["models"])
    if not models or info["test_rows"] <= 0 or info["cv_folds"] < 2:
        raise ValueError("Invalid model list or evaluation sizes")
    tables, frames = {}, {}
    for key, (filename, columns) in TABLES.items():
        frame = pd.read_csv(report_dir / filename)
        if not set(columns) <= set(frame.columns):
            raise ValueError(f"{filename}: missing required columns")
        frame = frame[columns]
        if set(frame.model) != models:
            raise ValueError(f"{filename}: incomplete model results")
        numeric = frame.select_dtypes(include="number")
        if numeric.map(lambda v: not math.isinf(v)).eq(False).any().any():
            raise ValueError(f"{filename}: infinite metric")
        frames[key] = frame
        tables[key] = records(frame)
    summary, cv = frames["summary"], frames["cv"]
    expected = {(m, metric) for m in models for metric in METRICS}
    if (
        summary.duplicated(["model", "metric"]).any()
        or set(zip(summary.model, summary.metric)) != expected
    ):
        raise ValueError("Summary must contain every metric exactly once per model")
    expected_cv = {(m, fold) for m in models for fold in range(info["cv_folds"])}
    if (
        cv.duplicated(["model", "fold"]).any()
        or set(zip(cv.model, cv.fold)) != expected_cv
    ):
        raise ValueError("Incomplete district-grouped cross-validation")
    if summary[["cv_mean", "test"]].isna().any().any():
        raise ValueError("Summary contains missing evaluation metrics")
    if not summary.loc[summary.metric.eq("n"), "test"].eq(info["test_rows"]).all():
        raise ValueError("Test counts do not match run metadata")
    for col in ("test", "cv_mean"):
        vals = summary.loc[
            summary.metric.isin(
                ["pr_auc", "roc_auc", "recall_at_top10", "brier", "positive_rate"]
            ),
            col,
        ]
        if not vals.between(0, 1).all():
            raise ValueError("Probability metrics outside [0, 1]")
    for model in models:
        metrics = summary[summary.model.eq(model)].set_index("metric")
        folds = cv[cv.model.eq(model)]
        for metric in METRICS:
            if not math.isclose(
                folds[metric].mean(),
                metrics.loc[metric, "cv_mean"],
                rel_tol=1e-7,
                abs_tol=1e-9,
            ):
                raise ValueError("CV table and summary disagree")
        if metrics.loc["positives", "test"] != info["test_positives"]:
            raise ValueError("Positive counts do not match run metadata")
    cal = frames["calibration"]
    if (
        cal.duplicated(["model", "bin"]).any()
        or not cal.groupby("model")["count"].sum().eq(info["test_rows"]).all()
    ):
        raise ValueError("Calibration counts do not match test population")
    missing = frames["missingness"]
    expected_subsets = {"pct_504_or_el_missing", "pct_504_and_el_present"}
    if (
        missing.duplicated(["model", "subset"]).any()
        or set(zip(missing.model, missing.subset))
        != {(m, s) for m in models for s in expected_subsets}
        or not missing.groupby("model")["n"].sum().eq(info["test_rows"]).all()
    ):
        raise ValueError("Missingness subsets do not partition the test population")
    new = frames["new_schools"]
    if (
        new.model.duplicated().any()
        or not new["n"].eq(info["test_new_school_rows"]).all()
    ):
        raise ValueError("New-school counts do not match run metadata")
    filters = json.loads((report_dir / "filter_report.json").read_text())
    filters = {
        year: {k: int(v) for k, v in row.items() if isinstance(v, (int, float))}
        for year, row in filters.items()
        if year in [*info["train_years"], info["test_year"]] and isinstance(row, dict)
    }
    experiment = {
        key: info.get(key)
        for key in (
            "train_years",
            "test_year",
            "seed",
            "fast",
            "exclude_states",
            "models",
            "cv_folds",
        )
    }
    experiment_id = hashlib.sha256(
        json.dumps(experiment, sort_keys=True).encode()
    ).hexdigest()[:16]
    payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "results_saved_at": datetime.fromtimestamp(
            info_path.stat().st_mtime, timezone.utc
        ).isoformat(),
        "evaluation": (
            "forward_temporal"
            if max(info["train_years"]) < info["test_year"]
            else "backward_temporal"
        ),
        "provenance": provenance,
        "info": {key: info[key] for key in INFO_FIELDS if key in info},
        "tables": tables,
        "filters": filters,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    payload["snapshot_id"] = digest
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{digest}.json"
    content = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    if destination.exists():
        if destination.read_text() != content:
            raise ValueError("Existing snapshot differs from its content ID")
        return destination
    # Readers either see a complete JSON file or no file, including during retraining.
    handle, temporary = tempfile.mkstemp(
        prefix=".export-", suffix=".tmp", dir=output_dir
    )
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dirs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--provenance", default="See the recorded input hashes and cleaning QA reports."
    )
    args = parser.parse_args()
    for folder in args.report_dirs:
        print(export_run(folder, args.output_dir, args.provenance))


if __name__ == "__main__":
    main()
