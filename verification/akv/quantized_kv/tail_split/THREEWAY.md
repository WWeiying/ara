# Threeway successor admission

`threeway.py` is a new worker. It does not modify or monkey-patch the old
`run_threeway_attention.py`, any existing build, or any old failed receipt.
It reuses the old build validator and terminal-input/UVM binder. The full
strided comparison remains a required, raw-rechecked same-profile/same-image
prerequisite tied to the exact predecessor of the H/S/B ELF.

The former single two-prefix tail run is replaced only by a checked combined
receipt from `combine.py`. Admission verifies its current pins, independently
replays all four raw split logs and UVM bindings again, verifies every consumed
input was in that combined receipt, and requires the exact four-way matrix and
accepted image. A single split PASS, build-only receipt, old TIMEOUT, missing
member or stale source cannot satisfy it. No gate-owner event wait is included;
invoke only after both prerequisites have completed. A parent-owned event
launcher may wait first, but must then execute this worker directly.

Example after full split acceptance, with fresh independent output:

```sh
python3 -B verification/akv/quantized_kv/tail_split/threeway.py \
  --build <existing-threeway-build> \
  --prerequisite <accepted-full-strided-run-of-the-same-format> \
  --tail-combined <tail-split-combined-output> \
  --output <new-independent-threeway-output> --timeout 10800
```

Use `--preflight-only` to check admission/image without starting simv. The
threeway executable, six ordered variants, numerical/work checker, trace
configuration, actual AXI/backend-write UVM gate, source/image pre/post checks,
direct process ownership and bounded cleanup retain the predecessor policy.
The maximum simulator timeout is still 10800 seconds. This successor does not
change H/S/B math, interpret unfinished runs as PASS, or infer a performance
result before a terminal independently checked run.

`test_threeway.py` uses only synthetic gate receipts and mock raw bindings to
test routing/rejection, plus clean-process CLI checks. These are host checks,
not numerical or SoC acceptance. The original tail and H/S/B sources remain
sealed. This file and the successor worker/tests are separate additions and
are not dependencies of the already pinned split ELF builds.
