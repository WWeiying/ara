# Final frozen directed results

Final pair, measured by host VCS V-2023.12-SP1 on 2026-10-09:

| Evidence | Original RTL | Final candidate |
|---|---:|---:|
| Output directory | `out/baseline_final05` | `out/candidate_final05` |
| Oracle-generated sequential operations | 4,950 | 4,950 |
| Additional overlapping pipeline operations | 576 | 576 |
| Flush recovery results | 5 | 5 |
| Accepted-work reset recovery results | 6 | 6 |
| Total result/tag/all-flags comparisons | 5,537 | 5,537 |
| Result/flags mismatches | 235 | 0 |
| Additional cancellation-state failures | 2 | 0 |
| Independent audit | FAIL, expected negative | PASS |
| Final simulated time | 486,240 ns | 486,240 ns |
| VCS reported simulation CPU time | 1.530 s | 1.550 s |

The two runs use identical fixture, oracle library, case JSON, case text, and
common dependencies. Their frozen input trees differ only in the five authorized
RTL files listed below. All 5,537 recorded per-operation wait/stream-cycle values
match between old and new. This establishes no latency change in this focused
test; it is not a whole-program performance, synthesis, or timing signoff claim.

Both VCS processes exited normally. Old failures are detected from actual
results and internal cancellation states, not from an assumed nonzero simulator
exit code. The final Python runner returns failure for the original RTL.

## Original failures retained

| Case family, including sampled pipeline repeats | Original failures | Candidate failures |
|---|---:|---:|
| Signed I2F boundary/overflow | 40 | 0 |
| Additional signed I2F regression | 12 | 0 |
| Explicit unsigned I2F | 34 | 0 |
| Cast UF boundary | 29 | 0 |
| MUL/FMA UF boundary | 84 | 0 |
| Nonzero-addend FMA | 18 | 0 |
| DIV UF boundary | 18 | 0 |
| Flush retained launch/done state | 2 | 0 |

The broad original source predates these changes but includes the previously
approved local repairs. It is frozen in `out/baseline01/inputs/fpnew`; the later
baseline run uses this source snapshot without reverting live dependency files.

`out/candidate01` additionally preserves the measured negative result of direct
upstream FMA boundary logic before adapting narrow destination bit positions:
48 failures, all FP16/FP32 on `fpnew_fma_multi`, with false UF. The final source
uses the actual super-format mantissa/tail layout, as explained in `README.md`.
Earlier runs are development evidence, not extra independent signoff tests.

## Observed control stress

| Actual DUT | Overlapping results | Max in flight | Blocked output cycles |
|---|---:|---:|---:|
| Cast multi | 78 | 3 | 52 |
| FMA multi | 252 | 3 | 168 |
| FMA FP32 | 82 | 3 | 54 |
| FMA FP64 | 82 | 3 | 54 |
| FMA FP16 | 82 | 3 | 54 |

Each of the 4,950 sequential operations also holds a valid result under output
backpressure for three cycles and checks data/flags/tag stability. Flush tests
exercise scalar launch delays 0/1/2/3 plus a vector completion waiting for peers.
Six additional tests reset accepted in-flight work, require no stale result, and
check a fresh operation afterward. These are observed functional checks, not
code-coverage percentages. The comparison also includes the separate nonzero
FMA addend that distinguishes pipelined RM from live input RM.

## Scope and preservation

- Only the five files below differ from the frozen pre-task FPnew tree.
- Previously dirty cast negative-boundary, unsigned-wrap, infinity, INT8 format,
  multifmt wrapper, and C910 rounding repairs are preserved.
- MVP is not changed. The upstream F2I status assignment is not imported because
  the local special-result selection already handles those overflows.
- No Ara RTL, registry, patch bundle, main-worktree file, or old helper was edited.
- No full-SoC regression, synthesis, Verilator, URG, or ZCC was run.
- Local offline tests: **20 PASS**. They exercise reference sentinels, INT8
  saturation, all flag-bit corruption, wrong IDs/tags, missing/duplicate traces,
  X results, incomplete completion, and simulator diagnostics.

The current source is ready for the parent's current-image integration smoke.
Unit evidence does not replace that integration run.

## Frozen hashes

Paths in the following table are relative to `hardware/deps/fpnew/`.

| File | Final SHA256 |
|---|---|
| `src/fpnew_cast_multi.sv` | `f6f8367472bc6edcddaf0edca70f9a9cfea1d76a0240e142ce8917899fa023ee` |
| `src/fpnew_fma.sv` | `ea20197ff471429defd9122bcce98fac708bff280986800183874872fc7688c8` |
| `src/fpnew_fma_multi.sv` | `73fee010682853487671fdbafda6b36553ca99fda91802bded7233ec9e51000d` |
| `src/fpnew_divsqrt_th_64_multi.sv` | `ed3cbc98654adba53bc74ae2e37f9341738806b81b82f0f84bb14a2a8301b8ce` |
| `vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_pack.v` | `df94dc248d8e3e4976cfdad861640abd344a1b9bcafa166eba4901c827bc13da` |

| Fixture/evidence | SHA256 |
|---|---|
| `run.py` | `ab249d92da8a819c1c6658f54675bd9ee9476ced07f9f1c210139020094d5728` |
| `oracle.py` | `9ad27e48f7e509d9f25749ba87b6bdfa7d0922995695432022687eb2ec44cdfd` |
| `upstream_tb.sv` | `af376daa6c35ca2ffedc73e558a4ae3919b0c98c361d3654fed9de82712f55c4` |
| `test_runner.py` | `d82d241f0a80f1fdb4b47d89cc4175af77b5122085e525ec490b8346c0828c6f` |
| `out/baseline_final05/audit.json` | `111b49dee15c966b255bc64d06f762504ede61a449ed54bcd900513a23104fd4` |
| `out/candidate_final05/audit.json` | `ddcacd90513ccbf1e754fbed6ddf390c1a01e7936a44873ab3531c7bb321fac8` |
| Final candidate executable | `09fd4e25733fa639b44a0ac66461eb715fa68144bdbb21a09eb066c31a44fea6` |

The final input manifests also retain the full hashes of every frozen RTL,
header, test fixture, and oracle input. `out/` is intentionally ignored by Git;
retain its raw local evidence or archive it separately rather than committing
simulator executables and generated C sources.
