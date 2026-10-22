# Masked Segment Consumer Static Review

Read-only RTL audit; no new test, simulation, or production edit. This is
compatibility analysis, not segment integration signoff. Reviewed identities:

| Source | SHA256 |
| --- | --- |
| segment_sequencer.sv | 672ddcdfafc3fb40206e9b28c9c4e5d67d40dc9fae18e577cff9c5dc586d4452 |
| vlsu/addrgen.sv | 470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da |
| ara_sequencer.sv | bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655 |
| vlsu/vldu.sv | 4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab |
| vlsu/vstu.sv | 139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2 |

Paths above are under hardware/src. Additional reviewed dispatcher identity:
8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2.

## Address and Predicate Compatibility

`segment_sequencer.sv:209-250` issues one field of architectural element i per
micro-op, with vstart=i and vl=i+1. Field zero and subsequent fields of a unit
segment use VLSE/VSSE with stride NF*E; explicit strided segments retain the
original stride. Subsequent field f adds f*E to scalar base. AddrGen
`:319-384` consequently addresses base+i*stride+f*E. Zero and negative strides
are preserved by the existing XLEN arithmetic. Integer EMUL advances each
field's vector register base by EMUL registers; fractional EMUL advances by1.

For that one-element request, AddrGen `:604-634` computes the absolute element
number as vl-(remaining_bytes>>SEW)=i, not i*NF+f. Every field correctly uses
mask[i]. Matching requires the buffered mask owner equal the current PE VID,
the element lie inside the tagged window, and its shuffled lane be valid.
Unit-segment rewriting does not accidentally re-enable burst mode; masked
memory also explicitly disables burst formation.

MASKU `masku.sv:1205-1206` tags each mask word with instruction ID and aligned
first element. Its nonzero-memory-vstart initialization at `:1810-1816` and
lane_sequencer `:1223-1238` agree on packed-mask origin. Each field is a new
PE request; the window/bit can repeat, but owner association must remain with
that request. VLDU/VSTU expose their actual buffered mask to AddrGen through
vlsu.sv, not an independently consumed second predicate stream.

## Skip, Fault and Completion

AddrGen `:923-947` turns an inactive field into one synthetic skip token,
advances exactly E bytes and does not issue MMU/AR/AW. An active unaligned or
translation-faulting field instead publishes an ordered exception descriptor.
Exception vstart is absolute i (`:970`, `:1283`). A skip's elem_start=0 is not a
fault-index report and must not be used as one by a probe.

VLDU/VSTU retire their mask at the micro-op end even when that is inside an
aggregate data word (vldu.sv:441-478, vstu.sv:473-497). VSTU still needs balanced
lane operands for skips; lane_sequencer.sv:721-741 explicitly supplies balanced
store packets. Thus an all-off segment is not a no-work shortcut: it still
requires NF*active_length ordered internal micro-ops, although no memory access.

The final sequencer fault-only load barrier retains matching LoadUnit done
before releasing an internal fault response, including FOF. The segment FSM
`:259-300` stops field issue on internal exception and waits for aggregate
idle before returning the architectural response. FOF suppression happens
later in dispatcher `:4368`, not before internal drain. Store B completion
ordering is unchanged. Normal nonfault loads may still acknowledge before
writeback; this review does not claim universal per-field completion barriers.

## Findings and Limits

No definite new address/stride/owner incompatibility was identified in the
masked AddrGen element-level change under the ordered peer protocol. However,
the consumer mask-input gates themselves rely on ordered issue/stream delivery
(`vldu.sv:122`, `vstu.sv:157`), rather than independently checking every incoming
owner. Verify that the old field's mask is retired and the next VID's mask is
accepted; matching window bits alone do not prove this.

The existing consumer commit-count exception assumptions still need upstream
ordering. Standalone AddrGen and VSTU PASS results do not prove actual segmented
MASKU/consumer/dispatcher integration. First-fault arrival, delayed final WB/B,
and fault-field partial progress must not be replaced with a synthetic sink
claim. Whole-register nf!=0 is explicitly excluded from segment classification.

Recommended original-case geometry: NF2, an inactive prefix plus an active
completed segment, then an active segment with a later field crossing into a
protected page; preserve actual nonzero trap/restart vstart. Observe
(element, field, VID, mask owner/window), MMU VA, skip/exception acceptance,
and physical final-write/B -> done -> architectural response. Concrete source
selection and adapter parameters are recorded separately in segment_review/.
