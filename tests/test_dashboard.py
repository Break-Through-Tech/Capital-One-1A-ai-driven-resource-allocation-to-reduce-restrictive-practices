"""Contract, corruption, immutable snapshot, and browser-independent UI regression tests."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from export_dashboard import TABLES, export_run

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
from results import load_snapshots, scores


@pytest.fixture
def completed_report(tmp_path):
    snapshot = next(
        s for s in load_snapshots()[0] if len(s["info"]["train_years"]) == 3
    )
    report = tmp_path / "report"
    report.mkdir()
    (report / "run_info.json").write_text(json.dumps(snapshot["info"]))
    (report / "filter_report.json").write_text(json.dumps(snapshot["filters"]))
    for key, (filename, _) in TABLES.items():
        pd.DataFrame(snapshot["tables"][key]).to_csv(report / filename, index=False)
    return report


def test_export_is_idempotent_and_pins_survive_later_runs(completed_report, tmp_path):
    out = tmp_path / "snapshots"
    first = export_run(completed_report, out)
    original = first.read_bytes()
    assert export_run(completed_report, out) == first
    info_path = completed_report / "run_info.json"
    info = json.loads(info_path.read_text())
    info["versions"]["python"] = "future-version"
    info_path.write_text(json.dumps(info))
    second = export_run(completed_report, out)
    assert second != first
    assert first.read_bytes() == original
    snapshots, errors = load_snapshots(out)
    assert len(snapshots) == 2 and not errors
    assert set(s["snapshot_id"] for s in snapshots) == {first.stem, second.stem}


def test_failed_export_leaves_last_valid_snapshot(completed_report, tmp_path):
    out = tmp_path / "snapshots"
    first = export_run(completed_report, out)
    original = first.read_bytes()
    cv = completed_report / "metrics_cv.csv"
    pd.read_csv(cv).iloc[:-1].to_csv(cv, index=False)
    with pytest.raises(ValueError, match="cross-validation"):
        export_run(completed_report, out)
    assert list(out.glob("*.json")) == [first]
    assert first.read_bytes() == original


def test_export_rejects_inconsistent_counts(completed_report, tmp_path):
    path = completed_report / "run_info.json"
    info = json.loads(path.read_text())
    info["test_rows"] += 1
    path.write_text(json.dumps(info))
    with pytest.raises(ValueError, match="counts"):
        export_run(completed_report, tmp_path / "out")


def test_corrupted_snapshot_is_not_displayed(completed_report, tmp_path):
    out = tmp_path / "snapshots"
    path = export_run(completed_report, out)
    payload = json.loads(path.read_text())
    payload["info"]["test_rows"] += 1
    path.write_text(json.dumps(payload))
    snapshots, errors = load_snapshots(out)
    assert not snapshots and len(errors) == 1


def test_exports_do_not_include_local_paths_or_school_ids(completed_report, tmp_path):
    path = completed_report / "run_info.json"
    info = json.loads(path.read_text())
    info.update(
        data_dir="/private/data", model_dir="/private/models", combokey="private-id"
    )
    path.write_text(json.dumps(info))
    content = export_run(completed_report, tmp_path / "out").read_text()
    assert "/private/" not in content and "private-id" not in content


def test_shipped_snapshot_metrics_and_metadata():
    snapshots, errors = load_snapshots()
    assert not errors and len(snapshots) >= 7
    combined = next(s for s in snapshots if len(s["info"]["train_years"]) == 3)
    assert scores(combined).set_index("model").loc["M5", "pr_auc"] == pytest.approx(
        0.4089644641
    )
    assert combined["info"]["test_rows"] == 89713
    assert "reconstructed" in combined["provenance"]


def app_test():
    testing = pytest.importorskip("streamlit.testing.v1")
    pytest.importorskip("plotly")
    return testing.AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=20)


def test_dashboard_all_views_and_empty_comparison():
    app = app_test().run()
    assert not app.exception
    assert app.metric[0].value == "0.409"
    for name in ["Compare models", "Data quality", "Presentation", "Overview"]:
        app.radio[0].set_value(name).run()
        assert not app.exception, name
    app.radio[0].set_value("Compare models").run()
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert any("Select at least" in x.value for x in app.info)


def test_dashboard_pinned_deep_link_and_missing_snapshot():
    snapshot = next(
        s for s in load_snapshots()[0] if len(s["info"]["train_years"]) == 3
    )
    app = app_test()
    app.query_params.update(
        snapshot=snapshot["snapshot_id"],
        model="M2",
        view="Presentation",
        evaluation="test",
    )
    app.run()
    assert not app.exception
    assert app.metric[0].value == "0.348"
    assert app.radio[0].value == "Presentation"
    app = app_test()
    app.query_params["snapshot"] = "missing"
    app.run()
    assert not app.exception
    assert "unavailable" in app.error[0].value


def test_backward_experiment_defaults_to_cv():
    app = app_test().run()
    backward = next(
        s for s in load_snapshots()[0] if s["evaluation"] == "backward_temporal"
    )
    app.selectbox[0].set_value(backward["experiment_id"]).run()
    assert not app.exception
    assert app.selectbox[2].value == "District-grouped CV"
    assert app.metric[0].value == "0.344"


def test_full_training_exports_snapshot_and_fast_run_does_not(
    tmp_path, real_sample_dir, monkeypatch
):
    import hashlib
    import train_baseline as tb

    # Two inexpensive real models verify the publication hook and M1 coefficient output.
    original = tb.build_models
    monkeypatch.setattr(tb, "build_models", lambda seed, fast: original(seed, fast)[:2])
    out = tmp_path / "published"
    args = [
        "--data-dir",
        str(real_sample_dir),
        "--out-dir",
        str(tmp_path / "reports"),
        "--model-dir",
        str(tmp_path / "models"),
        "--dashboard-dir",
        str(out),
    ]
    assert tb.main(args) == 0
    snapshots, errors = load_snapshots(out)
    assert not errors and len(snapshots) == 1
    expected = hashlib.sha256(
        (real_sample_dir / "201718/schools_201718_analysis.csv").read_bytes()
    ).hexdigest()
    assert snapshots[0]["info"]["input_sha256"]["201718"] == expected
    original_files = list(out.glob("*.json"))
    assert tb.main([*args, "--fast"]) == 0
    assert list(out.glob("*.json")) == original_files


def test_pin_button_preserves_cv_evaluation():
    app = app_test().run()
    app.selectbox[2].set_value("District-grouped CV").run()
    value = app.metric[0].value
    app.button[0].click().run()
    assert not app.exception
    assert app.query_params["evaluation"] == ["cv_mean"]
    assert app.metric[0].value == value
    assert app.selectbox[1].value == "District-grouped CV"
