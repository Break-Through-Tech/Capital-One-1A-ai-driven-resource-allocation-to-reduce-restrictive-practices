# Published experiment snapshots

`runs/*.json` contains validated aggregate metrics only. No school records or fitted
models are needed by the dashboard. Files are immutable and addressed by content hash.
Publish a new file to update results; keep older files to preserve presentation links.
The dashboard selects the latest successful snapshot of each experiment by default.

Existing snapshots were exported from the seven completed local baseline runs.
Their provenance notes identify reconstructed 2015–16/2020–21 inputs. Historical runs
lack input hashes in their original metadata; do not infer raw-data reproducibility.

`context.json` is a dated supporting analysis of 2020–21 outcome missingness and the
common new-school comparison, bound to specific snapshot IDs. It is not automatically
recomputed for new experiments and must never be attached to different snapshots.
