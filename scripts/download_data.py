#!/usr/bin/env python
"""Download the team's cleaned CRDC files from the GitHub release into data/processed/.

The files are too big for git, so they are attached to the release `data-v1`. Run it from
the repository root:

    python scripts/download_data.py          # the two files the baseline model needs
    python scripts/download_data.py --all    # every cleaned file

Files already present with the right SHA-256 hash are skipped. A download whose hash does not
match is deleted and reported, so a half-finished or changed file is never left in place.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("download_data")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "processed"
RELEASE_URL = (
    "https://github.com/Break-Through-Tech/"
    "Capital-One-1A-ai-driven-resource-allocation-to-reduce-restrictive-practices"
    "/releases/download/data-v1"
)
CHUNK_BYTES = 1 << 20


@dataclass(frozen=True)
class DataFile:
    year: str
    name: str
    sha256: str
    baseline: bool = False  # needed by scripts/train_baseline.py

    @property
    def relative_path(self) -> Path:
        return Path(self.year) / self.name


FILES = (
    DataFile(
        "201718",
        "schools_201718_analysis.csv",
        "4c0892743767bbfdfa24f26cd41eb550284cf2d1fc32f96c25402e19f9f8c3f6",
        baseline=True,
    ),
    DataFile(
        "202122",
        "schools_202122_analysis.csv",
        "be136e9031f6e4a5639e4f97c41df4fbe8c285cfcc0c7786ac1cf4f24f7b85ed",
        baseline=True,
    ),
    DataFile(
        "201718",
        "schools_201718.csv",
        "2a1fe1c873a8cc7fe60e7f79752c7d036e155095769cf2365d0391027556baaa",
    ),
    DataFile(
        "201718",
        "quality_detail_201718.csv",
        "6a3550d54c51a7864242add38e19f9a37d09ead964fc288044a919506f97784c",
    ),
    DataFile(
        "202122",
        "schools_202122.csv",
        "128321d64602047bc2951628af10209f8f6e2e8684a924f4bbb812acc8ca14f3",
    ),
    DataFile(
        "202122",
        "quality_detail_202122.csv",
        "6e2a83aab230f369505abf26404c738547af6bb42f38735160529785bbc6532b",
    ),
    DataFile(
        "201516",
        "crdc_2015_16_analysis_ready.csv",
        "efca32db215a27f890c5c83afd8cbd6fe795953124ee06c335236de46ce47459",
    ),
    DataFile(
        "202021",
        "crdc_2020_21_analysis_ready.csv",
        "90c2bd89057bc465bd608e386bb08526bce3dae39c23ee47f48a3ab00c584510",
    ),
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(file: DataFile, data_dir: Path, base_url: str) -> bool:
    """Download one file unless it is already there. Returns False if the hash is wrong."""
    target = data_dir / file.relative_path
    if target.is_file() and sha256_of(target) == file.sha256:
        LOGGER.info("ok      %s (already present)", file.relative_path)
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    url = f"{base_url}/{file.name}"
    LOGGER.info("fetch   %s <- %s", file.relative_path, url)
    with urllib.request.urlopen(url) as response, partial.open("wb") as handle:
        for chunk in iter(lambda: response.read(CHUNK_BYTES), b""):
            handle.write(chunk)
    if sha256_of(partial) != file.sha256:
        partial.unlink()
        LOGGER.error("bad     %s: SHA-256 does not match; file removed", file.relative_path)
        return False
    partial.replace(target)
    LOGGER.info("ok      %s", file.relative_path)
    return True


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the cleaned CRDC files.")
    parser.add_argument("--all", action="store_true", help="every file, not only the baseline's")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--base-url", default=RELEASE_URL, help="release download URL")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point. Returns the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    files = [file for file in FILES if args.all or file.baseline]
    failed = [file.name for file in files if not fetch(file, args.data_dir, args.base_url)]
    if failed:
        LOGGER.error("%d file(s) failed: %s", len(failed), ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
