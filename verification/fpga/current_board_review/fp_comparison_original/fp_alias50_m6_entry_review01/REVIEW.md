# FP Alias First50 Source/Input Entry Review

Decision: **NO BLOCKER WITH EXPLICIT PROCESS-EVIDENCE LIMITS.** Accept these source-faithful first50 software/checkpoint-reference inputs for subsequent worker-plan preparation/review. No DUT acceptance or launch authorization. This review read source, ELF bytes, generated checkpoint summaries, Host metadata and recovered tool evidence; it did not open/reparse the raw reference or run Host, Spike, a compiler or DUT.

Producer: `../fp_alias50_m6_prepare01`. READY SHA256 `feae4a0dc86ea2e5222655469f574634eaae03741d777bb015f71af6644ee004`. Recovered qualification: `recovery_provenance01/receipt.json`, SHA `4754dcb245bea03b836e57b607981efe3ba9ea398c874dfe710c1f752ebcc4e0`; companion README SHA `6d5a5f2cd3fcb9ed992be6b904c96c61f15cc0727d534ad2866a286dd9184f45`. Bind this supplement alongside unchanged READY; do not silently promote its old rc0 field into a durable child wait receipt.

## Authentic Source And History

Original parent is `rvv_fp_compare_unmasked_alias_v8_e16_m8`, not a historical diagnostic replacement. Recovered C SHA `3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`; original Linux ELF and existing full-parent rebuilt ELF are byte-identical at SHA `266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`, also matching the original family manifest. No new rebuild was performed.

Only a stop after the complete original call50 oracle and a label are inserted into original C. Removing these two lines exactly restores the original; source oracle block SHA `603ef982f376499e7e370d565d90dd7ef4f689f1f3c130798c2c9d94d5593272` is unchanged in the port. Runtime diff is Linux I/O/exit/entry adaptation, including the inactive RESTART UART-drain branch; the new port equals the established682 port with only identity/stop682→50 replacement. Original assembly/headers and startup/runtime/linker copies are unchanged. Physical a/b arrays remain1024 words, only CAP512 initialized per call; predicate remains128 bytes, output130 bytes. No empty-loop/history shortening, RNG replacement or invented warmup.

Defines are SEW16, unmasked1, restart0, unboxed0, destination_kind1. Independent source-loop enumeration matches all50 ledger entries and the old682 ledger's first50: calls1..48 cover seed0/op0, VL0/1/2/3/256/511, four mask modes × sticky0/1; call49 is VL512/mask0/sticky0 and call50 VL512/mask0/sticky1, both start0. All49 genuine predecessors remain.

Call50 is anchored to actual archived `rvv_compare_uncovered01/original_board_report.json` SHA `7ed11ee7257c8571d8d5d4bf87780231d82fd5373173343598d21d47ed5aa00f`: same original name, failed exit1, 19.6431064s; first detail is `op=0 seed=0 vl=512 mask=0 sticky=1 expected_flags=17 actual_flags=17 errors=64`. It proves this numerical/flags tuple and aggregate64 errors, not exact wrong-bit locations, stopped-state recovery or an M6 failure.

## Actual Assembly And Full Oracle

Independent ELF PT_LOAD byte inspection confirms all ten helper windows in both SoC/Spike binaries exactly occur once in the original Linux ELF. op0..3 have16 instructions, op4..9 have21; only op0 is selected. Target in both new backends is PC `0x80000508`, encoding `62881457`, unmasked `vmfeq.vv v8,v8,v16`. This is source-alias-v8, not MIN, masked comparison, unboxed scalar or a13-instruction Gather helper.

The original op0 loads full e16/m8 source groups and mask, requests VL/fflags with vset resetting vstart (no explicit restart write in this helper), reads returned vstart/flags, restores saved fflags, restores CAP512 and vsm-stores64 result bytes. CAP512/vtype11 and actual setup are checked by the reference parser; wrapper checks actual vlenb128. Predicate physical initialization is128 bytes, logical vlm footprint is64 at CAP512. Preserve these units in the future worker.

Independent integer FP16 oracle/classifier agrees with all1536 archived fixture entries in the existing Host report. Generated checkpoint summaries were reviewed for all50 calls: 25600 result bits,100 original guards,50 flags/vstart,51200 source values and6400 physical predicate bytes. Full512-bit old destination is derived from loaded alias source a[i/16], not output0x5b. VL0 must preserve old bits; active bits are exact; nonzero-VL tail permits original `{old,1,wanted}` alternatives. No preferred tail is imposed. Unmasked semantics apply even when the source loop varies predicate mode.

All50 generated output summaries satisfy the unchanged bit oracle and guards0/65; the supplementary output[66..129] initialization remains unchanged. Last output is64 bytes `01`, flags17/vstart0. The stored summaries and parser code were checked, not the raw debugger stream again. These are50 actual debugger checkpoints before target and at return, not an independently classified full retirement trace or per-instruction CSR-restore ledger. Future DUT checks must establish their own retire/protocol evidence.

Host metadata preserves two numeric0 positives (ordinary/permitted all-one tails), eight numeric1 mutations (call50 bits0/511, NV, returned vstart, both guards, first VL0 preservation, predecessor49 bit11), and five contradictory/missing-marker negatives. Source code applies these mutations at their named calls before the unchanged original oracle. Reports/log identities match pins; no Host rerun.

## Factual Process Recovery, Not Fabricated Child Wait

Initial outer preparation is preserved as `prepare_attempt01.py` SHA `d358ebb2796013f1acad0ff3878f229c36fe650ae9987ea91855268da11ba556`. Recovered existing tool-session observation70225/chunk a82bde is **exit1**, `ValueError: call1 loaded predicate`: its Python constructor used `bytes(255)`, not one byte255. The original attempt is not relabeled PASS.

Offline finalization uses `prepare.py` SHA `549e5ba679dcc02a8d433f4d9be7148f445f527a5490134de0d1ecfb37d3ff59`; recovered tool-session33133/chunk dffde7 is **exit0**. Source diff confines the numerical repair to the byte constructor and adds a no-execution finalization path/pin recovery. Same raw/ELFs/Host results are consumed; no Spike retry or C/asm/oracle change.

The recovered receipt is an explicit transcription of the actual preparer's existing exec/write_stdin responses, not an original on-disk wait file or signed platform transcript. Both preserved script hashes and bound artifacts match. Individual tool wait-call durations are not total runtimes and are not summed.

There is **no separately persisted nested Spike numeric wait receipt**. The checked synchronous helper requires subprocess.run returncode0 before returning; observed initial traceback is in the later offline parser, so normal-return control flow supports nested0. Firmware a0=0/PASS is separate architectural evidence, never a host wait status. Existing `actual_process_returncode:0` fields remain unchanged but are qualified as inferred, not directly saved. Spike and total outer elapsed times remain unknown/null. This absence is retained, not papered over and not a demand for a redundant rerun under the user's accepted evidence policy.

Readiness is qualified by unchanged source/ELF identities, full original oracle,50 per-call architectural checkpoints and the recovered actual offline-parent exit0. It is not an attestation of a missing durable child receipt or independent full-raw reparse. Input-pins unchanged only covers offline recovery/review; no historical persisted pre/post-Spike ledger is invented.

## Pins, Cost And Future Worker Gate

33 input and88 artifact pins match;120 hash checks exclude only the292111-byte raw Spike log. Its recorded SHA `544bbd4aac4dfc4e30145a54811fa03c480d2c9a4b5ffb62e68ae7c980e86d79` is cross-linked among READY/reference/artifact/recovery metadata, not freshly rehashed here. Source/provenance SHA `9feb97224ccfca6cd45324ae26f4f60a2ed8916808099da534ea0e517dd7b8d3`; SoC manifest SHA `272107a89c43a6a7797df6638c85c7f99ce4474f2708bc87ce72c8b4f72c7cc6`.

| Reusable input | SHA256 |
| --- | --- |
| SoC ELF | `4496c2b3644420634d48c0552b62a5126344271ea62fd2baac3c93205cf27983` |
| Spike ELF | `65e729caedfd94c64f8131e78ef9a2f0d4103fc9918eac75c2fb2f1e00437d49` |
| reference.json | `4b680a64974cf35fc3c4ae98e81871129df9ddba9710b0856790bb158e774f8d` |
| reference_calls.json | `6a9f77d1cfa27a27f5aec7661368ad75b8c8342fc08b83d0669cca6a29c42d7a` |

Actual minstret interval is1579534-5=1579529; debugger observes without new firmware instructions. M4 calibration2250..2268s and hypothetical273/s estimate5786s are proxies, not measured M6 walltime or RTL-cycle estimates. Initial budget.json5400s is not the future runner contract. Zeno's separate jobs1/case7200/worker9000 preparation requires its own frozen plan/image/authorization review; no automatic deadline change or execution is approved by this input entry.

Future plan must bind this ENTRY/REVIEW **and recovered receipt**, unchanged source READY/SoC ELF, actual M6 image/private command, all50 ordered calls/49 predecessors and original permitted oracle, flags/vstart/guards, independent full retire/protocol accounting, exact terminal membership, noabort/retry and actual numeric monitor outcome saved before generic/postcheck failures. Do not treat the reference's inferred rc field as a future DUT wait receipt. Source label and runtime id remain distinct. Parent factual-recovery and later worker review are required before launch.

Scope is first50 only: no acceptance of remaining632 through682, full17920-call Linux parent, historical board schedule, all FP alias variants or performance equivalence. Held682 remains held. Read-only static/summary/ELF command actual exit0, chunk6169d8; recovery-binding command actual exit0, chunk6c9507. No producer imported/executed or sealed input modified.
