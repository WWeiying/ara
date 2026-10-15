# Reopened P1: slideup source origin

This supplements the sealed mask-stream report. Its candidate lane hash was
`2f1899d5bcf14df84a7622678276619ce6bfbcfecdc6239072412d0fe7a86c99`;
that source is the **baseline**, not the final candidate for this investigation.
The earlier mask-only harness intentionally did not exercise slide source
addressing and therefore could not close this defect.

## Hypothesis and Measured Baseline

Current lane `SlideAddrGenA` inherits per-lane architectural vstart. The UP
branch only replaces the length; DOWN explicitly replaces the origin with
stride/NrLanes. `operand_requester.sv` adds
`vstart >> (EW64 - eew)` to the source register's VRF word base, even with
`is_slide=1`. That flag avoids subtracting vstart from the scaled length, not
from the address. SLDU's UP traversal starts at source position zero and
suppresses destination writes below architectural vstart.

Prediction made before editing: four lanes, e32, VL16/vstart8, slide1up must
request source word 32 but currently requests word 33. Its logical source
stream is shifted by eight elements. Destination element 8 therefore uses
vs2[15] instead of vs2[7].

`slide_source_v2_tb.sv` instantiated four real lane sequencers, four real
operand requesters (including their bank arbiters), and the real current SLDU.
The distinct memory pattern is `vs2[i] = 0x1000 + i`. Reads are driven from
actual granted bank requests; results are checked at actual requester VRF
write ports. The source origin is never replaced by a zero-origin fixture.

Baseline measurement for case 0:

| Signal | Value |
|---|---|
| SlideAddrGenA command | cycle 3, origin 2, length 4, EW32, scale_vl=1 |
| First source read, all lanes | cycle 4, bank 1, row 4, word address 33 |
| Lane 3 first word | 0x0000100f0000100b |
| Destination element 8 | actual 0x100f, expected 0x1007 |
| Completion | cycle 11; 8 wrong bytes; prestart bytes unchanged |

All 41 baseline cases finished: **13 predicted UP failures reproduced and
28 controls passed**. This run had no fixture compile/runtime failures.
The source data failure is independent of mask liveness: requests are unmasked
and complete normally despite returning wrong data.

## Narrow Repair and Results

Only the UP branch in `lane_sequencer.sv` changes:

```systemverilog
operand_request[SlideAddrGenA].vstart = '0;
```

DOWN's explicit stride-origin assignment and length calculations are unchanged.
The final candidate lane SHA256 is:
`60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0`.

**Fixed: 41/41 pass, zero data errors.** Case 0 emits origin 0/length 4,
reads bank 0/row 4/word 32 on all four lanes, and writes 0x1007 to element 8.
Completion remains cycle 11. All 41 completion cycles match baseline.
All 20 DOWN records are identical before/after, including data, source origin,
physical address, read count, and completion cycle.

Coverage includes slide1up, ordinary UP, slide1down, ordinary DOWN; e32/e64;
small-vector starts 0, 1, half VL and VL-1; and architectural starts 32 and 64
at VL128. Ordinary offsets include 1 and 8, and DOWN offsets cross whole source
word boundaries. Every accepted destination byte is compared, including
prestart/tail preservation. The test resets between cases.

## Evidence and Bounds

- Baseline: `verification/out/board-current-lane-source-v2-before-20261010/`.
- Fixed: `verification/out/board-current-lane-source-v2-fixed-20261010/`.
- Each has `status.json`, source hashes and snapshots, commands, compile/run
  logs, a runner snapshot, and a focused `source_origin.fsdb`.
- Both testbench hashes are
  `be2a7b105e0e0725d0fb25ada5d07cb5778b2c8171e52030163abc354bdb4b78`.
- The fixed runner verifies that only the lane production source differs from
  baseline, all input snapshots remain pinned, and the testbench is identical.
- Host VCS only; one simulator process for the entire matrix. Compile bound
  300 seconds, simulator bound 90 seconds, each case 160 post-issue cycles.
  FSDB stops after case 0, not after the entire matrix.

Re-run the candidate with the same frozen consumers:

```sh
python3 verification/fpga/current_board_review/lane/run_slide_source_v2.py \
  --frozen verification/out/board-current-lane-source-v2-before-20261010/snapshot \
  --out verification/out/NEW-lane-source-v2-fixed
```

The modeled parts are memory read contents and a finite post-read FIFO standing
in for the ordinary operand queue. This is stronger than a request-only check,
but it does not run the original Linux ELF, dispatcher, physical SRAM model,
mixed source/destination EEW conversion, alias dependencies, or masked slide
integration. It does not establish full historical board closure. Earlier
sealed helpers were not edited or relabeled as results for the new hash.
No commit or FPGA mirror edit was made. The new candidate is ready for the
parent's frozen integrated build.
