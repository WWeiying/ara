# GAP102 attempt02 strict collector

Prepared offline only. No collector execution, simulation launch, rerun, or
admission is performed by this preparation. Parent owns the running unit.

- Fixed run: `verification/out/gap102-widen-acc-cross-old-image-20261006-02`.
- Parent prepared seal:
  `7c9aed3b60eb2249e8555547bc81ac7d7b3b2e647fdbb4a01b35483aab6b4280`.
- Frozen preflight, ELF, calibrated branch leaf, all66 image files and600s
  command are inherited from the reviewed prepared record, with conflicting
  expected hashes rejected. No extra preflight build or Spike invocation.
- Independent sealed Spike prefix:101339 instructions,74174 GPR writes,
  2495 scalar memory accesses,0 FPR writes. Boot ROM precedes the application
  entry and is not silently counted as application retirement.
- Strict vector comparison:35 instructions,6144 bytes, no unknown-byte skip,
  non-bitexact, trapped, incomplete, or unretired request. Independent software
  data oracle separately checks all4096 VRF bytes,1536 source guard bytes,
  two CSR snapshots,64 recovery guard bytes,723 checks and zero traps.
- Requests/responses and commit/vector backend allocations/completions must
  conserve; the one exact MAC must retire and execute. Independent tracer
  retirement prefix, exception absence and terminal tail are checked.
- Reread raw single VDB and fixed717 union; raw127 must actually newly hit.
  Native expression paths are not treated as measured coverage. No DVE.
- Rejection retains `failure.json`, known input pins and already-computed
  comparisons/bitmap evidence. No PASS status or admission is emitted on FAIL.
  A successful collection is only a proposed candidate, never admission718.

Tests, from the integration repository:

```bash
python3 -m unittest discover -s verification/coverage -p test_collect_gap102_strict.py
```

Only after terminal completion and parent review, the offline candidate command
is below. It must use a fresh output; no automatic retry or overwrite:

```bash
python3 verification/coverage/collect_gap102_strict.py \
  --prepared-seal 7c9aed3b60eb2249e8555547bc81ac7d7b3b2e647fdbb4a01b35483aab6b4280 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/gap102-strict-candidate-717-20261006-01
```
