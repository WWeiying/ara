# NV Qualification After Source-Origin Repair

Terminal: **host464 checks PASS, Spike8/8 PASS, candidate04 VCS8/8 PASS**.
See [DUT_REPORT.md](DUT_REPORT.md) for exact flags and acceptance identities.

Eight **new directed successor controls**, not archived original cases. The
original three controls, their sources, pins, and reports remain unchanged.
No production edits or image build. Sources and ELFs freeze after host/Spike.

## Static Contract

Audited immutable candidate04 sources under
`/home/wangwy/fpga_runs/current_board_memory_candidate04/frozen/sources`:

- `hardware/src/lane/lane_sequencer.sv:1028-1077`: comparison operand streams
  now start at zero while architectural vstart remains16.
- `hardware/src/lane/vmfpu.sv:1222-1258`: classifiers tag dense per-element NV;
  EQ/NE use signalling NaNs, LT/LE use any NaN, considering both operands.
- `vmfpu.sv:1542-1589`: tag bits travel as result bit2 alongside bit0;
  lane aggregate comparison fflags data and valid remain suppressed.
- `hardware/src/masku/masku_operands.sv:226-242`: NV and result use the same
  EEW/vrf_pnt compression; NV defaults zero outside the current slice.
- `hardware/src/masku/masku.sv:796-809,448-465`: exact architectural
  `[vstart,vl)` window and predicate qualify NV on accepted comparison results.

Origin0 does not bypass these gates. It restores the element identity to which
both result and NV qualification apply. Prestart index5 is computed but filtered;
masked-off17 is filtered by predicate; active21 qualifies; tail37 must not raise
NV. With this aligned VL32 the tail lies outside the consumed source words,
which also discriminates the old incorrectly advanced stream. This is not a
tail-within-partially-consumed-slice test.

The earlier candidate04 FP3 evidence used only finite inputs and cannot prove
NaN qualification. No existing exact-ELF candidate04 evidence for these new
NaN cases was substituted for actual reference/DUT checks.

## Fixed Cases

All e16/m1, VL32, vstart16, tu/mu, v24 result, v8/v16 sources, v0 predicate;
64 source elements and the full1024-bit result register are checked. Exactly
one NaN is present per case. All other values are positive FP16 ONE/TWO.

| Case | Op | NaN input/index | Bits | Exact final fflags |
| --- | --- | --- | --- | --- |
| prestart_snan_eq | EQ | lhs5 | 0x7c55 | 1 |
| inactive_snan_eq | EQ | rhs17 | 0x7c55 | 1 |
| active_snan_eq | EQ | lhs21 | 0x7c55 | 17 |
| active_qnan_eq | EQ | rhs21 | 0x7e55 | 1 |
| active_qnan_ne | NE | lhs21 | 0x7e55 | 1 |
| active_qnan_lt | LT | rhs21 | 0x7e55 | 17 |
| prestart_snan_le | LE | rhs5 | 0x7c55 | 1 |
| tail_snan_lt | LT | lhs37 | 0x7c55 | 1 |

Sticky NX=1 is initialized before every target. Fflags17 means NX|NV, not
unrestricted nonzero flags. Frm=1 and vcsr=5 must remain unchanged; pre/post
VL32/vtype8 and vstart16->0 are checked immediately around the target.

## Independent Data And Flag Oracles

Finite golden truth derives from literal `0x9e35c692396d58b3`, with bitwise
complement for NE/LT and one explicit ISA unordered-result override at the NaN
index. Neither golden data nor expected flags are inferred from DUT values.
The host model independently classifies actual binary16 inputs and compares
finite positive encodings to validate the generator and every golden bit.

Predicate bits16..31 are0xd6ad; index17 is off,21 is on. Active truth differs
from a wrongly advanced source at9 or10 selected positions in every case.
Thus a periodic NaN pattern cannot hide source-origin errors. Prestart and
masked-off bits must equal old vd. Tail permits only old/one or computed mask
result within VLMAX64. Full predicate, both complete source arrays and memory
guards are checked. Output separately reports data/setup/CSR/flag errors.

Host:8x58=464 positive/negative checks PASS, including all body-bit mutations,
all five fflags-bit mutations, CSR/source/predicate/guard/tail mutations and
shifted16 wrong-stream rejection. Spike:8/8 PASS, explicit
`rv64gcv_zvfh_zvl1024b` plus the established nonzero-vstart probe.

Artifacts: `host01/results.json`, `reference01/reference.json`,
`prepared01/provenance.json`, `soc01/programs.json`. The latter is the reusable
SoC manifest. HTIF and SoC ELFs necessarily differ by runtime backend; both
derive from the same frozen test C/S. No test rebuild occurs for DUT replay.

## DUT Policy

`run.py` reuses the sealed candidate04 image and existing integration runner,
jobs1,180 seconds/case, at most8 cases. The runner stops on the first failure;
no timeout changes or retries. One admission gate enforces cap24, reserves up
to2 unoccupied NF7 slots, and requires32GiB available. Strict completion,
exact markers/flags, raw failure veto and private input/image pins are checked.
No FSDB. A terminal report, not launch or partial progress, determines DUT PASS.
