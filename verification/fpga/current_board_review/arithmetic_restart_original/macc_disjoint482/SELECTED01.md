# Original vmacc Boundary Selections

Status: **HOST + SPIKE READY; NO DUT RUN; NOT PREFIX CLOSURE**.
Only the original trial481 single and immediately adjacent original480-481 pair
were prepared. Frozen `identity02`, `prepared02` (482-prefix), parent prefix5,
production RTL, and other agents' files were not modified.

## Identity and Scope

Original Linux ELF: `rvv_integer_macc_accumulators_restart_e8_m4`, SHA256
`608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d`.
`identity02/report.json` establishes byte-identical reconstruction of the entire
original ELF using the successor C plus archived S/header and original toolchain.
The lost original C text itself is **not recovered**; this is binary-equivalent
source, not a claim of original C byte identity.

The archived terminal trace printed completed480 at VL512/start1 and completed481
at VL512/start256. It establishes the software boundary, not internal acceptance
or a numerical failure. Both selections use seed0, original op0 `vmacc.vv
v24,v8,v16,v0.t`, e8m4, VL512, mask mode0 (all on), accumulator0 (all zero), rm0.
Inputs preserve the original xorshift RNG, edge replacements and b[0]=0.
All 13 original setup/target/store/return instruction encodings remain identical
in both SoC and Spike ELFs. Target encoding is `b5042c57`.

`prepare_selected.py` reuses the frozen runtime-only source and runtime. It counts
the original scalar loop tuples, skips before destination initialization/vector
execution/oracle, and stops after selected481 passes through the original checks.
It does not execute fake warmup or the skipped vector calls. Single skips0..480;
pair skips0..479 and executes480 then481, including the original destination
reinitialization between them. This is not cumulative accumulator history.
`selection.diff` records every source-selection change. Original `completed=`
prints now count local calls; explicit `MACC_ORIGINAL_TRIAL index=` retains the
historical index. The original summary's literal `seeds=5` is unchanged, but only
seed0 executes here.

Each call retains all512 output checks, two guard checks, and the original
returned vstart low32/high32 container checks. No additional fflags/vxrm/vxsat
sampling is claimed; the archived helper only reads vstart. All-on/full-VL/zero
accumulator means masked-off, tail, and dropped-nonzero-accumulator mutations are
inapplicable to these particular selected calls, not newly covered controls.

## Host and Spike Evidence

The complete host call rows match **both** frozen prefix and full-capture rows,
and the independent Python expected rows, exactly:

```text
CALL 480 0 512 1   0 cd3506418f2df673 56f1b2e31a7a93f5
CALL 481 0 512 256 0 cd3506418f2df673 5ccbbef2ede70eda
```

The first FNV64 covers all a/b bytes, 128-byte mask, old destination and guards;
the second covers the entire result and guards. These are complete-buffer hash
snapshots plus original scalar full-output checks, not stored byte-by-byte dumps.
Both positives pass. Each selection rejects active/prestart/left-guard/right-guard/
vstart-low/return-high corruption: **12 negatives rejected**. Seven terminal tests
per selection cover valid, contradictory PASS+FAIL, nonzero exit, incomplete,
wrong count, trap and wrong original index: **14 checker tests pass**.

Spike nonzero-vstart probe passes; ISA is `rv64gcv_zvl1024b`.

| Selection | Original calls | Spike instructions to replay_exit | Reference wall time |
| --- | --- | ---: | ---: |
| `macc_e8_m4_single481` | 481 | 1,940,068 | 0.3263s |
| `macc_e8_m4_pair480_481` | 480,481 | 1,396,805 | 0.2675s |
| Frozen full-prefix reference | 0..481 | 16,438,522 | 2.5792s |

These are separately compiled measured costs, not a linear per-call estimate;
the smaller pair count must not be interpreted as RTL speedup. No VCS budget or
success is inferred from Spike wall time.

## Handoff and Pins

Manifest: `selected01/soc/programs.json` (two exact entries, target PCs and markers).
SHA256: `dd868d52bf77a3eca62a452cfafb064fc436dec58254b9b1452a73ae758d22af`.

SoC ELF hashes:

- single481: `fba12e5cea7ec8f31b8189c7ff724a7cbc948da840a224c647ed6b57f9df4285`
- pair480-481: `53d6b25ae90f8fc83517c23f03c9e7e736d77a6ecfe83e9449c5ee60a22d33fc`

`selected01/pins.json`: **196 files independently rehashed PASS**, SHA256
`32dacfd6cff38120c536fac8da9fa4d86e79b22dd979baedfe8ff4bc9171f308`.
`selected01/complete.json`: SHA256
`0f3f7e38b10028de03716d8adda331efd2a73a01b00e004d96d1349a1de1fdf1`.
Parent inputs rechecked unchanged after preparation. Detailed host/reference
status, compilation commands, source diffs, disassembly, symbols, scopes and ELF
identities are retained beneath each selected case directory.

Preparation note: the initial helper invocation stopped before creating the output
directory because the imported SHA helper takes Path rather than str. Both pin
verification calls were corrected to wrap Path; no oracle/expectation changed and
no generated failed run was overwritten. There was one actual host/Spike build
of selected01. No DUT or production edits were made.
