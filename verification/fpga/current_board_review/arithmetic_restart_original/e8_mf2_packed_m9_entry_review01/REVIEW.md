# E8 MF2 Full4095 M9 Entry

**NO_BLOCKER_ENTRY_REVIEW** for the exact frozen plan below. Aquinas is the
sole launcher under the parent's existing conditional authorization. This
review neither launches nor establishes DUT PASS or original Linux closure.

| Binding | SHA256 |
| --- | --- |
| prepared01/plan.json | 6ed1c1ffafeddb136962cf49ab10e761441e9bf3d24be67a71770a2245a2ea3f |
| result.json (machine-readable entry) | 0ea8cefcaab42f96730ed0f4a09db4843a336f658b093f5fb121a01e9d2bc6ed |
| Reference READY | 7327fc1457c47dc44f16c9d9f556251e3184058084486293d494d54d423f3f18 |
| Frozen M9 image.json | 48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a |
| Original accepted SoC ELF | 5e901ae235792e40de311713125a7a37a480a3e266c3a7c8d8d4887bb8433839 |

## Actual Evidence

Read-only metadata audit rehashed all796 plan pins, including source,
reference receipts, executable, immutable RTL, imported helpers and new
worker/checker. It exited0 (session24929, completion a5503b). Reference raw
was hashed only, not semantically reparsed. No Host, Spike, compile or DUT
execution was performed by this reviewer.

Stored new-worker Host25 passes: PID3098401 actual wait0,119.194513149s,
timeoutfalse,retries0,pinsunchanged. The118.512s unittest duration is not the
outer wait duration. Positive synthetic full4095 rows and negatives cover
all25 required target-owner deletions, five helper-memory owner deletions,
wrong owner/done, dropped transport, actual ABI, fresh initialization,
first-SH stale-shadow data, tail2/results/guards, return vstart, raw veto,
numeric-first0/17/timeout, and lateabort/postcheck failure. Synthetic rows
are explicitly not captured DUT execution or a scalar ISA emulator.

Dryrun contains exactly one M9 command, private input.elf, runtime ID,
NO_FSDB and commit_trace.csv. It is not a launch. Reference acceptance is
the previously reviewed sole parser execution: full4095,262080 results,
8190 guards,561831 firmware-through-HTIF, actual parser0/24.226s.

The first metadata-tool invocation exited1 before checking pins because
the local Python lacks hashlib.file_digest (completion bd0fb4). Only this
reviewer's hash helper was changed to streaming sha256; the subsequent
metadata audit exited0. No producer artifact, oracle, test or reference
was changed or rerun.

## Contract Review

- Exact original25 helpers,13 instructions each, capacityonce and all4095
  calls in source order; no prefix substitution, warmup or extra RVV/CSR.
  Existing binary-equivalent reconstructed C provenance remains distinct
  from unavailable original C bytes.
- CAP64/e8mf2/vtype7 occupies one128B physical register, but only low64B
  belong to the observed original group. Upper64B are neither asserted
  initialized nor checked. Gather/slide bounds remain original CAP, not VL.
- Every call initializes exactly66 output bytes. Actual compiled order is
  SH at offset64 followed by eight SD. Eight LD plus LHU at offset64 cover
  all64 results and both guards. Tail2 means result63 plus rear guard, not
  two architecturally exempt tails. Padding beyond offset65 is not read.
- All128 software mask bytes are initialized/checkable at each original
  group boundary; actual vlm reads8B. Original all/odd/mod7 mask modes are
  retained, not replaced with additional alloff modes. Fresh a/b per seed,
  mask per original group and output every call cannot be satisfied by
  stale but numerically equal shadow bytes.
- Actual-model owner requirement is20475 setup/store memory owners plus
  2610 nonempty-window targets =23085 minimum, including117 op24 memory
  targets. Qualification is vstart<vl, never predicate-population. The
  lossless six-event observer checks each architectural owner's alloc/done,
  not merely aggregate totals;1485 empty targets may be elided.
- Reset comes from pinned M9 FF-register facts (FpgaEn0), not invented
  unknown-GPR values. Actual startup/BSS/main/304B frame and return-address
  store are checked by Host. Actual retirement PC/code and decoded scalar
  addresses/data are used at runtime; CTRL0 exit is not Spike HTIF.
- Mature numeric-first worker persists actual child outcome before full
  checking. Generic and strict counts must match; raw failure veto,
  exact private ELF/input/command/image, final pins, late plan drift and
  sticky abort are enforced. The imported worker binds this checker via
  the process's checker module, not the historical mf4 checker.
- Direct service jobs1/case10800s/worker12000s/service13200s, no retry/build,
  cgroup termination and real ExecStopPost exit receipt are explicit.
  A300s metadata collector has360s stop allowance and does not reparse CSV.
  Fresh admission must satisfy total24 and MemAvailable>=32GiB, reserved0;
  this review does not claim an actual live-resource observation.

Estimated DUT cost1668.929s includes20% margin using prior403.97retire/s;
it is not a performance guarantee. The fixed case ceiling remains3h.
Only one bounded startup CPU/CSV-size observation is planned, then no
long-run polling. All sealed producer and previous acceptance files remain
untouched. No remaining entry blocker was found.
