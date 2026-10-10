# GAP102 historical718 admission prepared, not executed

`admit_gap102_offline.py` does not launch simulations, DVE, or a collector.
It admits only the exact parent-reviewed attempt02 candidate after complete
PASS. A failure, absent raw127 increment, changed expected pin, wrong single
VDB or altered717 prefix cannot be admitted. Original GAP101 FAIL remains
excluded. No official DVE percentage or current RTL signoff is asserted.

Fixed inputs:

- Candidate: `verification/out/gap102-strict-candidate-717-20261006-01`.
- Run: `verification/out/gap102-widen-acc-cross-old-image-20261006-02`.
- Reviewed prepared seal:
  `7c9aed3b60eb2249e8555547bc81ac7d7b3b2e647fdbb4a01b35483aab6b4280`.
- Baseline: frozen `cache-port1-offline-admitted-717-20261006-01` admission
  manifest seal from the reviewed preflight, unchanged.
- Collector and test hashes are fixed in `COLLECTOR_PINS` and checked.

After the collector finishes and the parent reviews the candidate, supply an
independent canonical JSON file directly under `verification/out`. Its content
must be exactly the map `{absolute_candidate_artifact_path: expected_sha256}`
for all eleven names in `admit_gap102_offline.FILES`. Its SHA256 must be supplied
externally as `--review-seal`. The tool never creates this parent review map or
substitutes observed hashes for the supplied expectations.

Audit reuses the sealed full scalar/vector comparisons, requiring their exact
counts/no unknown skips, and re-reads actual commit/vector traces to reproduce
the full data and lifecycle oracles. It checks inherited full image/source pins,
all717 baseline pins, exact prepared/run identities and terminal success, then
independently reads the single VDB, reconstructs union/delta and validates the
target against source-bound compiled identity and actual raw bit. It does not
re-admit the historical717 software population from scratch.

Commands for later parent-authorized execution only:

```bash
python3 -m unittest discover -s verification/coverage -p test_admit_gap102_offline.py
python3 verification/coverage/admit_gap102_offline.py \
  --review-pins /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/gap102-candidate-parent-review-pins-20261006-01.json \
  --review-seal <PARENT_REVIEW_MAP_SHA256> \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/gap102-offline-admitted-718-20261006-01
```

Admission emits `admission-manifest.json` with output hashes and external review
binding. Parent independent revalidation uses the same arguments plus
`--verify --seal <ADMISSION_MANIFEST_SHA256>`; it reconstructs all outputs and
re-reads raw VDB instead of trusting a success string. No output overwrite or
automatic retry is provided. Until this command actually passes,718 is not
admitted.
