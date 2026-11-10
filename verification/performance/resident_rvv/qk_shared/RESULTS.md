# Stage-3 Component Checkpoint

The implementation extends the existing resident PV datapath with FP32 QK
accumulation on the actual lane FPU. It reuses the lane-private 16 x 64-bit
accumulator array, the two reader entries and existing AKV Q/K/V storage.
No new arithmetic array, larger SRAM or wider external interface is introduced.
QK and PV remain experimental and unadvertised; normal runtime selection is
unchanged. This checkpoint does not establish complete Attention performance.

## Checked Evidence

All paths below are relative to
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`.

| Gate | Receipt | Verified scope |
|---|---|---|
| Original CPU dirty-state cause | `resident_pv_commit_dirty_20261110_03/report.json` | 72 WT/WB checks; original 23 dirty-state failures versus zero after the patch; other outputs equal. Original PV SoC reproducer still pending. |
| Synchronous resident reader | `stage3_reader_gate_20261110_01/report.json` | 232 normal scenarios, 128,048 accepted-data checks; four each of cancel/reset/invalid-command cases; real context and synchronous storage. |
| Central control and final-write accounting | `stage3_control_gate_20261110_03/report.json` | 43 scenarios, 12,078 checks; tagged stub lanes, stalled final acknowledgements and outstanding K-collector drain. Not an arithmetic test. |
| Actual shared FPU | `resident_qk_lane_fpu_20261110_01/report.json` | Standard/shared integer configurations each pass 26 controller scenarios against independent SoftFloat expectations and the unchanged ordinary-FP/coexistence suite. |
| Decoder and ABI | `qk_admission/test_admission.py` | 17 host tests, exhaustive control/register checks, default-off selection, no VRF source, preserved old operation IDs and generated contracts. Not whole-SoC execution. |

The FPU gate checks FP32 QK and existing FP16 PV, all five supported rounding
modes, signaling/quiet NaNs, inactive elements, odd tails, held outputs,
abort/drain, reset cancellation and reacquisition by QBS. Per arithmetic
configuration, 6,302 operations are accepted, 6,298 return, and four are
explicitly cancelled by reset. The original full-FP suite retains its checker.

The control gate holds ownership until the final accepted writes return their
acknowledgements. Cancellation during an uncancellable K gather retains the
lease until that gather drains. Its first two attempts remain recorded: both
failed testbench expectations, not proven RTL arithmetic failures. The third
attempt corrects the hexadecimal sentinel and the single-active-lane barrier
expectation without weakening completion, data or ownership checks.

Receipt SHA256 values at review:

```text
CPU:     2b297b1738ba1aea7e539a83ac6ade6dfd624168590d804fb211dec285b4872d
Reader:  ee15e86c3f52ff66c0acefda7bcb098e94d97a41e8f70ca31202481dbc6c2458
Control: b0099f9f0df97248f0147234e807dc828fd9736ebd3d6192c52349dc31d86e59
FPU:     f3673a5d5b406c7662b9378dc8cc7cdab11638543dcbfa02bbb54bc237459ef8
```

## Complete-Call Preparation

The smoke and ABBA firmware builds are complete, not executed:

- `stage3_attention_build_smoke_20261110_01/build.json`
- `stage3_attention_build_abba_20261110_01/build.json`

Both use the frozen real Attention input, D128, two query heads and 137 context
tokens split into 64, 64 and 9. The baseline retains panel-four RVV QK and
rotating-register PV. The candidate replaces both arithmetic leaves while
keeping preparation, online softmax, rescaling, normalization and final drain.
The unchanged oracle requires all output bits, flags and memory guards to match.
The new work checker additionally checks every resident operation, per-lane
accepted/returned FMA count, output byte-enable and architectural write.

## Still Required

1. Compile the committed production snapshot with accepted dependencies and the
   separately recorded CPU patch; no live dirty dependencies enter the build.
2. Re-run the exact original PV boundary ELF, then QK architectural boundaries.
3. Pass complete-call smoke before paired ABBA measurements. Report full-call
   cycles separately from resident-engine cycles; do not infer model speedup.
4. Make a measured retention decision and complete applicable runtime/fallback
   integration and version delivery. No FPGA or physical acceptance is implied.
