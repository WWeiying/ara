# Gather11 Archived Context Recovery

## Result

No additional exact unreturned tuple recovered: **0/11**. This is a bounded check of the11 known recovery roots and their state/report/snapshot metadata, not a global assertion that no external dump exists. No CSV contents, active campaign outputs, UART replay, reference, compilation, DUT or RTL modification were used. Existing decoder and sealed evidence remain unchanged.

Under `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/`, the relevant roots are `rvv_recovery08_{154,155,168,169,171,172,173,175,176,177,178}`. Their4832 file names were inventoried; candidates were only boot `initramfs.cpio` and two `terminal_scene/batch_progress_000{1,2}/snapshot.{json,csv}` pairs per record. A boot archive is not captured process RAM. No GPR/stack/core/RAM dump attachment was located by this targeted inventory.

Across67 existing `state.json`, board report, terminal report, snapshot JSON and snapshot-command report files, no captured regs/GPR/stack/CSR/SATP fields were found outside source/input descriptions. All22 snapshot JSONs contain only core cycle/retirement/PC/trap counters, not the register file. Their marker is0 and every mailbox word is0. `last_pc/head_pc` are not a saved architectural halted context, and neither global retirement nor DDR last accepted addresses supply stack data or process page mappings.

`rvv_stall_handoff_permute01/index.json` identifies an actual instrumented trigger for **e16/m1 op16 vslidedown.vi**, and explicitly says the original uninstrumented trigger is unrecorded. Its `trace/` contains program sources/ELF/disassembly, not a saved CPU trace for these11 Gather records. That unrelated trigger cannot fill a Gather tuple. `stall_family_triage02/{ledger,triage}.json` remains a classification/source index, not a context dump.

## Recoverable External Location

R168 `terminal_scene/state.json` and `launch.json` identify the original observer machine directory:

`D:\fpga_runs\ara_rvv_recovery08_20261009_168`

The saved state is `stopped_review_scene`; its error is an observer-stopped PowerShell exception, **not a CPU exception stack dump**. The archived snapshot command is `snapshot`. The remote directory is a concrete place to ask for previously saved debugger/halt/core/RAM material; this review did not access it and does not assert that such material exists there. `evidence.json` records the other10 actual remote roots where available. Provide any original debugger-session transcript or attachment index from those roots, including external paths omitted from the local copy, before proposing another replay.

## Exact Missing R168 Material

Existing source binding is original `rvv_permute_restart_e8_m4_ops3`, ELF SHA256 `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`. The executable is already archived; another ELF rebuild cannot replace missing runtime state.

For the existing `../r168_context_decoder01/decode.py`, supply one authentic, same-incident captured context:

- Actual halted PC, SP/x2 and RA/x1. Decoder supports original helper PC1063e/10642 with caller RA103ce; board counter PCs alone cannot satisfy this requirement.
- Actual s4/x20, s7/x23, s8/x24, s9/x25 and a3/x13, a4/x14, a6/x16, a7/x17. These cross-check trial, scalar/length pointers, op, VL, capacity, scalar and vstart. In total the11 required64-bit fields including PC/SP/RA comprise88 bytes of values.
- **Exactly missing stack bytes SP through SP+31**, with the original virtual address and little-endian ordering: SP+0..7 mode; +8..15 seed; +16..23 capacity+1; +24..31 completed original calls. All32 actual bytes are required by the frozen decoder. Read-only original objdump confirms104d2 `ld a5,24(sp)` /104d4 `addiw a5,a5,1` /104d6 `sd a5,24(sp)`. The earlier follow-up's "32-bit count" wording is not the physical storage width; no sealed decoder was changed.
- Capture/run identity, actual ELF identity, and evidence that registers and memory were collected together before reset/exec/context loss. Optional actual vlenb CSR supplies another capacity consistency check.

If only physical DDR bytes survive, additionally provide the original stopped task's SP, SATP/page-table root, relevant page-table entries and capture-time association so SP..SP+31 can be translated. Last accepted bus addresses or a boot initramfs cannot establish that mapping.

Full VRF is not necessary to identify the current original call and its deterministic intra-child predecessors. Actual VID/request acceptance/completion/queue state is additional evidence needed for an RTL stall cause. For the other10 ELFs, preserve all x0..x31, PC and a reasonable caller-stack window (336 bytes for R168); verify each exact ELF's stack layout before applying offsets. Do not run the R168 decoder against another child or copy guessed register values.

## Limits And Next Action

R168's original returned-error print identifies a **returned** call, not the subsequent unreturned call. Its four recorded predecessor programs and exact Linux execution recipe are already available, but do not reconstruct the stopped process's GPR/stack/VRF state. Accepted numerical singles/prefixes likewise cannot recover historical state or close these11 stalls.

The next useful input is an existing original same-context regs+32-byte stack dump, a mapped RAM/core dump, or a debugger transcript pointing to one. Without that material, exact tuple recovery from the inspected archive is not possible; no further counter-based guesses or blind prefixes are justified. No new DUT is proposed here.
