"""Read the portable experiment contract without any training dependencies."""

from pathlib import Path
import hashlib
import json

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def load_snapshots(directory=DATA / "runs"):
    snapshots, errors = [], []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            item = json.loads(path.read_text())
            digest = item.pop("snapshot_id")
            expected = hashlib.sha256(
                json.dumps(item, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()
            if digest != expected or path.stem != digest or item["schema_version"] != 1:
                raise ValueError("unsupported or damaged snapshot")
            item["snapshot_id"] = digest
            snapshots.append(item)
        except (ValueError, KeyError, OSError, TypeError) as error:
            errors.append(f"{path.name}: {error}")
    return (
        sorted(
            snapshots,
            key=lambda x: (x["results_saved_at"], x["snapshot_id"]),
            reverse=True,
        ),
        errors,
    )


def latest_experiments(snapshots):
    latest = {}
    for item in snapshots:
        latest.setdefault(item["experiment_id"], item)
    return list(latest.values())


def year(code):
    return f"{str(code)[:4]}–{str(code)[4:]}"


def label(snapshot):
    info = snapshot["info"]
    name = " + ".join(year(y) for y in info["train_years"])
    return f'{name} → {year(info["test_year"])} · seed {info["seed"]}'


def scores(snapshot, evaluation="test"):
    frame = pd.DataFrame(snapshot["tables"]["summary"])
    return frame.pivot(index="model", columns="metric", values=evaluation).reset_index()
