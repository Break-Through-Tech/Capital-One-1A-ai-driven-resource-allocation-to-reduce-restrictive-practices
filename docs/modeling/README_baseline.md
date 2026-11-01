# Baseline model: did a school report any seclusion?

This is the team's first, deliberately simple model. It answers one yes/no question per
school: did the school report at least one seclusion incident? It gives every later model a
fair score to beat.

## First results (train 2017-18, test 2021-22)

Training: 87,684 schools (5,874 with any seclusion). Test: 89,713 schools (6,470 positive,
9,190 not in the training year). Test-year scores:

| Model | PR-AUC | Lift | ROC-AUC | Recall in top 10% |
|---|---|---|---|---|
| M0 | 0.072 | 1.00 | 0.500 | 0.100 |
| M1 | 0.119 | 1.66 | 0.660 | 0.196 |
| M2 | 0.310 | 4.29 | 0.790 | 0.459 |
| M3 | 0.168 | 2.32 | 0.727 | 0.265 |
| M4 | 0.161 | 2.24 | 0.730 | 0.258 |
| M5 | 0.373 | 5.17 | 0.844 | 0.500 |

State carries most of the signal: without it, the best model is M3 (PR-AUC 0.168).

## What it does

1. Loads the training year(s) (default 2017-18) and the test year (default 2021-22).
2. Keeps the rows that pass the modeling filters (below) and builds the target
   `any_seclusion = 1 if seclusion_instances >= 1 else 0`.
3. Compares six fixed models with 5-fold cross-validation on the training year(s). Folds
   are grouped by district (`leaid`), so a district is never in both the fitting rows and
   the scoring rows. The same folds are used for every model.
4. Refits every model on all training rows and scores the test year once. The newer year
   stands in for "data the model has never seen".

| ID | Model | State? |
|---|---|---|
| M0 | Always predicts the training positive rate (no skill) | no |
| M1 | Logistic regression (median fill, standardize) | no |
| M2 | Logistic regression | yes |
| M3 | Random forest (300 trees, min 20 schools per leaf) | no |
| M4 | Histogram gradient boosting (learning rate 0.05, 300 rounds) | no |
| M5 | Histogram gradient boosting | yes |

Features (from `docs/eda/feature_shortlist_202122.csv`): log enrollment, grade band,
special-education / alternative / charter / juvenile-justice / magnet status, `pct_idea`,
`pct_504`, `pct_el` with a "missing" indicator for each, psychologists and social workers per
100 students (capped at the training 99.5th percentile), log district enrollment, and, for
M2 and M5 only, one column per training state.

## Where to put the data

Copy each year's analysis file from the team's shared data folder to:

```
data/processed/201718/schools_201718_analysis.csv
data/processed/202122/schools_202122_analysis.csv
```

`data/processed/schools_{year}_analysis.csv` also works. These files are git-ignored.

## How to run it

From the repository root:

```bash
pip install -r requirements.txt

python scripts/train_baseline.py --train-years 201718 --test-year 202122

# Variant
python scripts/train_baseline.py --exclude-states HI PR

# Tests (the data tests skip if the cleaned files above are missing)
python -m pytest -q
```

2015-16 and 2020-21 cannot be used yet: their cleaned files have a different column layout
and must first be converted to the 50-column team format (AI_CONTEXT A4).

Other options: `--data-dir`, `--out-dir`, `--model-dir`, `--cv-folds` (5), `--seed` (42),
`--fast` (fewer trees, used by the tests).

## Output files

Written to `reports/baseline/` (git-ignored).

| File | Contents |
|---|---|
| `metrics_cv.csv` | One row per model and fold: every metric on that fold's held-out districts. |
| `metrics_summary.csv` | Per model and metric: CV mean, CV standard deviation, test value, and `drop` = CV mean - test (PR-AUC, PR-AUC lift and ROC-AUC only). |
| `metrics_test_new_schools.csv` | Test metrics for schools whose `combokey` is not in the training years. |
| `metrics_test_by_missing_504_el.csv` | Test metrics split into schools with `pct_504` or `pct_el` missing and schools with both present (see "Temporal test"). |
| `calibration_test.csv` | Per model, 10 equal-width bins of predicted probability: mean predicted, observed rate, count. |
| `coefficients_M1.csv` | M1 coefficients on standardized features, largest first. Associations, not causes. |
| `filter_report.json` | Rows left after each filter step, per year. |
| `run_info.json` | Years, row and positive counts, features per model, package versions, seed, folds. |

Fitted models are saved as `(FeatureBuilder, model)` pairs in `models/baseline/<ID>.joblib`
(git-ignored). Load with
`builder, model = joblib.load(path)` and score with
`model.predict_proba(builder.transform(frame))[:, 1]`.

Metrics: **PR-AUC** (average precision; main metric because positives are rare; no-skill
value = positive rate), **PR-AUC lift** (PR-AUC divided by the positive rate; 1 = no skill),
**ROC-AUC** (0.5 = no skill), **recall in the top 10%** (share of all positive schools found
among the 10% with the highest scores; schools tied at the cutoff get partial credit, so a
no-skill model scores about 0.10), **Brier score** (probability error, lower is better).

The PR-AUC `drop` partly reflects a different positive rate in the test year, not only a
worse model. Compare the `pr_auc_lift` drop as well: it takes the positive rate out.

## Modeling choices and why

- **Target.** Any seclusion (yes/no) rather than the rate: about 7% of schools are positive
  and counts are very skewed, so the yes/no question is the most stable starting point.
- **Filters.** `flag_analysis_ready` is True; `seclusion_instances` is not missing (an
  unknown outcome is never counted as "no seclusion", even if a file lacks the flag); enrollment at least 30 (rates of tiny schools
  are noise); drop schools with impossible staffing (any FTE above enrollment, counselors +
  nurses + psychologists + social workers above 20 per 100 students, or teachers above 50 per
  100), the EDA rule from `data_issues_202122.csv` #3. Missing staffing never drops a row.
- **District-grouped CV.** Schools in one district share policy and reporting habits; letting
  a district be on both sides of a split would overstate the scores.
- **Temporal test.** Train on older years, test once on the newest year, to see how much a
  model loses on data from a later year (`drop`). Caution: `pct_504` and `pct_el` are almost
  never missing in 2017-18 but 22.6% and 18.8% missing in 2021-22, and the missingness is
  informative (`data_issues_202122.csv` #2). A model trained on 2017-18 barely sees the
  `*_na` indicators, so the drop mixes this coding change with any real decline.
  `metrics_test_by_missing_504_el.csv` scores the two groups separately to show how much.
- **No leakage.** Seclusion columns, `flag_missing_seclusion`, `flag_analysis_ready`, IDs and
  names are never features (checked in code). Caps and state lists are learned from training
  rows only, inside each CV fold too.
- **No class weights.** Weights would distort the predicted probabilities. We compare models
  on ranking metrics, which do not depend on a cutoff, and keep the probabilities usable.
- **Fixed hyperparameters.** No tuning this round: the goal is a fair floor, not the best
  model. Gradient boosting has early stopping turned off, so it always runs its 300 rounds
  (sklearn would otherwise switch it on above 10,000 rows and hold out a random,
  not district-grouped, 10% of each fold).

## Open team decisions

1. **`enrollment_total` as an input.** It is the rate's denominator (AI_CONTEXT A7). It is
   used here as log enrollment; agree whether that is acceptable.
2. **Extreme seclusion counts** (more incidents than students, `data_issues_202122.csv` #4).
   They do not change the yes/no target, but matter for any rate model; verify with CRDC.
3. **Puerto Rico and Hawaii** report no seclusion. Keep, or drop with `--exclude-states`?
4. **Security staffing** (`fte_leo`, `fte_guards`) is left out because of likely reverse
   causality. Revisit?
5. **2020-21 in training.** It is the COVID year; including it may teach the model unusual
   patterns.
6. **Missing `pct_504` / `pct_el` coding shift.** Much more missing in 2021-22 than in
   2017-18. Options: keep the indicators (current), drop the two features, or train on a
   year with similar coding. Compare using `metrics_test_by_missing_504_el.csv`.
7. **Forecasting vs same-year scoring.** This baseline uses features from the same year as
   the outcome. To forecast next year's seclusion, features would have to come from the
   previous year.
