# FP32 Exact Reference Entry Review

Decision: **NO_BLOCKER_REFERENCE_ENTRY**, for reference_entry02 only.
This is preparation admission, NOT reference PASS, DUT permission, or Linux
closure. Parent must separately authorize the exact entry/review before one
reference execution. Entry01 remains sealed and was not granted final admission.

## Exact Binding

- ENTRY: `b8df036ab44fb1819fac00a7153e5cfa6e0809eaf29e8d33bcfea110b2d38ac1`.
- Input pins: `a7f6fdf6d8899ec5b2581866b8edf950394d4bc3b63b8dc7634a3bb407c621f1`.
- Checker: `5d54f5427a28768b71bfdd7e141dc0510e0c5c4fed699bf0ad200af888c35318`.
- Actual Spike ELF: `9b6f3e8fa391514816fc6731aeb8b9628d374fbe5f0e1ccb85fb6a2e929e1254`.
- Original Linux parent: `rvv_fp_compare_unboxed_unmasked_e32_mf2`, ELF
  `1bc4201a51302e1c9f2f0f8f517cc053de49ba38ee2aa21574bf5f15fd68ca38`.
- Original C: `03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad`.

All198 current file pins rehashed equal, all182 predecessor pins retained.
Input before/after maps agree. Spec, executor and audit wrapper are byte-equal
to entry01. Earlier independent entry inspection checked all736 spec PC/code
entries against actual ELF loadable bytes with zero mismatches. Tesla's pinned
artifact review `6162b716...` supplies original185-instruction/696-byte helper
identity and conditional cost evidence; no compiler/CFG or numerical test rerun.

## FP32 Scope and Actual Checker

Full17920 calls,286720 result bits,35840 guards,17920 flags and vstarts.
Capacity is exactly three instructions, CAP16, e32/mf2 vtype23, physical1.
Actual capacity vset encoding is0172f557. The original ten helpers are four
17-instruction and six19-instruction functions:182 static operation instructions
plus capacity3,326144 dynamic operation instructions plus capacity3.

Each input has4096B backing and exactly64B freshly written each call; remaining
4032B must remain zero. The cache does not change this test. Each call still
checks49 stores:16 mask SD,16 interleaved input SD,16 output SD and final SH.
Input period stride64B and16 LD are FP32-specific, not FP16's32B/eight LD.
Full128B mask and130B output initialization remain; output LWU at0x8000026e
checks16 result bits and both original guards at offsets0/3. The final SH at
output+128 is an initialization obligation, not a replacement guard location.

The actual vf prefix uses LWU encoding0005e383 and FMV.D.X f2038053. Parser
tracks f0 independently of x0. It requires full64-bit committed f0 payload to
equal the zero-extended source uint32, including0x80000000 and nonzero seeds.
Wrong upper32, NaN-boxing, erased payload, x0 substitution and old LHU are
covered by stored short negatives. This does not claim physical FPR readback.

Original FP32 fixtures retain qNaN0x7fc12345 and sNaN0x7f812345. Source-row
logic uses the original table, vf malformed scalar's qNaN column14, and active
elements only for flag accumulation. EQ/NE quiet-NaN versus signaling-NaN and
ordered comparison flags remain table-derived. Sticky0/1 is exact. UNMASKED1
means active i<VL even for maskmode3; VL0 preserves old bits and sticky alone.
Nonzero-VL tail allowed sets remain {old,1,wanted}, not one selected tail value.

## Cache and Short Evidence

Only setup_store is overridden. The pure expected_setup builder is inherited;
one tuple of49 integer triples is cached per Checker/current ordinal, with
no actual memory/event/counter in its construction. Ordinal change replaces
the cache. Every original phase/PC/index/address/value/width check and counter
increment remains. Gold/spec are immutable inputs by contract; no production
method mutates them. Mid-call mutation of those inputs is unsupported, not
silently accepted as a new scenario. No cross-instance cache exists.

Stored36 tests include all31 predecessor checks against the successor and5
cache differentials. Actual child wait0, no timeout,6.632769118994474s;
test-body log5.120s. Profile: six calls, old294/new6 constructions,294 actual
events each. Negatives cover missing/duplicate equal data, wrongPC/address/
width/high32, missing final SH, oracle-driven ordinal transition and isolation.
No full-audit wall-time speedup is claimed. No tests were rerun by this review.

## Execution Gate and Limits

Executor requires this review's exact SHA, status and ENTRY/pins binding,
plus separately hashed parent JSON. It pins all inputs before reference,
before audit and at completion; saves actual child wait receipts before
validating; uses exclusive reference01/audit01 outputs; preserves failures
without retry. No DUT command is present.

ISA `rv64gcv_zfh_zvfh_zvl1024b`; `rs 4000000; quit`; reference120s/raw768MiB,
audit600s, actual firmware through HTIF<=3000000. HTIF store at0x8000007a
must be64-bit value1 at actual symbol tohost, after complete original oracle
and exact console. All remaining rows through EOF must be side-effect-free
0x8000007e/a001 park. Exact ELF/control flow and contiguous helper checks
remain inherited, including unexpected RVV rejection.89600 memory-instruction
occurrences/15360 nonempty targets are reference qualifications, not DUT owners.

Conditional cost upper2957810 leaves42190 below3M; it is not measured firmware
or a timing guarantee. Budget failure must remain NOT_ACCEPTED, not trigger
automatic expansion. Numerical Host/compiler/CFG and raw traces were not rerun.

Parent authorization schema (parent must create/sign; this is NOT approval):
`status=AUTHORIZE_SOLE_FP32_FULL17920_REFERENCE`, exact `entry_sha256` above,
`review_sha256` of sibling REVIEW.json, integer `reference_attempts=1`.
Pass both authorization path and SHA plus this review path/SHA to the pinned
reference_entry02/execute_once.py. No reference execution by this reviewer.
