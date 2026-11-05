# CRDC Model Lab

An interactive Streamlit + Plotly dashboard for the team's completed experiments.
Includes overview, model/training-year comparison, calibration, data-quality views,
and a presentation view that can be pinned to an immutable snapshot in its URL.
The initial seven runs contain six forward temporal comparisons and a separate
within-2021–22 district-grouped CV view. Backward-year test results are labeled.

## Run locally

From the repository root:

```bash
python -m pip install -r dashboard/requirements.txt
python -m streamlit run dashboard/app.py
```

Open the URL printed by Streamlit. On macOS, if file watching fails, add
`--server.fileWatcherType poll`. The dashboard needs no raw data, scikit-learn,
model files, database, API keys, or training process. The initial aggregate result
bundle is approximately 280 KB; dependencies are installed rather than committed.

## Share with the team

Deploy through [Streamlit Community Cloud](https://share.streamlit.io/):

- Repository: `Break-Through-Tech/Capital-One-1A-ai-driven-resource-allocation-to-reduce-restrictive-practices`
- Branch: `codex/model-dashboard` while this stacked PR is under review; switch to `main` after merging.
- Entry point: `dashboard/app.py`
- Python: 3.12 (Advanced settings).
- Dependencies: `dashboard/requirements.txt` (Cloud finds the entry point's dependency file).

Connecting the organization repo may require a GitHub administrator. The app is not
publicly hosted merely because this PR exists. The owner must finish the account
connection and deployment. The root README has a deploy link prefilled for this branch.
Do not upload the raw CSVs or fitted model files to the dashboard.

After deployment, send teammates the app URL. Select a result/model/evaluation and
click **Pin presentation** to create a stable URL. Keep its snapshot JSON in Git;
deleting it breaks that presentation link. A missing pinned snapshot shows an error
instead of silently substituting newer results. The pinned presentation and model
metrics remain fixed; the separately labeled latest-experiment comparison panel is live.

## How updates work

1. Train on the modeling machine with the usual full-run command:

   ```bash
   python scripts/train_baseline.py --train-years 201516 201718 202021 --test-year 202122 --out-dir reports/baseline/my_run --model-dir models/baseline/my_run
   ```

2. On successful completion, the script validates all report tables and writes an
   immutable, aggregate-only JSON snapshot into `dashboard/data/runs/`. New runs record
   input-file and training-code hashes. `--fast` skips publication; `--no-dashboard`
   explicitly disables it. `--dashboard-dir PATH` selects another destination.
3. Review and commit the new snapshot, then push it to the dashboard's deployed branch.
   Streamlit Cloud updates from GitHub. Local sessions check every 30 seconds for newly
   exported files; hosted sessions see files published to the deployed Git branch.
4. The app automatically discovers the latest snapshot for each experiment. No frontend
   edits are needed when an experiment adds a model through the same report contract.

Training is not automatically scheduled, and local exports are not automatically pushed
to GitHub. Those remain explicit team actions. The provided GitHub Actions workflow
validates the app and exported data; it does not train models. This avoids starting
expensive training on page visits and does not depend on unpublished raw-data downloads.

To publish existing completed results (including a different model pipeline that emits
the same report format):

```bash
python scripts/export_dashboard.py reports/baseline/my_run --provenance "Describe the cleaning source and any reconstruction here."
```

Required files: `run_info.json`, `filter_report.json`, `metrics_summary.csv`,
`metrics_cv.csv`, `metrics_test_new_schools.csv`,
`metrics_test_by_missing_504_el.csv`, and `calibration_test.csv`.
See `scripts/export_dashboard.py` for the version-1 schema and allowed fields.
Model identifiers and descriptions come from `run_info.json`; there is no fixed
six-model limit. The default selection prefers M5 when present, otherwise the first model.
New experiment identity includes training/test years, model definitions, seed, folds,
excluded states and fast/full settings. New snapshots never overwrite older ones.

The fixed state-missingness and common-new-school tables in `data/context.json` are
explicitly dated November 4, 2026. They are historical supporting analyses, not automatically
recomputed for new training runs. Common-cohort results are shown only with their matching
snapshot IDs and M5. Ordinary per-run new-school cohorts vary across training combinations.

## Validation

```bash
python -m pip install -r requirements.txt -r dashboard/requirements.txt
python -m pytest -q
```

Tests cover complete exports, rejection of incomplete/mismatched results, immutable
snapshots, corrupted-file handling, payload allowlists, all UI views, empty model
selections, pinned links, and backward-year evaluation labeling. Real-data model tests
skip when the local cleaned CSVs are absent; dashboard tests run from committed aggregates.
