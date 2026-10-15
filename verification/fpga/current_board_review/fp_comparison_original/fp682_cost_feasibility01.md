# FP Alias682 Cost Feasibility

**Decision: HOLD under the three-hour limit. There is no post-target empty
enumeration to remove.** The old roughly8-hour estimate is consistent with the
existing source, compiled loops, measured reference retirement count and accepted
130-prefix DUT rates. It is an extrapolation, not measured682 M6 walltime or a
guaranteed bound. No compilation, Host/Spike/reference/DUT execution, live-process
query or large trace reparse was performed. Only this report was written.

## Exact Program And Scope

Original parent: `rvv_fp_compare_unmasked_alias_v8_e16_m8`, archived at
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions45/binaries/rvv_fp_compare_unmasked_alias_v8_e16_m8`.
The actual archived ELF and retained `original_rebuilt.elf` both hash to
`266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
Recovered original C hashes to
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`;
the actual archived assembly and retained `original/scenario.S` both hash to
`eb5659c77622636492675c2ffd77b2e1a2fc93ede9471013d123f54151a02f86`.

Prepared case: `prepared02/prepared/alias_v8_e16m8_prefix682/`.
It is e16/m8, CAP512, destination v8 alias, **unmasked**, nonrestart, boxed scalar.
It keeps682 total calls (681 predecessors before the last call), including the
original call50 data-error context and later call681/682 flag-error contexts.
Last call: seed1/op2/VL1/mask-mode0/sticky1/vstart0, historical expected flags1,
actual17. These are genuine recorded contexts, not a newly invented tuple.
Full parent17920 calls and original Linux execution remain outside this prefix.

`call_sequence.json` independently counted: op0/1 each112, op2=66, op3=56,
op4..9 each56;346 vv and336 vf calls. There are349184 result-bit checks,
1364 guard checks,682 returned-vstart checks and682 exact flag comparisons.
All calls are retained, including104 VL0 calls. The source does not use a mutable
PRNG: `lhs_index`/`rhs_index` deterministically derive table indices from seed/i/op
(`case.c:31..35`). No seed/input generation was replaced or approximated here.

## Empty-Enumeration Hypothesis Rejected

- `case.c:40..43`: ordinary seed/op/length/mode/sticky loops; no selected-tuple
  filter or `continue`. Every entered body initializes inputs/output, calls the
  original helper and executes the full oracle.
- `case.c:47..53`: fills all128 mask bytes, both512-element input arrays and
  all130 output bytes **on every call**.
- `case.c:58..84`: helper followed by full-CAP scalar oracle, flags and guards.
  Checking only VL would remove required preserved/tail/alias-result checks.
- `case.c:92..95`: immediately after the completed oracle, `++cases` and
  `if(cases==682) goto prefix_done`. No remaining seed/op matrix is enumerated.
  Compiled SoC PC `0x800003d4` branches directly to summary at `0x8000048a`.
- `prepare_prefix.py:96..103` inserts exactly that after-oracle stop.
  Its Python tuple construction enumerates the full parent then slices682
  (`:115..123`), but that is preparation-time work, not code executed on DUT.
- Mask-mode3 does not make this unmasked comparison inactive. It still loads v0
  and the original helper still runs. VL0 is also not a no-target/no-state loop:
  full source loads, VL changes, flag save/restore and result-mask store remain.
  Dropping these calls would remove original architectural/register-layout history.

## Where Retirements Go

Existing compiler command is `-Os`, no scalar autovectorization, original
assembly and full scalar oracle; no new compilation was performed. The following
are **static counts from the retained compiled loops**, not a measured per-PC
profile or a claim about RTL stall-cycle attribution. For the zero-error path,
let N=682*512=349184, V=346*512=177152, active=123362, tail=225822.

| Existing work | Instructions / lower bound | Compiled SoC evidence |
| --- | ---: | --- |
| Fill both complete a/b arrays | 7513772 exact | `0x800001c2..200`, backedge `3fa..3fc`;20*N-2*682+3*V |
| Full512-bit oracle | >=11662176 | `0x80000294..2e0`, backedge `3fe..400`, tail `402..42a` |
| All128 mask-byte initialization | 654848 exact | `0x8000018e..1a4`;512 nonzero-mode calls*128*8 +170 mode3 calls*128*6 |
| All130 output-byte initialization | 354640 exact | `0x80000216..220`;682*130*4 |
| Original helper bodies | 12592 exact | vv16/vf21 instructions per call, including target/load/store/CSR/ret |
| **Subtotal lower bound** | **20198028** | Excludes call setup, loop selection, flags/guards, summary/startup/runtime |

Oracle minimum is `25*N - 2*682 + 3*V + 3*active + 9*tail`.
The common per-bit path and backedge cost25 (minus final backedges); vv lookup
adds3. Active checking adds3; preserved/tail old-value checking adds at least9.
Nonzero-VL allowed-tail alternatives can add up to2 more per tail bit;53248
tail bits belong to VL0 calls. Thus this loop's zero-error range is
11662176..12007324 instructions, without assuming which permitted tail value
the DUT chooses. Wrong results/diagnostic output need not share this cost.

SoC and Spike main PC maps are **not identical**: Spike main starts0x800000e0,
SoC0x800000d8. Comparing their main mnemonic sequences finds two removed
`auipc` instructions outside these counted loops; the input/oracle/initialization
loop counts above are unchanged. Helper bodies remain16/21 instructions.
The subtotal is99.6927% of the measured reference retirement count. Even granting
all remaining62260 instructions for free would barely change the estimate;
those remaining instructions are not established removable empty enumeration.

Vector instructions can have nontrivial latency despite their small retirement
count. There is no682 DUT timing/profile proving the walltime split between
vector stalls and scalar work. The evidence nevertheless excludes a large
post-target scalar filter loop as the explanation for the instruction cost.

## Measured Cost And Three-Hour Test

`budget01/alias_v8_e16m8_prefix682.log` records minstret5 at `_start`,20260293
at `replay_exit`, return a0=0 and the original682/errors0 PASS markers:
**20260288 retired instructions**. ISA was `rv64gcv_zvfh_zvl1024b`; this used
the retained Spike-specific ELF, not the SoC ELF. No count was remeasured.

The accepted M4 `candidate04_restart_run04/replay/summary.json` and
`TERMINAL08.md` supply the actual comparable timings below; their large CSVs
were not re-read. The terminal complete hash still matches the accepted report.

| Accepted130-prefix | Actual DUT retirements | Simulator seconds | Retirements/s |
| --- | ---: | ---: | ---: |
| Masked e16/m2 | 1147283 | 1647.3071881979704 | 696.459657 |
| Unmasked e16/m2 | 1146548 | 1633.254851676058 | 702.001894 |

At those rates682 costs **28860.73..29090.40 seconds,8.02..8.08 hours**.
Its counted subtotal alone gives7.99..8.06 hours at the same assumed rates.
Meeting10800 seconds with the existing retirement count would require at least
**1875.95 retired instructions/s**, before extra validation/teardown, or removal
of **12678668..12738524 instructions (62.58%..62.87%)** at the measured rates.
There is no removable empty loop of that magnitude. M4 e16/m2 rates are not M6
e16/m8-alias measurements; concurrency, vector latency and Spike/SoC runtime
differences prevent interpreting this extrapolation as an absolute lower bound
on walltime. No current M6 throughput guarantee is asserted.

## Feasibility / Action

No compliant empty-enumeration-only successor is justified. Reordering/removing
repeated initialization, precomputing or rewriting the scalar oracle, skipping
VL0/mask modes, splitting history, shrinking CAP or replacing the helpers would
be different transformations from the requested no-target/no-state cleanup.
Even eliminating *all* input-fill instructions, which is not authorized, leaves
over12.7M reference instructions, about5 hours at these rates.

Keep the current682 ELF and full oracle **HOLD_NOT_RUN**. Do not budget on an
assumed early failure or launch a three-hour trial hoping for a throughput gain.
No software edit, compile/reference experiment, new framework or DUT run is
recommended within the present constraint. The remaining original alias history
gap stays open; accepted130 prefixes and earlier call50 evidence do not close it.

## Selected Identity Pins

| Artifact | SHA256 |
| --- | --- |
| `prepared02/soc/alias_v8_e16m8_prefix682.elf` | `82831408882d97d62b20e4e3b5e9a431f97ecbe0b0261091ffd663d0af546b1a` |
| `prepared02/spike/alias_v8_e16m8_prefix682.elf` | `c3826fc2f35192eaa3d3148f15b261f6022ec39aa9d6f42e7ea988fe0078e296` |
| Prepared `case.c` | `6c4cb874c4ee73ccfd58d210234940e0e1981472a39485b616b292d19e977b46` |
| Prepared `call_sequence.json` | `4d4db26c6350a78e8eeb8def92e157439ddba9db2bd8b2710a158376e411dfd5` |
| SoC `.dis` | `637e24d5dc1f32370081c5ab7cefacc0a48ddc583a5fbf9862e2a8576ef78437` |
| Spike `.dis` | `6f991d7fa2a43dfb1cad580fea5f06ca8ddcc1939844694ab3fb0cd6d260f8f1` |
| Existing682 budget log | `83fa02e132279cf9c7255cfc1615437443503e3373c3ae687d60f716e22ff2dc` |
| `candidate04_restart_run04/complete.json` | `ef2eb50bdf0e4f4eb35e9af794d2fdf26cca99286623723818507265ab650747` |
| Same run `replay/summary.json` | `ba2c9cad981e226217175dd944ff16ce76ef9dd9ee2b9f95b030faf235e56162` |
| `TERMINAL08.md` | `ca53bbe17a0e89adf180bd016aa18cd24a4c08bc35c94de298b73f47f643e165` |
