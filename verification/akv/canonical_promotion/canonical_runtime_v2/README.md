# Canonical Runtime V2

Read-only ordinary runtime successor. Frozen `ordinary_runtime/run.py` SHA-256:
`85065e8784520c5e49db1b7ed26f97930a4ac48cd110ed0c0484390deddd2f8c`.
`checked_soc` uses the original code with private builder globals and mandatory
graph/build-v2 dependencies. Only that private builder namespace changes
`expected_graph`; no original helper module is monkeypatched. `run` is cloned
with only private `checked_soc` and `own_pins` replacements.

Build admission requires every `canonical_graph_v2.inputs()` path and the
explicit build-v2 `build.py`, `test_build.py`, `README.md` pins, in addition to
all original dependencies. Runtime pins additionally include this directory's
explicit `run.py`, `test_run.py`, `README.md`. Original exact ELF, raw replay,
protocol, per-call comparison, image identity and failure-state code is retained.
Receipts use `canonical_soc_v1`: the actual root/build workflow is unchanged.
An old failed worker is never relabeled PASS.

CLI matches the original: `python3 -B run.py --soc-build BUILD
--expected-soc-sha256 REVIEWED_SHA --output FRESH_DIR [--timeout 9000]
[--preflight-only]`. Parent template/root-cause review and approval are required
before EDA. This implementation does not perform source promotion.

Host tests: `python3 -B -m unittest discover -s
verification/akv/canonical_promotion/canonical_runtime_v2 -p 'test_*.py' -v`.
Mock finalization is software-only evidence, not an RTL PASS. Freeze after parent
approval and use successor files for subsequent revisions.
