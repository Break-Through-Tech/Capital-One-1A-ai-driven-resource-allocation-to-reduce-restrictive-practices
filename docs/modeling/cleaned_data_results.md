# Completed cleaned-data baseline comparison

Verified November 4, 2026. PR #27 (2020–21) and PR #23 (2015–16) are merged into main and integrated into the local model branch. All seven saved runs are complete: six forward temporal comparisons and one within-2021–22 district-grouped CV run. All runs used the full model settings, seed 42, and five district-grouped folds.

## Test on 2021–22: M5

Every row scores the same 89,713 schools, including 6,470 positives. Lift means average precision divided by the test positive rate. Recall is the fraction of positive schools found in the highest-scored 10%.

| training_years           |   pr_auc |   pr_auc_lift |   recall_at_top10 |   roc_auc |   brier |
|:-------------------------|---------:|--------------:|------------------:|----------:|--------:|
| 201718                   |   0.3731 |        5.1739 |            0.4995 |    0.8439 |  0.0542 |
| 201516                   |   0.3660 |        5.0746 |            0.4835 |    0.8312 |  0.0557 |
| 201516 + 201718          |   0.3946 |        5.4721 |            0.5063 |    0.8439 |  0.0539 |
| 202021                   |   0.3918 |        5.4332 |            0.5124 |    0.8429 |  0.0545 |
| 201718 + 202021          |   0.3894 |        5.3998 |            0.5201 |    0.8523 |  0.0540 |
| 201516 + 201718 + 202021 |   0.4090 |        5.6707 |            0.5257 |    0.8510 |  0.0535 |

The combined 2015–16 + 2017–18 + 2020–21 model has the highest observed PR-AUC (0.409), up from 0.373 for 2017–18 alone. Its top-10% recall is 52.6%, versus 50.0%. This supports retaining 2020–21 in the comparison; it does not establish a statistically significant improvement or a universally best training choice.

## Same new-school cohort for every model

These 2,241 schools (128 positive) are absent from all three older training-year datasets after modeling filters. Comparing this identical cohort avoids the changing cohort sizes in the original per-run reports. It measures new schools, not necessarily new districts.

| training_years           |   pr_auc |   pr_auc_lift |   recall_at_top10 |   roc_auc |   brier |
|:-------------------------|---------:|--------------:|------------------:|----------:|--------:|
| 201718                   |   0.2101 |        3.6784 |            0.3750 |    0.6694 |  0.0501 |
| 201516                   |   0.2230 |        3.9039 |            0.3594 |    0.7336 |  0.0499 |
| 201516 + 201718          |   0.2469 |        4.3228 |            0.4219 |    0.7065 |  0.0490 |
| 202021                   |   0.2063 |        3.6127 |            0.3984 |    0.5865 |  0.0507 |
| 201718 + 202021          |   0.2239 |        3.9199 |            0.3672 |    0.7409 |  0.0504 |
| 201516 + 201718 + 202021 |   0.2248 |        3.9364 |            0.4219 |    0.7243 |  0.0497 |

On this cohort, 2015–16 + 2017–18 has the highest PR-AUC (0.247), above the three-year model (0.225). Both find 42.2% of positives in the top 10%. The small cohort and lack of uncertainty intervals limit how strongly to interpret this difference.

## Within-2021–22 cross-validation

M5 district-grouped CV mean PR-AUC is 0.344, mean lift 4.78, and mean top-10% recall 46.6%. The `cv_202122` run also scores 2017–18 after fitting 2021–22; that backward-year test is deliberately excluded from the forward comparison above. Fold-mean lift is not the ratio of fold-mean PR-AUC to overall prevalence.

## Data provenance and interpretation

The local 2015–16 and 2020–21 team-format inputs were reconstructed in the preceding work from older cleaned exports and then processed with Sofia's scripts; they are not independently downloaded raw-source reproductions. That work reported matching substantive QA counts and mappings after restoring the 2015–16 999 FTE placeholders, with remaining differences in source-file metadata and ID notes. This wrap-up verifies the saved models against the currently available inputs, rather than claiming to rerun that raw-data audit. Current analysis-input SHA-256 hashes are recorded in `reports/baseline/comparison/input_sha256.json`.

2020–21 missing outcomes are uneven across states. Largest missing-outcome shares in the full cleaned school roster:

| lea_state   |   schools |   missing_outcome |   missing_share |
|:------------|----------:|------------------:|----------------:|
| PR          |   841.000 |           841.000 |           1.000 |
| HI          |   294.000 |           294.000 |           1.000 |
| FL          |  3983.000 |          2174.000 |           0.546 |
| MD          |  1406.000 |           742.000 |           0.528 |
| NV          |   729.000 |           384.000 |           0.527 |
| NC          |  2686.000 |          1155.000 |           0.430 |
| NM          |   880.000 |           371.000 |           0.422 |
| CA          | 10159.000 |          4060.000 |           0.400 |
| NY          |  4893.000 |          1855.000 |           0.379 |
| LA          |  1350.000 |           508.000 |           0.376 |

Missing outcomes are excluded, never relabeled as zero. State is a major predictive feature, so reporting differences may contribute to the results. These are associations and same-year scoring results, not causal staffing effects or next-year forecasts. Comparing several training choices against 2021–22 makes this an exploratory comparison; an independent future evaluation is needed before treating the selected winner as validated.

## Verification and artifacts

- 105 existing tests passed (three existing pandas deprecation warnings).
- All seven runs have six saved model artifacts and complete five-fold metric tables.
- Re-scoring M5 in each run reproduced all eight saved test metrics to numerical tolerance.
- Full model comparison: `reports/baseline/comparison/temporal_test.csv`.
- Common new-school comparison: `reports/baseline/comparison/common_new_schools_M5.csv`.
- Model for the best overall observed result: `models/baseline/train_1516_1718_2021/M5.joblib`.
- Notebook dashboard: final section of `notebooks/baseline_model.ipynb`.

Rebuild the comparisons and verify saved models from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/summarize_baseline_runs.py
```

To refit the combined-years models in a new output folder:

```bash
python scripts/train_baseline.py --train-years 201516 201718 202021 --test-year 202122 --out-dir reports/baseline/combined_rerun --model-dir models/baseline/combined_rerun
```

Model artifacts, cleaned data, and detailed CSV reports remain local and git-ignored; this summary and the notebook's rendered tables preserve the comparison in the repository.
