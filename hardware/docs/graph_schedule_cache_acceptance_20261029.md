# Graph schedule and prepared-cache probe acceptance

## Paired result

`verification/out/graph-schedule-model-20261029-01` completed PASS.
Independent replay verified the raw log and all 1036 sealed inputs. This uses
the same Qwen3-1.7B Q4_K_M model, 40-token prompt, context 128, one CPU worker,
Q8_0/Q4_0 K-cache runs and Q8_0 V-cache as the preceding probe experiments.
Probe OFF and ON each perform six inference steps.

| Comparison | Result |
| --- | --- |
| Graph epochs and node counts | All six equal |
| Ordered fused-group boundaries and operation IDs | All 3894 groups equal |
| Native executor call shapes, order and statuses | All 472008 calls per mode equal |
| Prepared-cache snapshots after each graph | All 14 fields equal in every graph |
| Paired logits | 911616 words bit-exact |
| Selected tokens, FCSR and VCSR | Equal |
| Guest completion | Suite PASS, exit 0 |

The isolated CPU-loop copy buffers group boundaries and prints only after
the graph. It does not install an evaluation callback or split graph views.
The cache snapshot reads the existing inline worker state used by repack.cpp;
final ELF symbol inspection verifies a single shared TLS instance. Only the
CPU-loop archive member was replaced; the remaining archive bytes match.
There are no production-source, RTL or algorithm changes in this experiment.

## Final cumulative cache statistics, per mode

| Log field | Meaning | Value |
| --- | --- | ---: |
| s0 | Queries | 2208 |
| s1 | Hits | 1328 |
| s2 | Misses | 880 |
| s3 | Stored snapshots | 880 |
| s4 | Capacity evictions | 0 |
| s5 | Rejected cache requests | 0 |
| s6 | Allocation failures | 0 |
| s7 | Conflicting duplicate entries | 0 |
| s8 | Requested input-comparison bytes | 397672448 |
| s9 | Copied payload bytes | 49467392 |
| s10 | Producer computations on the cache path | 880 |
| s11 | Generic producer computations on that path | 0 |
| s12 | Retained snapshot bytes at final observation | 0 |
| s13 | Valid entries at final observation | 0 |

These counters cover the prepared-cache path, not every quantizer invocation.
They are cumulative within a child; retained bytes and entry count are
instantaneous state. Zero final retained entries is not absence of prior reuse.
Requested comparison bytes count candidate input lengths, including scans
performed by both get and put. Comparison can stop early, and memory caches
can absorb accesses. This number is neither physical DRAM traffic nor time.
Copied payload includes snapshot population and cached-output copying; it is
not just output-write traffic.

## Next hypothesis, not an accepted optimization

Current `value_cache::find` visits entries in slot order. Candidate keys contain
K, producer and format/control identity, but do not prioritize the M4 group that
previously matched. Different row groups often share those key fields, causing
unnecessary byte comparisons before the intended group is found. Existing
measurements justify investigation, not a promised speedup.

A conservative candidate is a preferred-entry hint for each M4 group. Search
that slot first, still check its complete key and exact input bytes, then fall
back to the unchanged full search on any mismatch. A stale hint must never
produce a hit by itself. Preserve cross-group duplicate reuse, replacement,
raised-flag replay, allocation-failure behavior and capacity. Do not replace
content validation with pointer/group identity or simply add a group key that
disables otherwise valid reuse.

Test the hypothesis on multiple real captured activation groups before changing
the production runtime. Required evidence: equal outputs/flags and hit/miss/
producer counts, fewer requested comparisons, and lower **complete preparation
cycles in VCS** with hint maintenance included. No claimed benefit may be based
solely on QEMU timing or the requested-byte counter. Reject or keep the original
implementation if actual full-call latency does not improve.

## Scope and provenance

This closes the probe's functional, graph-schedule and cache-count equivalence
for this model configuration. It does not establish hardware counter/retirement
equivalence or negligible probe overhead. Actual RTL cycle attribution still
requires an appropriate bounded paired measurement. QEMU counters remain
functional test evidence only.

| File within the run | SHA256 |
| --- | --- |
| `result.json` | `b2c28eb0e4b4fa5a2a1e1a02840cafd84eb3ca4c70becbdcaff72b05303e212b` |
| `qemu.log` | `bf6b2594b2817cff51a1ce6f32ac04f13823be524308464b0d26a4062c143d43` |
| `test` | `83cedb722a55a1dd0be7e71c803f50ba392a99ea62ccaef27970ad43f4c73b16` |
| `source-pins.json` | `fba00e24b4a9812a02614da8bde6e7dc374d582c80d1d7d0bc75bffc1fcd7d21` |
