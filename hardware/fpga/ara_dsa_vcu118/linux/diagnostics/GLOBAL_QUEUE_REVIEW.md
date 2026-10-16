# Global indexed-write review, 2026-09-28

## Result

Similar constructs exist beyond the four previously identified result queues.
This review establishes additional verification targets, not additional proven
synthesis defects. No functional RTL or running-build inputs were changed.
The VALU failure remains the only measured RTL/mapped discrepancy in this
investigation.

The subsequent restricted source-module / Vivado 2020.1 mapped tests and
remaining gaps are tracked in [QUEUE_MAPPED_VALIDATION.md](QUEUE_MAPPED_VALIDATION.md).
The static candidate table below is not a list of confirmed failures.

## Coverage

* Parsed 706 Verilog/SystemVerilog files: 653 in the exported FPGA RTL tree and
  53 in the main Ara RTL tree. Duplicate Ara copies are not independent designs.
* Compared all 653 exported RTL files against the Windows build's frozen
  `D:/fpga_runs/ara_valu_fix_20260928/package/SHA256SUMS`: zero mismatches.
* 625 scanned package files appear directly in manifest.json; others may be
  included, optional or unused. Listing a file does not prove instantiation.
* Used pyslang 11.0.0 syntax trees with manifest include paths/defines plus
  SYNTHESIS, ARA_FPGA_HOST and ARA_FPGA_ETHERNET. This is not elaboration,
  formal equivalence, or a vendor-netlist test.
* Found 150 broad syntax candidate groups, including 39 main-tree duplicate
  groups; 111 are in manifest-listed package files. These are NOT bug counts.
* Parser diagnostics were IgnoredMacroPaste (8), NonStandardGenBlock (3),
  NewlineEOF (2) and MisleadingIndentation (2); no missing-include or unknown-
  macro diagnostic was reported. Macro-paste diagnostics limit confidence in
  those expansions and must not be mistaken for clean elaboration.
* Inventory including source hashes, writes and diagnostics:
  `/tmp/ara_queue_global_audit_20260928.json`.
* Six scanner tests passed, including nonblocking writes, nested arrays,
  same-index overrides, exclusion of comparisons and separate processes.

## Prioritized candidates

Paths below are relative to `hardware/fpga/ara_dsa_vcu118/rtl`, except Ara
paths which are shortened to the matching `hardware/src` location.

| Priority | Site | Static observation | Discriminating mapped test |
| --- | --- | --- | --- |
| First | `lane/vmfpu.sv:1963,2570` | Dynamic partial payload writes and whole read-entry clear | Hold first VMUL/VFADD result while second entry fills; compare all payload fields and completion IDs |
| First | `vlsu/vldu.sv:416,537` | Queue/lane/byte writes with independent lane clears | Delay one VRF lane grant while AXI fills another entry; pending data/BE/address/ID must remain unchanged |
| First | `sldu/sldu.sv:751,937,1088` | Partial byte writes, reduction initialization and dequeue clears | Cross-lane slides and reduction forwarding under staggered grants |
| First | `masku/masku.sv:1426,1479,1640,1661` | Whole result construction, field override and dequeue clearing | Mask/compress results with partial last packet and independent lane grants |
| First, newly identified | `masku/masku.sv:1145,1210,1232` | Mask operand queue bit writes versus lane/row clearing | Keep one lane's mask unaccepted while filling next mask entry; no change to pending mask bits |
| Next | `cva6/core/scoreboard.sv:213,238,247,283` | Whole instruction allocation, dynamic writeback field updates, commit invalidation | Simultaneous allocate/writeback/commit with distinct transaction IDs and a flush |
| Next | `cva6/core/store_buffer.sv:176,187` | Read-entry valid clear followed by whole write-entry assignment | Simultaneous enqueue/dequeue and pointer wrap, checking new-entry priority when slots coincide |
| Next | `cva6/core/lsu_bypass.sv:75,82,94` | Whole request enqueue, dynamic valid-bit clears, whole-array dual-pop clear | Push plus load/store pop combinations, preserve unrelated entries |
| Next | `vlsu/qbs/qbs_read_engine.sv:540,554` | Whole burst metadata enqueue and partial current-response update in always_ff | AR acceptance while non-final R beat updates a different head; byte/beat counters and tag stay associated |
| Next | `common_cells/src/id_queue.sv:219,227,244,265` | Whole linked-list entries and pointer/free field updates | FULL_BW simultaneous pop/push, same-ID append and freed-slot reuse |

The QBS case is not the same combinational coding pattern: it uses clocked
nonblocking writes. AR acceptance is capacity-gated and response handling
requires outstanding metadata. These controls reduce functional alias risk,
but do not establish correctness of the synthesized independent write paths.

The ID queue is used by multiple AXI helpers. Whether a particular FULL_BW
configuration is active must be checked in the elaborated design. Do not infer
it solely from source presence.

## Lower-priority matches and exclusions

* VALU/VMFPU/SLDU instruction queues assign a whole accepted instruction and
  then adjust fields through the **same accept pointer** (`valu.sv:1295`,
  `vmfpu.sv:2638`, `sldu.sv:1153`). The override is intentional; it differs
  from writing one pending result while clearing another. Still include
  instruction ID/mask/conversion decoding in mapped functional tests.
* `operand_requester.sv:351` uses a genvar requester index. Its default and
  field assignments become fixed per-requester logic, not runtime queue-slot
  selection. Likewise many AXI/Cheshire channel overrides use fixed indices.
* `cva6_tlb.sv:288,333` updates entries in a bounded loop with mutually
  exclusive flush/replacement branches. BHT/BTB and QBS metadata pipeline
  matches include reset-only whole-entry assignments. Lower priority than
  concurrent runtime whole/partial writes; not a proof of equivalence.
* AXI upsizer output construction, ID prepend/remap, FPnew format assembly,
  and LLC address-map construction produce numerous expected syntax hits.
  Most use elaboration constants, loop indices or output defaults.
* CVA6 speculative store queue and WT cache write buffer have competing
  dynamic **field** updates but no matching normal-operation whole-entry
  clear in the reviewed blocks. They are adjacent risks, not identical to
  the observed VALU pattern.
* Ara sequencer dependency matrices and queue valid vectors combine row and
  bit updates. They are bit arrays rather than payload structs; completion/
  hazard tracking still needs protocol checks.

## Limits and next gate

The scanner deliberately over-approximates index aliasing and does not prove
branch exclusivity or infer constant indices. It handles ordinary identifier/
member/select assignment LHSs; concatenation LHSs, hidden generated/encrypted
vendor implementations and alternate macro configurations are not certified.
Whole-root defaults are excluded from the automatic entry-overlap criterion.

Do not rewrite every hit. First extract the prioritized cells from the full
synthesis checkpoint and compare held payloads, enqueue/dequeue ordering,
byte enables and completion under identical legal stimuli. Only change RTL
where static semantics and measured evidence agree. Continue to require
Linux boot plus checked user-vector/context-switch tests for board acceptance.
