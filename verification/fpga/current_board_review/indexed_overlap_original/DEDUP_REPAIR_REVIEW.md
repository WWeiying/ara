# Indexed Overlap Dedup: Conditional Repair Review

**Static approval of the proposed scope, not measured repair acceptance.**
No RTL change, simulation, wave conversion or reference/oracle modification.
The latest actual waveform, not the earlier scalar attempt numbering, establishes
request vstart15 and exception vstart16.

## Wave Premises

Tesla/Confucius `failure_analysis01/WAVE_ADDENDUM.md`:

- At367660.5ns AddrGen request: vstart15, indexEEW64, oldEEW32, replay/capture0.
- At367664.5ns index15 produces correct address0x4000a000.
- At367678.5ns index16 produces0x0000400040017000 in idx_final_vaddr_q and
  mmu_vaddr_o, already wrong before exception transport.
- Dispatcher eew_q[v4]=EW32, eew_q[v5]=EW64 throughout those samples.

These observations support the cross-register interpretation previously listed
as conditional hypothesis B. The first bad address is not a fixture printf
artifact or solely a later tval transport problem. Raw input-word bytes and the
exact pre-dedup expression value still require separate evidence.

## Deterministic Static Failure Chain

Assume the corresponding ready architectural decode has the observed start15,
VL32, source v4/indexEEW64/LMUL4, destination v4/SEW32/LMUL2, valid v4/v5 tags,
and snapshot_valid=0. This produces the following values in source order:

| Stage | Source result |
|---|---|
| active_register_mask(LMUL4,EW64,15,32), dispatcher:317 | bits0,1 set; only v4/v5 |
| active_group_has_mixed_eew, :422 | true: valid tags32 versus64 |
| initial source reshape :5375 | bit1=1: source needs64 and indexed_mixed=true |
| initial destination reshape | bit0=0: only v4 active, already tagged32 |
| overlap priority :5415 | keeps bit0=0 until source is normalized |
| indexed_load_index_overlap :5418 | false, because source bit1 is still1 |
| same-base source dedup :5654 | bit1 becomes0: vd==vs2; none of its exceptions applies |
| capture branch :5776 | not selected: indexed_load_index_overlap remainsfalse |
| reshape branch :5809 | not selected: final reshuffle_req_d is000 |
| original issue | direct VRF, first-active-register oldEEW32, mixed source stream |

The mixed-EEW function itself correctly detects this input. It walks the active
register mask, chooses the first valid tag and ORs differences against later
valid tags. It does not reset the result on the second register. The defect is
the later removal of an already required source conversion, combined with a
capture-eligibility flag computed before that removal.

Original vle64 VL32 writes v4/v5 and tags them valid; metadata valid bits are
only cleared at reset in this code. Nevertheless include actual valid bits in
the decode evidence rather than silently treating any unknown tag as valid.

## Proposed Minimal Change And Why It Is Sufficient Here

Add `|| indexed_load_groups_overlap` to the **second component** of the existing
same-source/destination dedup mask at5654. Keep all other components,5415 source
priority, capture matching, and5584 old-EEW replay override unchanged.

For this request the expected state sequence becomes:

1. Keep source bit1. prepare_reshuffle selects source basev4, old32/new64,
   two active registers. Convert v4; v5 already64 is skipped by the existing
   rs_mask_request logic (:1649). WAIT_IDLE waits for physical completion.
2. Decode again: v4/v5 now64, source bit0, destination v4 needs32. The indexed
   capture predicate is nowtrue, so capture the VL32 source in correct EEW64.
3. Decode with snapshot_valid1: replay matches source v4/EEW64/LMUL4, source
   reshape is cleared, and vd conversion changes only active destination v4
   to32. Existing WAIT_IDLE again protects physical completion.
4. Decode after vd conversion: tags are mixed32/64 again, but the matching
   snapshot clears source reshape before dedup and overrides oldEEW to64.
   The new OR does not reassert any bit: it only prevents clearing an existing
   bit. Therefore no normalize/capture loop occurs; publish replayed VLXE with
   vstart15, indexEEW64, saved-source oldEEW64, destinationSEW32.

At replay, aligned source origin is aggregate word3, then4; AddrGen first selects
index15 within word3, then correctly consumes word4/index16. Snapshot capture
still starts at0 and covers full VL32; inactive captured prefix bytes are not
used for this restarted address stream. Full-register layout conversions preserve
canonical old destination bytes, including the completed prestart prefix. They
must not re-execute or reload the original index-load prologue.

Do not instead recompute the indexed capture predicate only after clearing the
source bit: that would capture a still-mixed physical group under a single EEW.
Do not merely force oldEEW64 on direct VRF: v4 is actually laid out as32 before
normalization, so it would damage index15. Do not duplicate the existing5584 fix.

## Scope And Side Effects

- The flag is exact VLXE/use_vd/use_vs2/group-overlap. The new exception only
  matters when vs2==vd, since different bases already pass this dedup component.
- For VLXE the initial source bit requires indexed_mixed_vs2_layout: VLXE is
  outside all in_lane_op ranges and is not VCOMPRESS. Thus adding overlap alone
  or overlap AND indexed_mixed is equivalent for set source bits in the current
  code. The simpler overlap exception matches the existing source-priority
  contract. Either choice should be reviewed against the same truth table.
- VSXE, disjoint indexed loads, gather/compress, comparisons, arithmetic,
  widening/narrowing and reductions do not gain this exception. Their existing
  dedup and snapshot paths remain unchanged.
- Uniform layouts and already matched replay do not gain a source conversion
  from this OR. With replay active the source bit is already0, so it stays0.
- Same-width indexed source/destination also must not lose required mixed-group
  normalization merely because bases match; do not add an unnecessary
  source-EEW != destination-SEW qualifier to the fix.
- This repairs a path previously issuing mixed-layout data, so extra maintenance
  latency is expected there. It does not establish cycle invariance for the whole
  faulty program. Original resident/fault-ov0 controls should remain unchanged
  where this extra predicate cannot affect a set bit.
- A separate existing-domain caveat: uniformly stored index EEW different from
  encoded index EEW does not set indexed_mixed. This patch does not add a proof
  that snapshot capture labels that uniform physical view correctly. Do not
  claim all indexed-layout configurations closed by this one mixed-group repair.

## Required Falsification Evidence

Before declaring the mechanism measured, correlate the same decode/request epoch:

1. Real vstart15/VL32, source/destination widths/LMUL, v4/v5 tag+valid,
   snapshot_valid0, indexed_mixed=true and indexed_load_groups_overlap=true.
2. Before dedup source bit1=1 and indexed_load_index_overlap=false; after dedup
   source bit1=0, final reshape000 and no capture transition in baseline.
3. Candidate retains bit1, executes the finite state sequence above, publishes
   matched replay oldEEW64, and produces index16 address0x40017000. Assert no
   extra original index reload and no skipped original full32-value oracle.

Important observability limit: the existing capture.tcl did not explicitly dump
indexed_mixed, the dedup predicates or reshuffle_req_d. Moreover pre/post dedup
are two procedural assignments to one combinational variable; a settled-value
waveform of reshuffle_req_d alone does not expose both. Current wave proves the
bad request/layout and pre-MMU result, while the pre-dedup value above is a
**source evaluation from measured premises**, not an already observed waveform
sample. Direct per-stage proof needs parent-owned nonfunctional observation taps
or statement-level debugger observation; alternatively label the source-derived
pre-value honestly and measure all inputs, final bit and branch/state outputs.

The first failing original request plus its preceding correct index15 is the
minimal discriminator. Follow with the unchanged complete50-round original
fault/ov1 program and original resident-ov1/fault-ov0 controls, full data/guards/
CSR/same-PC retry gates. No run or production edit is authorized by this note.
