# Reader-Held AR / Older SLVERR Gate

Review-stage testbench-only implementation. No VCS compile or simulation has been
launched. Canonical RTL, frozen helpers, old images and receipts are unchanged.
This is a directed integrated fault/drain test, not performance or MMU evidence.

## Why Before the Cut

The original `axi_cut` uses two-slot `spill_register` channels. The reader counts
AR acceptance before that cut and allows only two outstanding bursts. Holding
an AR after the cut alone cannot guarantee `reader.ar_stalled_q` while another
burst is outstanding. Do not treat cut-held traffic as this target coverage.

`reader_fault_cut.sv` wraps the original, unmodified `axi_cut`, at its slave side.
It gates both AR VALID into the cut and READY back to the VLSU, and both R VALID
to the VLSU and READY back to the cut. It does not store/generate response data,
change IDs, lengths, RLAST or data, bypass the cut, or change reader depth.
The two-entry observation ledger records real accepted requests only. Normal
traffic outside QBS command ordinal 2 is not restricted by that ledger.
The wrapper changes only the targeted beat's RESP from actual OKAY to SLVERR.
An independent bound probe checks handshake agreement, complete pass-through
payload/side-channel equality and upstream AR/R stability. Existing full-SoC
UVM monitors remain enabled on actual memory traffic; no trace filtering.

## Exact Scenario

Use the complete 71-command handoff program, retaining all 192 QBS word checks,
62 AKV resident row checks after external poisoning, capability checks, guards,
trap-PC/cause checks, scratch-register checks and normal RVV before/after.
`render.py` makes five exact main-source edits (plus protocol prefix rename),
with an inverse test: the second QBS uses its valid weights instead of address
zero; expected mtval becomes weights; an explicit address marker is added.
Trap cause remains load access fault 5; hardware reader fault must now be AXI
response 3, never old PMA 5 or validation. Original probe.S is reused unchanged.

1. Accept the first 144-byte Q4_K row AR in QBS ordinal 2. Gate subsequent ARs.
   Any earlier activation response still passes normally. Hold only the target
   response until it is the head of the actual accepted-request ledger.
2. Require the second row at weights+144 to be reader-held for at least two
   samples, with one real outstanding burst. Inject SLVERR on the target's first
   non-last R beat. Keep IDs/data/RLAST from actual memory and drain all 9 beats.
3. Hold the younger AR for six more cycles after older RLAST, when outstanding
   is zero but reader `ar_stalled` and `fault_pending` remain asserted. No fault
   terminal/owner release is allowed. Then admit the held AR and drain its 9
   real response beats without exposing payload/completion for the failed work.
4. Require exact reader fault identity, then engine fault terminal, then owner
   release. At the next AKV admission require empty reader/cut and write drain;
   its resident Q row must still match, followed by the original retry/context
   lifecycle and ordinary RVV checks. Context metadata is also checked across
   the fault and the other owner's first load.

The wrapper has a 4096-cycle directed-scenario bound. Profile captures 250000ns
(extend only after concrete evidence, never automatically); future wall timeout
is at most 900 seconds. Neither bound is a measured runtime claim.

## Private Preparation and Review

`prepare.py` validates snapshot-03 and the accepted handoff ELF build, produces
separate old/new full-SoC filelists and private VLSU copies, profile/TCL files,
and GNU/VCS command recipes. It executes neither compiler nor simulator.
Only the cut instance is wrapped; late-declared VLSU signals are connected using
new early-declared probe wires and assignments after all original declarations.
Baseline maps the three engine/VLSU overlay units back to pinned originals.
Every other original source/include/define/UVM unit remains in its original order.
Existing startup/libc/assembly objects are explicitly reused and hash-checked.

```sh
python3 -B verification/akv/reader_fault_gate/prepare.py \
  --snapshot verification/akv/shared_reader_integration/snapshot-03 \
  --fixture-build verification/out/reader-handoff-build-20261024-01 \
  --output verification/out/reader-held-ar-prepare-NEW
python3 -B -m unittest discover -s verification/akv/reader_fault_gate -p 'test_*.py' -v
```

After source/interposer review, a build executor must pin compiler dependencies,
fresh full-SoC source manifests and images. Resolve ELF `weights` (one 432-byte,
64-byte-aligned symbol whose first 288 bytes stay in one 4KiB page), pin
nm/ELF/disassembly, and pass the same address to
`+READER_FAULT_TARGET=<hex>` and the checker. Do not reuse an old accepted simv:
the injection wrapper is a new TB component requiring a separately identified
image. Two images share the exact successor ELF. No execution worker is enabled
by this preparation script.

Acceptance requires `check_log_and_cycles` (both semantic checks plus exact
fault-command AR/R counter association), actual simulator exit0,
unfiltered `ara_verify.uvm_dut` with backend/AXI/write checks, full source/image/
ELF pins before and after, and a bound FSDB export whose complete required
signal list matches `profile.py`. Partial log/wave helpers intentionally do not
return overall PASS. In particular, cut-held-only, no injected error, unknown
active controls, missing cycles, fake responses and missing resident recovery
are failures. Invalid-cycle payload X is not independently a failure.

Host tests are synthetic parser/transform checks, not SV elaboration, protocol
simulation or proof that the intended overlap was reached. Compile/execution
and old/new equivalence remain unverified until separately approved runs.
