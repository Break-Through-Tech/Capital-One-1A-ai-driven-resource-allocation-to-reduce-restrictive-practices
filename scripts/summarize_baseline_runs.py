#!/usr/bin/env python
"""Verify saved baseline runs and consolidate their results without refitting."""
from pathlib import Path
import hashlib
import json

import joblib
import numpy as np
import pandas as pd
import train_baseline as tb

ROOT = Path(__file__).resolve().parents[1]
RUNS = ['.', 'train_1516', 'train_1516_1718', 'train_2021',
        'train_1718_2021', 'train_1516_1718_2021', 'cv_202122']


def main():
    base = ROOT / 'reports/baseline'
    out = base / 'comparison'
    out.mkdir(exist_ok=True)
    data = {year: tb.prepare_years([year], ROOT / 'data/processed', [])
            for year in ['201516', '201718', '202021', '202122']}
    seen = set().union(*(set(data[y].frame.combokey) for y in ['201516', '201718', '202021']))
    common = ~data['202122'].frame.combokey.isin(seen)
    results, common_results, cv_results = [], [], []
    for run in RUNS:
        folder = base / run
        info = json.loads((folder / 'run_info.json').read_text())
        summary = pd.read_csv(folder / 'metrics_summary.csv')
        cv = pd.read_csv(folder / 'metrics_cv.csv')
        assert len(cv) == 6 * info['cv_folds'], run
        assert not cv.duplicated(['model', 'fold']).any(), run
        assert len(summary) == 6 * len(tb.METRIC_NAMES), run
        model_dir = ROOT / info['model_dir']
        for model in info['models']:
            assert (model_dir / f'{model}.joblib').is_file(), (run, model)
        test = data[info['test_year']]
        assert len(test.frame) == info['test_rows'], run
        assert sum(len(data[y].frame) for y in info['train_years']) == info['train_rows'], run
        builder, model = joblib.load(model_dir / 'M5.joblib')
        scores = model.predict_proba(builder.transform(test.frame))[:, 1]
        metrics = tb.compute_metrics(test.target, scores)
        saved = summary[summary.model.eq('M5')].set_index('metric')['test']
        for name, value in metrics.items():
            np.testing.assert_allclose(value, saved[name], rtol=1e-10, atol=1e-12)
        label = ' + '.join(info['train_years'])
        if info['test_year'] == '202122':
            wide = summary.pivot(index='model', columns='metric', values='test').reset_index()
            wide.insert(0, 'training_years', label)
            wide.insert(0, 'run', run)
            results.append(wide)
            common_results.append({'run': run, 'training_years': label,
                                   **tb.compute_metrics(test.target[common], scores[common])})
        else:
            wide = summary.pivot(index='model', columns='metric', values='cv_mean').reset_index()
            wide.insert(0, 'training_years', label)
            cv_results.append(wide)
        print(f'{run}: complete; saved M5 metrics reproduced')
    pd.concat(results).to_csv(out / 'temporal_test.csv', index=False)
    pd.DataFrame(common_results).to_csv(out / 'common_new_schools_M5.csv', index=False)
    pd.concat(cv_results).to_csv(out / 'within_202122_cv.csv', index=False)
    roster = pd.read_csv(ROOT / 'data/processed/202021/schools_202021.csv', low_memory=False)
    states = roster.assign(missing=roster.seclusion_instances.isna()).groupby('lea_state').agg(
        schools=('missing', 'size'), missing_outcome=('missing', 'sum'))
    states['missing_share'] = states.missing_outcome / states.schools
    states.sort_values('missing_share', ascending=False).to_csv(out / '202021_state_missingness.csv')
    manifest = {}
    for year in data:
        path = ROOT / f'data/processed/{year}/schools_{year}_analysis.csv'
        manifest[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / 'input_sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(pd.concat(results).query("model == 'M5'").to_string(index=False))
    print('\nIdentical new-school cohort:')
    print(pd.DataFrame(common_results).to_string(index=False))


if __name__ == '__main__':
    main()
