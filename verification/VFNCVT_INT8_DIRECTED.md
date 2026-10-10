# FP16 to INT8 directed regression

Source: `apps/riscv-tests/isa/rv64uv/vfncvt_int8.c`. The only Makefrag change
owned by this task is the `vfncvt_int8` entry immediately after `vfncvt`.
No RTL, runtime, existing tests, or simulator source was modified.

## Frozen shard bundle (2026-09-26)

Bundle: `verification/out/vfncvt-int8-shards-20260926-01/`.
The final `manifest.json` has `status=PASS`, exact observed ordinals, counts,
compiler/source flags, executable hashes and golden log paths. `SHA256SUMS`
covers every input. All input files are read-only; no apps make was invoked.
Ara ELFs use the snapshotted existing `link_sim_2m.ld`, VLEN=1024, NR_LANES=4,
repo LLVM O3/lp64d/scalar flags, and privately compiled common runtime objects.
Golden ELFs use the same O3 test settings with the existing Spike harness;
function/data section splitting is disabled because its linker script does
not collect suffixed TLS sections. These are separate Ara and Spike ELFs.

Frozen test source SHA-256:
`8910876dc1fa436a11c852c37e65536219297c6caee319ddae8833a896dd9416`.

Selection is compile-time `VFNCVT_INT8_SHARD_COUNT` (default 1) and
`VFNCVT_INT8_SHARD_ID` (default 0). A zero-based ordinal is assigned BEFORE
preparation, input generation, vector execution, or reference work. Selection
is `ordinal % SHARD_COUNT == SHARD_ID`. Unselected cases only advance enumeration.
Failure messages use the original ordinal, not a shard-local counter.

The no-define default remains the original 384 cases. Enabling
`VFNCVT_INT8_EXTRA_BOUNDARIES=1` appends 80 singleton cases, preserving old
ordinals 0..383. The new patterns are `d800` (-128), `d801` (-128.125), `d802`
(-128.25), and `dbfc` (-255.5), each under all four opcodes and five frm modes.
The eight shards enable this option, so their union is the expanded 464-case
full suite, not a coverage reduction of that suite.

| Ara ELF under inputs/ | Cases | Byte checks | Golden -l records |
| --- | ---: | ---: | ---: |
| shard_0.elf | 58 | 4,600 | 310,063 |
| shard_1.elf | 58 | 4,030 | 285,063 |
| shard_2.elf | 58 | 4,030 | 270,063 |
| shard_3.elf | 58 | 4,030 | 285,063 |
| shard_4.elf | 58 | 4,600 | 310,063 |
| shard_5.elf | 58 | 4,030 | 285,063 |
| shard_6.elf | 58 | 4,030 | 270,063 |
| shard_7.elf | 58 | 4,030 | 285,064 |
| smoke.elf | 40 | 1,988 | 180,064 |

Every row is numerical Spike PASS. Each numbered shard checks 174 CSR fields.
The runtime case-ID bitmaps prove every ordinal 0..463 occurs exactly once
across the eight shards. Their totals match a separately executed full golden:
464 conversions, 33,380 byte checks, 12,452 active conversions and 1,392 CSR
field checks. Expanded full golden: 1,990,063 instructions. Default golden:
384 cases, original 33,300/12,372/1,152 checks, 1,970,064 instructions.

Smoke is a separate, deliberately overlapping subset, NOT a ninth partition:
20 mixed-input batches cover four opcodes x five frm modes; four full-VLMAX
mf2 geometry cases check fractional physical-register tails; 16 new boundary
cases cover four opcodes x four new inputs with frm=RTZ. It checks 1,732 active
conversions and 120 CSR fields. Build selection is
`VFNCVT_INT8_SMOKE=1 VFNCVT_INT8_EXTRA_BOUNDARIES=1` with shard count 1.
Smoke explicitly requires VLEN=1024 because its ordinal selection is fixed.

The frozen manifest field `spike_instruction_count` counts emitted `-l`
instruction records, NOT exact retired instructions. It includes golden
startup, test work, printf and host-interface polling, and one terminal-spin
entry. Spike compresses consecutive executions of the same PC; the terminal
self-loop's remaining executions have no final flushed repetition record.
Therefore the absence of `Executed N times` markers does not prove the absence
of suppressed terminal repetitions. No manifest/ELF/checksum was changed by
this clarification.

The 5000*N+63/64 pattern comes from this golden's `sim_t::INTERLEAVE=5000`
(`riscv/sim.h:67`), `sim_t::idle()` stepping that quantum, and
`fesvr/htif.cc:274` checking tohost between steps. Final printf waits on
fromhost until a host-service boundary. In shard 0, the final poll load/branch
are records 310001/310002; the 63-record suffix includes those two instructions,
print return, main return, exit handling and the first terminal self-jump.
The suppression logic is in
`riscv/processor.cc:549`; the runtime spins after writing the exit request in
`benchmarks/common/syscalls.c:56`. The analogous suffix can be 64 depending on
which poll-loop instruction spans the service boundary.

Offline counts from entry to main through the call of its FIRST summary
printf (excluding the printf body, startup and exit) isolate the completed
test work: shard 0..7 respectively 272657, 244428, 231403, 244138, 272571,
244598, 231621, 244465 records; smoke 147057. Every numerical check precedes
that first printf on these passing runs. These are still Spike test-body
records, not the distinct Ara ELF's retired instructions or DUT cycles.

At 700 cycles/sec and a hypothetical 1 CPI, using whole-trace records gave
about 443 seconds for the largest shard and 257 seconds for smoke. These are
only rough planning figures, not cycle measurements. Allow additional
CPI/throughput margin; no 600/900-second RTL completion is claimed.
No VCS was run, and no RTL runner/timeout was changed. At most five parallel
RTL processes remain under the caller's control.

Reproduce into a NEW output directory, without touching shared apps outputs:

```sh
python3 verification/build_vfncvt_int8_shards.py \
  --output verification/out/vfncvt-int8-shards-REBUILD
```

The script snapshots test/runtime/header/linker inputs, builds nine Ara ELFs
and eleven golden ELFs sequentially, records all argv in `commands.json`,
runs/checks golden traces, verifies observed partition IDs and counts, and
freezes inputs only after success. It refuses an existing snapshot/manifest.
The original full golden ELF is untouched at its original apps path and is
also preserved under `inputs/legacy/`, with its original source and notes.
Two failed host setup attempts are retained outside inputs for audit: the
Spike linker-section mismatch, and a Python 3.10 hash API compatibility fix.
Neither involved a test source change, coverage change, or RTL execution.

## Previous full golden provenance

The remainder describes the previous unsharded source/checksum, preserved in
the bundle's `inputs/legacy/`. Its counts are historical, not shard counts.

- Source SHA-256: `471f7803adfd5af1828d82a1732c5cb39fdf9f40ca4cc37485be15e41c9f7fd4`
- Spike ELF: `apps/riscv-tests/isa/rv64uv-p-vfncvt_int8`
- ELF SHA-256: `bfa58c0ff26384a594ebf75a52f4f08ad7f189bf8a3937251ef7ba44dca4552e`
- Compiler: repo `install/riscv-llvm/bin/clang`, LLVM 22.0.0git,
  revision `d92671cf7dc316730e7bacba04b642e70059d640`; no ZCC.
- Compiler executable SHA-256: `c9e4459570b10dc31a2e9ed6006ae0484580ae19b2b77e7451687d8f52705795`
- Golden: `/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike`
- Golden source HEAD: `f1e3bde8eba74c12d21679096bc26461f4214d1d`, clean worktree.
- Golden executable SHA-256: `c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`

The repo's legacy installed Spike rejects nonzero-vstart arithmetic. The
existing verification golden explicitly enables `VU.vstart_alu` in
`riscv/processor.cc`; do not drop restart cases to accommodate the legacy binary.

## Reproduce

From the worktree root:

```sh
make -C apps/riscv-tests/isa rv64uv-p-vfncvt_int8 \
  RISCV_LLVM="$PWD/install/riscv-llvm/bin/clang -fuse-ld=lld" \
  RISCV_CC_DEFS_C='-DVLEN=1024 -DNR_LANES=4'
/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike \
  --isa=rv64gcv_zfh_zvfh_zvl1024b \
  apps/riscv-tests/isa/rv64uv-p-vfncvt_int8
```

The non-Spike source also compiled warning-free with the repo's Ara O3,
lp64d, scalar-code flags to `/tmp/vfncvt_int8-ara.o`. No shared runtime build
was started. The future standard Ara target is
`make -C apps bin/rv64uv-ara-vfncvt_int8 zcc=0`; this was only dry-run here.

## Checks and results

All four instructions (`x`, `xu`, `rtz.x`, `rtz.xu`) run under all five legal
`frm` modes. Raw half inputs are decoded using integer significands, shifts,
remainders and rounding, then checked against the rounded signed/unsigned
range. Each invalid element contributes NV but not NX; valid inexact elements
can independently contribute NX. No host or scalar floating-point arithmetic
is used. Semantics follow the [RISC-V vector conversion specification](https://docs.riscv.org/reference/isa/v20260120/unpriv/v-st-ext.html).

At VLEN=1024, the exact breakdown is:

- 80 batches: 20 each of mixed (73 elements), exact, fraction-only, and
  invalid-only (16 elements each).
- 160 singleton boundary checks: 8 half patterns x 4 opcodes x 5 rounding modes.
- 144 geometry cases: 6 LMULs x 4 opcodes x 6 policies. Destination mf8 through
  m4 uses source mf4 through m8, disjoint v8..v15 and v24..v27 register groups.
- Policies: full-VLMAX mixed; masked exact with restart/tail; unmasked exact
  with restart/tail; all-masked; vstart greater than VL; VL zero. Skipped inputs
  alternate signaling NaN and 0.5 to detect unintended NV/NX. Seeded DZ checks
  sticky flags. Full physical-register tails are checked at fractional LMUL.
- 384 conversions, 12,372 active element conversions, 33,300 byte comparisons
  (including 20,928 undisturbed bytes), and 1,152 CSR field comparisons:
  384 each for fflags, vstart reset, and frm preservation.

| Golden VLEN | Cases | Byte comparisons | CSR field comparisons | Result |
| --- | ---: | ---: | ---: | --- |
| 128 | 464 | 6,420 | 1,392 | PASS |
| 1024 | 384 | 33,300 | 1,152 | PASS |
| 4096 | 384 | 125,460 | 1,152 | PASS |

Small VLEN stripmines the same corpus. The source supports up to VLEN=16384,
but this golden rejects VLEN above 4096, so larger configurations are untested.
Half patterns `d800` (-128) and `d801` (-128.125) are currently mixed-corpus
only; `d804` (-128.5) and `d807` (-128.875) have isolated flag checks. The user
requested two additional isolated patterns after freeze; these are NOT added
to this checksum. Adding both would increase the default count to 424.

## Runtime evidence

The same frozen ELF passed again with golden `-l`. Artifacts are
`/tmp/vfncvt_int8-final.stdout` and `/tmp/vfncvt_int8-final.trace`.
The trace contains 1,920,063 instruction records and exactly 384 vfncvt records;
the other 680 lines are symbol annotations, with no trap/repetition records.
This includes the Spike harness, not an Ara cycle measurement. At an assumed
1 CPI and 700 simulated cycles/second, this suggests about 46 minutes, not a
600/900-second run. Actual Ara O3 code, CPI, and simulation throughput differ.
No VCS execution, RTL timeout adjustment, or coverage reduction was performed.
