# WT Cache Invalidation / AXI Read Response Repair

## Root Cause and Change

External invalidation takes priority over D-cache read capture in
`wt_axi_adapter.p_axi_rtrn_decode`. The original RREADY expression only
blocked internal atomic invalidation. Consequently an external invalidation
could coincide with an accepted AXI R beat while capture and metadata pop
were disabled. Losing the final beat leaves the read metadata pending.

The verification dependency now uses the FPGA package's functional repair:

```systemverilog
axi_rd_rdy = ~invalidate & ~inval_valid_i;
```

This is the only functional RTL change. Existing CVA6 fixes remain intact.
The canonical CVA6 patch and its registry digest include the change. The
AXI ID remap implementation is unchanged; its SHA256 remains
`299d6e889e54dd1d872e649608d66569f5c1bfc2d422903f985b75d4a4974a15`.

## Actual Paired VCS Results

Evidence directory: `verification/out/wt-inval-collision-20261015-01/`.
The executor exited 0. Sources remained unchanged during the experiment.
Both variants compile the verification branch's actual adapter, AXI shim,
FIFOs and configuration packages. The baseline adapter is byte-identical to
the pre-repair source, SHA256
`8141dfb8af2f098529b421a1b281bb167a74f4e79bcf7881a795aad3c286d3dd`.
The repaired adapter SHA256 is
`d3da46f4f86eaf238ceabd377734330214060a17d04cdbeeb9eb19f2a44de321`.

| Variant and scenarios | Results |
| --- | --- |
| Original, ordinary read without invalidation | 1/1 PASS |
| Original, invalidation overlapping each of four read beats | 4/4 expected failures reproduced |
| Repaired, D-cache read: five overlap positions including none, hold 1/4 cycles, with/without concurrent B response | 20/20 PASS |
| Repaired, I-cache read: none/first/final beat, hold 1/4 cycles | 6/6 PASS |
| Repaired, LR read: none/single beat, hold 1/4 cycles | 4/4 PASS |

There are 35 executions: five baseline observations and thirty repaired
tests. Expected baseline failures are not counted as passing functional tests.
For the original final-beat collision, AXI accepted four beats but captured
only three, produced no load return and retained pending read metadata.

The repaired first-beat collision with four consecutive invalidations and
a concurrent store records four accepted/captured read beats, one correct
read return, one AW/W/B transaction and one store ACK. Read, write and B
queues are empty at completion. The LR counterpart records one read return,
four external invalidations and its one internal atomic invalidation.

The normal D-cache control takes 39 testbench cycles in both variants.
All its `READ_CYCLE` and `COLLISION_RESULT` records match exactly. During
external invalidation the shared R channel is intentionally stalled; the
control comparison is not a claim of unchanged latency for conflicting work.

## Checks and Reproduction

The testbench samples with a clocking block and drives on falling edges.
It verifies payload and TID, AXI channel stability under backpressure,
capture/pop counts, invalidation returns, B buffering and store completion,
and empty metadata/response queues. It uses no internal force or synthetic
completion. Every case has a 3000-cycle limit and a 30-second wall limit;
each compilation is bounded to 180 seconds, without automatic retry.

The runner rejects fatal/error output even if VCS exits zero. Its checker
tests reject incomplete/duplicate success markers, wall timeouts and
unrelated baseline failures. Host tests: 11 runner/checker tests and 21
dependency-patch tests passed. Generated outputs and frozen inputs remain in
the evidence directory, not in the dependency source tree.

```bash
cd /home/wangwy/openproject/ara_dsa_signoff_integration
PYTHONPATH=verification python3 verification/cva6/run_wt_inval_collision.py \
  --output verification/out/wt-inval-collision-new-run
```

The output directory must not exist. This is actual-module verification,
not a new whole-SoC/Linux boot or attribution of every historical board hang.
The previous M9 image and its acceptance records remain tied to their frozen
sources; they do not include this newly added dependency repair.
