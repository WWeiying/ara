# Original FP Comparisons: Preparation Only

Latest M4 successor: [candidate04_restart_plan05/README.md](candidate04_restart_plan05/README.md).
Only the two original130-call prefixes are scheduled, jobs2/3600s each/4500s
outer; **not authorized/launched**. The full682-call entry is HOLD, unchanged.
Sealed plan03 remains intact. Scheduling requires Gather75 terminal +38PASS
+NF8 initial admission, worker/slot release and parent coordination; Gather
first admission is not enough. No942-call DUT acceptance is claimed.

**READY for parent review: three authentic-source prefixes, host and Spike PASS;
no DUT execution, RTL change, image build, or Final38 polling.**
[ready_audit01/finding.json](ready_audit01/finding.json) independently checks the
raw reference logs, original identities, 1937 input pins and 39 prepared-file
pins. No original full-parent acceptance is claimed.

## Provenance

[provenance01/parents.json](provenance01/parents.json) identifies exactly
208 nonrestart + 29 restart failed original ELF records across 18 families.
These are parent programs, not 237 independent defects or singles.
[ready_audit01/original_contexts.json](ready_audit01/original_contexts.json)
binds all 237 to original report input hashes and 4740 retained detail lines.
Each report retains only 20 error details; this is not the complete failing
tuple set. Equal flags isolate a nonflag mismatch, not necessarily a data bit
rather than vstart/guards. The separate stalled e16/m8 restart is outside the29.

| Archived reduced source | Records | Identity limit |
| --- | ---: | --- |
| `rvv_small_fp_compare02` | 77 | Original current C hash; original assembly/fixtures pinned |
| `rvv_small_fp_compare_reconstructed01` | 119 | Explicit historical reconstruction label retained |
| `rvv_detail_fp_compare01` | 29 | Additional raw-output versions of the same restart parents |
| `rvv_compare_uncovered01` | 41 | Explicit reconstruction; includes unmatched e16/m8 |

Those 266 child records cover exactly237 distinct parents, not266 new failures.
[provenance01/singles.json](provenance01/singles.json) preserves every original
tuple, source hash, parent link and provenance label without relabeling old runs.

Removing exactly the two later unboxed additions restores C SHA256
`3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c`.
This matches original manifests for74 failed parents. Another88 use the current
C hash `03cc5031...e9bad`. Historical C hashes for75 older parents remain
unrecovered; their ELF, assembly, fixtures and contexts are pinned, but they
are not represented as fully source-equivalent replay inputs.

All three selected full parent ELFs rebuild byte-identically with the archived
Linux toolchain, before truncation or runtime adaptation. In particular the
e16/m8 original is `266467e6d61dc7334a83e62ce6ee8d2d0cfac5050811be026329c46eb3816754`.
Commands and rebuilt binaries are retained under `provenance01/` and each
`prepared02/prepared/*/original_rebuilt.elf`.

## Priority Contexts

Original e16/m8 unmasked v8 alias call50 is op0/seed0/VL512/mask0/sticky1:
flags17 match, errors64. The summary does not locate the failing bits; at least
62 must be data errors because vstart and combined guards contribute at most2.
Original final summary is17920 calls/errors1252, not merely this one failure.
The archived50-call run passes with flags17 and all64 output bytes `01`.

**New equivalence evidence:** current reconstructed C and restored historical C
compile to the identical original e16/m8 ELF. Removing only diagnostic printing
and the stop from the old50-call source recovers that current C exactly.
Thus a C-oracle version difference does not explain this specific mismatch.
Raw logging, executable layout, Linux/runtime and execution history remain
different. This is not proof of intermittency or of a current RTL cause.
The old isolated and50-call artifacts were neither changed nor rerun.

| Prepared program | Calls | Last authentic failure context | SoC target PC |
| --- | ---: | --- | --- |
| `alias_v8_e16m8_prefix682` | 682 | op2/seed1/VL1/mask0/sticky1, expected1/actual17; includes call50 and all intervening calls | op0 `80000508`, op2 `80000580` |
| `restart_e16m2_prefix130` | 130 | op0/seed0/VL64/start32/mask0/sticky0, flags16/16, errors12 | `800005cc` |
| `restart_unmasked_e16m2_prefix130` | 130 | Same measured tuple, unmasked instruction, errors12 | `800005ae` |

The682-call sequence adds genuine post-call50 vv/vf/operator and source-layout
history, reaching two later original flag failures at calls681/682. It is not
another isolated50-call replay. The130-call sources retain all129 predecessors
through the original data-error point, unlike the small generic D controls.
Every original per-call data/flags/vstart/guard check and allowed mask-agnostic
alternative is unchanged. Only an after-oracle stop and Linux entry/I/O/exit
adaptation were added; original assembly/data tables are unchanged. Diffs and
exact ordered tuple lists are in each prepared case. No Linux scheduling,
original virtual address, or cross-process history equivalence is asserted.

Additional uncovered selection, not prepared/rerun here: original unboxed
unmasked e16/mf4 op4/seed0/VL15/mask0/sticky0/1 has flags0/1 vs16/17 for vd24,
v8, v16 and v0. Unlike boxed-scalar D controls this uses malformed scalar boxing;
its flag mismatch alone does not establish a boxing defect. In contrast, the
first retained masked-unboxed failures are vv and do not exercise scalar boxing.
Original masked/unmasked restart source origins now use zero-based MulFPUA/B
in candidate04; that repair and existing D passes do not accept these parents.

## Reference And Review Gate

[prepared02/reference.json](prepared02/reference.json): all942 calls PASS on
Spike `rv64gcv_zvfh_zvl1024b`, raw logs show original marker, errors0 and exit0.
Host checks use an independent integer FP16 classifier for all1536 archived
fixture entries, three positive prefixes, five rejecting mutations (active bit,
NV, prestart, guard, vstart), and a permitted all-one mask-tail control.
`prepared01/ATTEMPT.md` preserves the earlier overly strict preprocessor-equality
assertion failure; optimized ELF equality subsequently proves the intended check.

Ready SoC manifest: [prepared02/soc/programs.json](prepared02/soc/programs.json),
SHA256 `e464d1b3cb8fe2b8d0c677b48fff6917715b1af97ead341465ad8e93ba8f3374`.
Full ELF hashes and PCs: [prepared02/address_map.json](prepared02/address_map.json).
**Do not launch before parent review.** Budget/probe choices remain unapproved;
no timing acceptance or current-image result is inferred from Spike.
