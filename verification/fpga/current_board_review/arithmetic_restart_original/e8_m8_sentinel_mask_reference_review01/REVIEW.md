# Exact Reference Entry Review

Decision: **NO_BLOCKER_EXACT_REFERENCE_ENTRY_ONLY**. The parent must still
provide the separate explicit execution authorization required by reference02.py.
This review does not launch or authorize Spike/DUT and does not accept a new
reference result. No reference currently exists for this successor.

## Exact Binding

Producer: `../full_e8_m8_sentinel_mask_reference_entry01/`.

- ENTRY.json SHA256:
  `6e1591fafa4a90c637a1db9f71c34f090f7b52090c8a2436351d826c8c1ba832`.
- Host02 actual execution receipt SHA256:
  `c66ead7cba6ba19768ef6e36ce7572aa6beda8d775dd8815075b625a7d0f39e5`.
- Spike ELF SHA256:
  `b1cd154e319211187f8e6e34f7e8f40398ebdc65f035e033ed7b8f8141d15c0c`.
- Consumer: reference02.py -> reference_check02.py -> lifecycle02.py,
  context.py, gates.py and PROFILE.json; inherited original e8 model and
  memory decoder are included in the pinned dependency set.

All254 ENTRY pins independently match, including the actual Spike executable,
source/model/helper provenance, new ELF/profile/checker and previous artifact
review. Profile/Host01/Host02 preflight and postflight maps are unchanged.
No Host, compiler, CFG, reference, raw parser or DUT was rerun by this review.

## Host Evidence And Successor Delta

Host01 is retained:18 tests,2 failures,0 errors, actual wait1/2.272416631s.
One failure was a test assumption that the tail SH is last. The actual profile
places that2B store at zero-based position100. Host02 uses the actual profile
position and does not change output layout or the129-store completion gate.

The other failure exposed a real observer gap: a business-store PC could escape
its bank and avoid the bank-specific checks. lifecycle02 checks both address
and address+width against the exact bank bound before dispatching. Bounds are
out1026, mask128, a1024, b1024; no e16-size input shadow is allowed.

Host02 is retained:18 tests,0 failures/errors, actual wait0/2.421909723s,
timeoutfalse/retries0. The executed command consumes test_entry02/lifecycle02.
Cases cover initialization deletion/duplicate/reorder/offset1026/value errors,
tail width/value, mask phase/drop/reorder, seed sequence/value, unknown source
GPRs, exact ABI-save exception, missing/late BSS, failure PCs, marker+FAIL,
incomplete scope, purepark violations, capacity state/order/code and comparator
branch/drop gates. These are short constructed fixtures, not a complete fake
reference, fullstream Host run or proof of DUT behavior. Host01 is not relabeled.

## Source And Observer Coverage

Full original4095 order, CAP1024/SEW8/m8/vtype3/physical8,4193280 result bytes,
8190 guards and4095 returned-vstart checks remain. Original model generates
expected data independently of observed output. Each call requires the original
seven arguments, source a/b values, all1026 fresh output bytes and full128B mask.
No call/prefix/history reduction is introduced.

Independent inspection of PROFILE confirms129 initializer events covering
128x8B plus2B, exact byte5b values and actual linked PC/codes. Each of three
mask profiles contains16 full8B stores; their values independently match all
1024 selected bits, including the high64B. Seed profiles retain2944 scalar
stores per seed,8832 total. Lifecycle requires the exact ordered initializer,
mask epochs and seed sequence before each helper; deleted/duplicate writes do
not satisfy the gate merely by producing the same final bytes.

Unknown source GPRs are not defaulted to zero. Only the12 actual main prologue
callee-save store PCs may save unknown entry values, with the actual decoded
register class,8B SP-relative store and304B frame restriction. Business stores
still require known source/base GPRs and width-truncated actual data. One shared
shadow contains actual initialization and observed vector-output state; scalar
reads are checked against that shadow or pinned ELF ROM. This ABI exception
does not exempt normal input/mask/output values or comparator branch operands.

All25 helper ranges are recognized, including interior PCs. Original13-step
order/code and all4095 counts are required, with physical vector inputs/old vd,
predicate, target CSR, complete target/store outputs and returned vstart0.
The comparator gate additionally enforces its exact nextPC/branches/ordinal/
zero-return, all528255 actual reads,69615 IDs,109575 gold reads and zero other
comparator loads. Final per-PC counts must match the actual linked success CFG,
including209340 constant-materialization instructions. Tail remains LHU2B at
out+1024, covering last result byte and rear guard; no padded dictionary bytes
substitute for actual output.

## Capacity, EOF And Cost

Capacity requires exactly once, in consecutive firmware retirements:
`0x800018f2:0x52fd`, `0x800018f4:0x0032f557`,
`0x800018f8:0x8082`. Actual t0=-1, a0/VL1024, vtype3 and known/reset vstart
are checked. Dropped, reordered, duplicated or wrong-state capacity sequences
are rejected by the short gates.

Every firmware row must match a decoded ELF PC/code. Boot-ROM rows below the
firmware address are separately counted, not treated as firmware; this entry
is not an independent boot-ROM ISA oracle. Target register/memory effects and
scalar loads/stores are checked as above, not by claiming a full scalar ISA
emulator. Post-HTIF rows must be exact `0x8000007e:0xa001` without memory,
GPR/vector or CSR effects; at least one purepark row and full EOF are required.
No early stop at the PASS marker is permitted.

Original return a0=0 at replay_exit, actual HTIF store1, complete helper/oracle
counts and the exact fullsource console marker are all necessary. Marker plus
FAIL/TRAP/ERROR/UNSUPPORTED is rejected. firmware_to_HTIF is the actual parsed
firmware retirement count through that store, not CFG prediction, debug counter,
boot count or post-exit parking. Its numeric gate rejects bool/noninteger/zero
and values above3000000 cause HOLD rather than READY.

## Execution Gate And Authorization Fields

The fixed future attempt is rs4000000;quit,120s wall,768MiB RLIMIT_FSIZE and
one600s closed audit. Fresh reference01 directory creation prevents repeat use.
Actual child wait status is fsynced before validation; errors preserve numeric
receipts and first observer context without retry. Closed raw is hash/stat-bound
before and after its one semantic traversal. Entry/input/review/parent pins are
checked before launch and after audit. No actual firmware result exists yet.

Parent must author a new authorization JSON with exactly these required values:

```json
{
  "status": "APPROVED_ONCE_REFERENCE_AND_AUDIT_ONLY",
  "entry_sha256": "6e1591fafa4a90c637a1db9f71c34f090f7b52090c8a2436351d826c8c1ba832",
  "review_sha256": "SHA256 of this review directory's review.json",
  "max_attempts": 1,
  "DUT_authorized": false,
  "reference_timeout_s": 120,
  "hard_steps": 4000000,
  "max_raw_bytes": 805306368,
  "audit_timeout_s": 600,
  "firmware_gate": 3000000
}
```

Executor takes the actual review JSON/path/hash and actual parent JSON/path/hash
via --review/--review-sha/--parent-authorization/--parent-sha. This template and
the independent review cannot substitute for that future parent-authored record.
No reference or DUT was launched, and no old/sealed consumer was modified.
