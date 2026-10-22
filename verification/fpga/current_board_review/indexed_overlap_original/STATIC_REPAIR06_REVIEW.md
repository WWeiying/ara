# Independent Static Repair06 Review

Date: 2026-10-11. Scope: the dispatcher dedup change only, relative to frozen
candidate05 (M5). No RTL edits, builds, simulation launches, or acceptance-tool
runs were performed for this review.

## Verdict

**No blocking static finding for admitting the same-ELF M6 DUT test.** The
change preserves a required indexed-source normalization request which M5
incorrectly discards. Existing snapshot/replay handling supplies the subsequent
destination conversion and correct source-layout tag. No new snapshot mechanism,
architectural vstart change, or unconditional full-group normalization is needed.
This is static approval, not M6 functional acceptance or historical-family closure.
The parent reports the isolated M6 build is running; this review does not certify
that build or its final image manifest.

## Exact Identities And Diff

SHA256 values independently read from disk:

| Artifact | SHA256 |
| --- | --- |
| Current `hardware/src/ara_dispatcher.sv` | `c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d` |
| M5 frozen dispatcher | `05e9a4633d3d3a989fc5433fbf647c26c9d21ec1837b210ee84b6c712f6815fd` |
| `REPAIR06_ROOT_CAUSE.md` | `3f81e20eb0441cdc93677052d67dc437cf99ab9349aaedeca71a126736b843ff` |
| `reference03/d32m2_i64_fault_ov1/soc.elf` | `5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f` |

The M5 comparison file is
`/home/wangwy/fpga_runs/current_board_memory_candidate05/frozen/sources/hardware/src/ara_dispatcher.sv`.
The actual unified diff contains two added comment lines and this one expression
change, at current dispatcher line 5659:

```diff
-              reduction_source_overlap_reshuffle,
+              reduction_source_overlap_reshuffle || indexed_load_groups_overlap,
```

This comparison is against M5, not git HEAD. It does not certify unrelated files
in the worktree or image. The new OR changes only the mask applied to an existing
`reshuffle_req_d[1]`; it cannot turn a zero source-request bit into one.

## Failure Chain And Finite Repair Sequence

Evidence is recorded in [WAVE_ADDENDUM.md](failure_analysis01/WAVE_ADDENDUM.md),
[WAVE_BOUNDARY.md](terminal_review02/WAVE_BOUNDARY.md), and
[REPAIR06_ROOT_CAUSE.md](REPAIR06_ROOT_CAUSE.md). The measured request starts at
**vstart15**, not 16. Its fault position subsequently becomes 16. It carries
index EEW64, old EEW32, v4/v5 tags 32/64, and no snapshot replay. The valid lane
words include `0x17000, 0x4000, 0x11000, 0x1e000`; the observed bad MMU address
is `0x0000400040017000`, matching base plus `(index17 << 32) | index16` under
the wrong EW32 deshuffle. The CSV records that same bad mtval.

For VL32/start15, the active e64 index interval includes v4 and v5. The active
e32 destination interval includes v4. `active_group_has_mixed_eew` (dispatcher
line 422) correctly identifies the mixed source. At lines 5408-5419, the code
requires source-first normalization and defers capture while that source request
exists. M5 then drops the source request because `vs2 == vd`, leaving neither
normalization nor capture. The pre/post-dedup values here are a static derivation
from the measured inputs, not a claim that both procedural values were separately
captured in the old wave.

With Repair06, the expected bounded sequence is:

1. Keep the source request; normalize active source registers to e64. v4 converts;
   already-e64 v5 is skipped. The existing WAIT_IDLE prevents re-decode before
   the final conversion has completed (dispatcher lines 1520-1650).
2. Re-decode the uniform active source. The source request is now zero, so the
   existing indexed-overlap path captures it before converting vd to e32
   (lines 5778-5809).
3. With a valid matching snapshot, replay selection clears source normalization
   and sets `old_eew_vs2 = source_snapshot_eew_q` (lines 5573-5595). That override
   already exists in M5; no duplicate override is required.
4. Destination conversion may make physical v4/v5 mixed again, but the saved
   source match still clears the source request before dedup. The new OR cannot
   recreate it. Issue uses the snapshot and architectural start15, not another
   source/destination conversion cycle.

No new normalize/capture loop was found in this path. Merely recomputing capture
after M5's source-bit deletion, or forcing direct-VRF old EEW64, would not be an
equivalent repair: either could consume a still-mixed physical source.

## Path And Side-Effect Review

| Domain | Static result |
| --- | --- |
| Legal indexed-load overlap | `indexed_load_groups_overlap` requires exact VLXE, used vd/vs2, and intersecting effective register groups. The change does not alter decode legality, alignment, EMUL limits, or overlap permissions. The original e32m2 vd4 / e64m4 vs2 v4 is the legal low-source-group overlap, not a newly legalized instruction. |
| Same EEW, already-correct layout | No source request exists, so nothing new is created. |
| Same EEW but mixed physical tags | Source normalization can genuinely be required. For equal base/EEW/LMUL, the existing merge at lines 5625-5632 may retain both destination and source requests. Destination normalization performs the same conversion; `rs_mask_request` at lines 1612-1616 and 1649 skips already-converted registers, including same-cycle boundary forwarding. This can add bookkeeping states, but does not imply two destructive conversions or a loop. No zero-cycle-cost claim is made. |
| Partial overlap with different bases | The old `(vs2 != vd)` term already preserves the source bit. Adding the group-overlap term changes no dedup decision in this case. Existing normalization/capture behavior is not newly validated by this review. |
| Same base, different source/destination EEW or group size | Required conversions are not duplicates. The measured mixed-layout case is in this changed domain. Uniform source-layout cases with no source bit remain unchanged. |
| VSXE indexed store | The new flag is false because it requires VLXE. Store-source dedup and store ordering are unchanged. |
| Nonoverlapping VLXE and other operations | Added term is false; original expression is preserved. |
| VL0 / vstart >= VL / other existing noops | The valid, nonexception, non-noop maintenance guard at lines 5349-5352 is unchanged. No new zero-length capture is introduced. |
| Mask, prefix and tail preservation | No predicate, active interval, destination preservation, or exception/retry logic changes. Existing reshuffles convert a whole physical register without changing its canonical bytes. A masked-off index within the active interval is not a reason to skip required layout consistency. |

## Capture From Zero Versus Active-Suffix Consumption

The snapshot must not be described as a uniformly meaningful full index group
when whole inactive-prefix registers retain another EEW. The sufficient invariant
for this repair is narrower: **the active index suffix has the saved EEW, and raw
snapshot word positions are identical to their original VRF positions.**

Relevant unchanged implementation:

- Dispatcher SOURCE_SNAPSHOT_CAPTURE (lines 1483-1505) starts the source-only
  maintenance request at zero, with the saved VL/EEW and no destination write.
- Lane capture (lane.sv lines 514-555) stores raw SlideAddrGenA VRF words in
  increasing snapshot indices. It does not compact away prefix registers or
  perform a cross-register reinterpretation before storing them.
- Indexed lane sequencing (lane_sequencer.sv lines 694-711) derives the first
  aggregate word from architectural vstart and encoded index EEW, then expresses
  the requester start/length in stored-EEW units. Both requester eew and vtype
  use the stored EEW, keeping `scale_vl` byte accounting consistent.
- Operand requester (operand_requester.sv lines 402-448) uses that same aligned
  word offset for VRF and snapshot origins. AddrGen (addrgen.sv lines 293-352)
  deshuffles using saved old EEW, selects the first element using architectural
  vstart/index EEW, and counts only `VL - vstart` indices.

For the actual four-lane, VLEN1024, e64 VL32 case, each register occupies four
64-bit words per lane, independent of its physical EEW. Capture therefore stores
eight words per lane: v4 at indices 0-3 and v5 at 4-7. Start15 replays word3,
selecting element15 (lane selector3); start16 replays word4, selector0. At start15,
v4 is a partially active register and is normalized in full. At start16, v4 can
remain e32 and contain completed destination results: its captured words 0-3
are not consumed as active offsets. They cannot shift v5 away from word4.

Whole-register boundaries are also aggregate-word boundaries. Consequently a
fetch rounded down to the start-containing word does not reach into a wholly
inactive preceding register. Prefix elements within the first active register
may be fetched, but that register has been normalized and AddrGen does not select
elements before vstart. Likewise, fetching a final aligned word does not extend
the logical index count beyond VL. This explains why active-only normalization
and capture-from-zero are compatible; it does not justify reading the saved
prefix later as meaningful active indices.

Inactive prefix capture does consume existing internal read/storage tokens.
It creates no architectural indexed memory access or destination write. Its
fixed raw-word positions/counts, rather than the semantic interpretation of
unused prefix values, determine completion. Repair06 does not change those counts
or snapshot capacity. No claim is made here that every unrelated snapshot user
or shape has been dynamically covered.

## DUT Admission And Remaining Evidence

Admit the unchanged reference03 fault-ov1 ELF against an image pinned to the
reviewed dispatcher hash. Preserve all 50 rounds, all 32 results and guards, the
original helper sequence, CSR checks, and same-PC retry without reloading indices.
The fixture's deterministic Sv39 fault schedule is not the original Linux paging
schedule; passing it must not be reported as full Linux closure.

The discriminating expected observations are surviving mixed-source normalization,
physical conversion completion before capture, snapshot replay with old EEW64
after destination conversion, and the corrected element16 address `0x40017000`.
If sampled, pre/post-dedup evidence must distinguish procedural stages rather than
label one settled combinational value as both. Existing resident-ov1/fault-ov0
controls and the parent's planned regression remain acceptance requirements;
this report adds no cases or runs. Required maintenance adds cycles on the broken
path. Normal-path cycle equivalence remains a measurement question.

**Final status: static review complete, no blocking finding; M6 DUT acceptance
pending. Only this new report was written.**
