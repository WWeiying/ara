# Independent Linked Artifact And Cost Review

Decision: **ACCEPT_COST_EVIDENCE_HOLD_OVER_3M_NO_REFERENCE_OR_DUT**.

The full successful-path conditional CFG evidence is coherent and exceeds the approved3M threshold. This accepts the artifact/accounting evidence, not firmware execution or architectural correctness on a target. No reference, DUT, further source/flag variant or target recompilation is admitted. No Host/compiler/CFG analysis was rerun by this reviewer.

## Actual Process Outcomes

SoC and Spike-backend GCC compilation each completed once with recorded child0, respectively1.720009620 and1.769570003seconds. The fixed configuration uses the pinned non-ZCC RV64 GCC, -Os, rv64gcv/lp64d, disabled automatic vectorization and the reviewed source/runtime; only the backend reference macro differs. The runtime source is the pinned existing prefix runtime, not a new environment or RTL image.

The first CFG attempt exited1 after2.020576908seconds, before scalar case execution. The existing `cfg_receipt01/wait.json` and `linked_cfg01/FIRST_FAILURE.json` retain the actual mistaken stack-bound diagnosis. No cost or PASS is attributed to that attempt.

Successor02 actually exited0 after152.667891679seconds within600seconds, without timeout/executor error; its actual log hash matches the wait receipt. Both complete paths reach finite completion stores rather than stopping on first crossing3M. The old auditor and binaries remain unchanged.

## Narrow Stack-Address Correction

Both linked starts contain PC0x80000008 `00100117` (auipc sp,0x100), followed by PC0x8000000c `fe810113` (addi sp,sp,-24). The intermediate value0x80100008 is an address-construction result, not a stack access. The pair resolves exactly to symbol __stack_top=0x800ffff0.

Reviewed `linked_cfg_successor02.py`: only the unique, actual contiguous AUIPC/ADDI sp pair receives this temporary exception. It checks destination/source register, actual immediate calculation and final symbol equality, then returns to the original64KiB stack rule. Both PCs are still charged by the unchanged walk. No subsequent stack store/load, case body, unknown instruction or branch is waived.

## Independent Artifact Checks

- Rehashed165 pre/post input pins and16 completed-result evidence pins: no mismatch. Original and current manifests match; actual compiler/analyzer receipts and their log hashes are consistent.
- Independently located the concatenated helper bytes once in the original ELF executable segment at0x10910. Its368 bytes (capacity3 plus four24-instruction helpers) match both new ELF executable segments, not merely an unchecked disassembly string. Concatenation SHA256: `6ef8ae8efe6c52758d48b8f230420fb8b0455d3e98b749c059a3fddb5c4d9dd8`.
- Both linked disassemblies contain37 static vector instructions, all in these five original helper windows. Each operation retains nine CSR instructions in original order, including vxrm/vxsat save and restore. The scalar walker fails on unresolved values/calls or unsupported opcodes; the helper success summaries charge all original PCs rather than replacing24 instructions with one.
- Independently checked both10752-entry argument ledgers against seed/op/VL/mask/start/control ordering and each backend's real symbol addresses. Every helper occurs2688 times; duplicate starts, empty VLs and sticky controls remain. Per-PC/helper and per-function totals sum to each reported complete count.
- Full linked-output scalar event records account for698880 initialization stores and698880 reads, precisely64SD+SH and64LD+LHU per call. The audited walk requires their per-call address/width/order, full previous-read completion, all4416 input SB events,5376 clear SDs and70644 cumulative mask SBs. These are operations on the conditional CFG path, not observed DUT transactions.
- Read the actual analyzer implementation: successful vector output is explicitly injected from the independently Host-validated oracle into only512 result bytes; it does not initialize guards/counters or modify source/mask/stack. Table bytes are checked against the linked ELF. This explicit hypothesis is not a second independent numerical reference.

## Complete Cost And Map

| Term | SoC | Spike backend |
| --- | ---: | ---: |
| Startup/BSS |1655|5756|
| Adapter main |20|21|
| Full main/caller/control/oracle |3394271|3371758|
| Capacity |3|3|
| Four original helpers |258048|258048|
| Printing and formatting |28552|40068|
| Finite completion |4|6|
| **Total conditional linked instructions** |**3682553**|**3675660**|
| **Excess over3M** |**682553**|**675660**|

The linked runtime has no device-ready polling loop on this path. All321 text calls,146 number calls,28 original boundary records and1704 output bytes are charged. The walker includes caller branches, relocation/address setup,55818 stack stores and130233 stack loads; it does not replace them with a proposed per-call overhead.

The recorded positive stack high-water is336 bytes in each image, with64KiB reserved. SoC image through BSS is86920 bytes and Spike95312 bytes, both within1MiB and below the reserved stack region. Initial unknown callee-saved values are treated as opaque spill/restore tokens, not fabricated zeros. These are linked-path/map properties, not physical target observations.

Finite completion is backend-specific: SoC PC0x8000006e performs8-byte CTRL write0 at0xd0000000; Spike PC0x8000007a performs8-byte HTIF write1 at0x80014740. Post-exit park is explicitly outside firmware accounting. Full counters10752/5505024/errors0 and final success text are traversed under the success hypothesis.

## Binding And Limits

- SoC ELF: `a3690d0ba3954bf8c043cb456b28084214559c542ee5fcdf4ba18ce323aeb852`.
- Spike ELF: `e6c826b4dbda92fc79f2b7ca1d532329776fe83d0152213887ee4701a7bee20e`.
- `linked_cfg02/complete.json`: `8a5c2187374c33be54be7b9046620ace57bccd9cc3f344735ac53b69bbd31db9`.
- `cfg_receipt02/wait.json`: `8b3f99558edc5f8157cddd8c5f66796037d4fc88f0ef94a2a6ee39fc64b5159c`.

The original-C Host composite remains accepted separately. The above counts are conditional linked instruction counts, **not measured Spike retired instructions, not a DUT PASS, not Linux closure, and not a <=3h runtime guarantee**. Full scope was not shortened. The fixed3M gate fails, so the next state is HOLD; no automatic optimization trial, larger budget or run follows.
