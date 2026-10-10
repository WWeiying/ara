# Ara Upstream Bounded Absorption, 2026-10-09

## Scope and Freeze

Only these existing RTL files were changed, relative to the pre-edit archive:

- `hardware/src/lane/simd_mul.sv:174`: default `r='0` in all four SEW combinational branches.
- `hardware/src/vlsu/vldu.sv:473`: retire a descriptor only inside beat consumption, comparing the current beat index to LEN.
- `hardware/src/ara.sv:804`: reject `VLEN < ELEN*NrLanes`.

No sequencer, segment RTL, sealed helper, existing timing TB, or registry was edited.
No Verilator, URG, ZCC, DC, synthesis, full regression, or commit was run.

Source SHA256 (ready for parent integrated smoke):

```
6f2796c849dbfdcac556791d6b31be11ef2769441453c5bfcfc1db296dbf8471  hardware/src/lane/simd_mul.sv
5700da41de5b85998b3feba441a4bddda0645b4f0f00f04927baedeb0899f07c  hardware/src/vlsu/vldu.sv
e80a6e0f1bd480818a7d923e147b8ffce5a0b98a955d14afe1f8746684b3794d  hardware/src/ara.sv
```

Original archive: `/tmp/ara-signoff-upstream-before-20261009.tgz`, SHA256
`bbc7a77d13e5bd7832f8001b54884b35b08d18675f56e698e35d365383802601`.
It existed before this work; its three owned originals were copied into each
baseline output before RTL changes. No archive was overwritten. Original hashes:

```
1ba7d9f1ed1aed9ec5407d0af244c4aa3a4be1f2457fdaee4653d6fa875c6c64  simd_mul.sv
2661d1d5bd22ad95825c38be679622d7bae987deae743e12d1fadfe7c3b0af0d  vldu.sv
ab7af0adead3fbc3a78cba5029ab8fb3fe3066b6f954085dff27971343be1eac  ara.sv
```

## Proven Cause and Fix

[Issue #499](https://github.com/pulp-platform/ara/issues/499) is an **open issue**,
not an accepted upstream patch. LEN and the beat counter are eight bits. With
LEN=255, the original next-count comparison matches zero before the first beat
has finished. A partial first beat can therefore pop the descriptor without R
handshake, discard its byte pointer, and misattribute subsequent data.

Unmodified RTL measured evidence preceded the VLDU edit:

```
old-02: cycle=5 POP=1 RREADY=0 len_q=0 len_d=0 rptr_q=0 rptr_d=0 vrfptr_q=31
new-03: cycle=5 POP=0 RREADY=0 len_q=0 len_d=0 rptr_q=0 rptr_d=1 vrfptr_q=31
```

The final fixture also uses an ordinary vstart=0 load: 31 bytes before a page
boundary, then 4096 bytes in a 256-beat descriptor, then 13 final bytes. The old
image fails at cycle 8 (`DESCRIPTOR_BEFORE_LAST_R`); the new image writes all 4140
bytes once, with the final three inactive bytes disabled. Descriptors enter the
real VLDU through public inputs; no force/deposit or replacement datapath is used.

The fix is deliberately not the issue's literal RREADY-only proposal. Local
indexed masked elements create LEN=0 `is_skip` descriptors and no AXI R response.
The existing byte-consumption condition handles both real R data and internal
skip bytes; only after that event can a last-index descriptor retire. LEN=0 and
LEN=255 both work without overflow-sensitive arithmetic. Mask ownership and the
result/commit queue logic are unchanged.

## VCS Evidence

All directories below are under `verification/out/ara-upstream-20261009-agent-`.
Each holds a complete source snapshot, `pins.json`, commands, compiler/runtime
logs, image, process PID, exit status, and terminal receipt. Full hashes and
offline checks are in `evidence-final.json`. Runtime shared-object hashes for
these completed runs are captured at audit time; the executable itself was
pinned before execution. The final replay helper also pins shared objects before
and after execution.

| Suffix | Result / actual scope |
|---|---|
| `vldu-old-02` | Expected old failure, first beat partial from vstart=31 |
| `vldu-old-split-01` | Expected old failure, natural page crossing, same final fixture as new-03 |
| `vldu-new-03` | 18 cases, 39,558 enabled bytes, 2,624 R handshakes, 124 descriptor handshakes, 53 skip descriptors |
| `vldu-small-old-01`, `vldu-small-new-01` | Both 97 cases, 24,615 bytes; identical case/count records and simulation time 52,690,000 ps |
| `mul-old-01`, `mul-new-01` | Both 24 configurations; independent arithmetic oracle and cycle equivalence pass |
| `guard-old-128x4-01` | Original assertion block accepts illegal stride zero |
| `guard-new-128x4-01` | Expected VCS elaboration error, exactly the new guard |
| `guard-new-256x4-01` | Legal boundary accepted, register stride one |

VLDU long tests use VLEN=8192, 4 lanes, 128-bit AXI, EW8. They cover LEN
0/1/254/255, alignment offsets, vstart, first/last partial beats, page splits,
mask supply bubbles, R bubbles, independent lane grants, delayed final grants,
mixed indexed active/skip traffic, 40 consecutive all-masked no-R skips, and two
simultaneously queued instruction owners. Checks include every enabled byte,
disabled prestart/tail/mask byte enable, duplicate/missing writes, destination
address and owner, mask owner/first element, last-R/descriptor correspondence,
6,474 stalled-result stability samples, exactly one done per owner, and final idle.
The current VLEN=1024 configuration is tested separately with LEN 0..31 and 63.
This is a VLDU module test, not an end-to-end test of addrgen's descriptor generation.

SIMD uses the **unchanged** `verification/timing/simd_mul_equivalence_tb.sv` and
an archived original module renamed mechanically as the reference. It covers
SEW 8/16/32/64, pipeline depths 0/1/2, fixed-point enabled/disabled, all four VXRM
modes, min*min saturation, edge products, other multiply/MAC operations, random
backpressure, reset, result/mask/saturation, and queue drain. Original numerical
behavior already passes; 24 original configurations additionally show `r=xx`
outside VSMUL. New non-VSMUL `r=0` assertions pass. This is a combinational-default
repair, **not** a claim of a newly demonstrated numerical failure. Local prefix
arithmetic, retiming, EW16 shift=15, and live-output VXRM semantics are preserved.
Upstream provenance: [commit e561b79](https://github.com/pulp-platform/ara/commit/e561b79).

Guard rationale follows [open PR #484](https://github.com/pulp-platform/ara/pull/484),
which is not claimed as merged. `vaddr()` divides a register's bytes by lanes and
then by eight. Below one ELEN-bit word per lane, that stride is zero. These tests
compile the **actual assertion text extracted from ara.sv**, together with the
actual package address function. They are **not full Ara parameter elaboration
or a complete legal-configuration build**. Parent integrated smoke remains separate.

The original VCS `$fatal` runs return process exit 0 on this host. They remain
FAIL because the receipt requires an exact terminal marker and rejects Fatal/Error
diagnostics. No failed receipt is relabelled PASS. Initial compile plumbing
failure (`vldu-old-01`) and the first fixture's incorrect EW8 inverse-layout
assumption (`vldu-new-01`) remain preserved and are excluded from acceptance.
The corrected independent inverse uses lane interleave plus three-bit reversal,
not the DUT shuffle function. No extra RTL changes were made to accommodate it.

## Replay

Run from the integration worktree, always with a fresh output directory:

```sh
python3 verification/ara_upstream_20261009/run_units.py --suite vldu --output /ABS/NEW
python3 verification/ara_upstream_20261009/run_units.py --suite vldu --small-only --output /ABS/NEW_SMALL
python3 verification/ara_upstream_20261009/run_units.py --suite vldu --baseline --split-focused --baseline-archive /ABS/ORIGINAL.tgz --output /ABS/NEW_OLDFAIL
python3 verification/ara_upstream_20261009/run_units.py --suite mul --reference-simd-mul /ABS/ORIGINAL_simd_mul.sv --output /ABS/NEW_MUL
python3 verification/ara_upstream_20261009/run_units.py --suite guard --vlen 256 --lanes 4 --output /ABS/NEW_GUARD
python3 -m unittest discover -s verification/ara_upstream_20261009 -p 'test_*.py' -v
python3 verification/ara_upstream_20261009/audit_evidence.py
```

Candidate VLDU/guard replay works without the default /tmp archive. Explicit
missing archives fail closed; baseline runs require it. SIMD equivalence requires
an archive or an explicit reference and never silently substitutes the candidate.
The helper bounds compile at 180 s and simulation at 120 s; these are short module
runs, not long-running background campaigns. Twelve no-EDA unit tests cover
archive/reference routing, missing provenance, compile failures, false success
markers, exit-code failures, and image mutation.

## Deferred Risks (No Edits)

- `segment_sequencer.sv:280` WAIT_END does not independently latch a late exception
  as open PR #490 proposes. Local exception capture at :262 and main-sequencer
  serialized memory completion/drain differ from that proposal. A reachable lost
  exception is not established by this work; copying the upstream state transition
  could bypass local draining. Requires its own measured exception-order hypothesis.
- Main-sequencer load/slide dependency blocking remains conservative. Draft PR #203
  changes a broader dependency protocol and is not needed by these three fixes.
  No performance improvement or coverage claim is made for that deferred work.

No full synthesis or new integrated acceptance campaign was launched by this sidecar.
