# Full17920 Finite Reference Entry

Status: **prepared,22 short checker tests passed; independent ENTRY review pending**.
No reference or DUT was executed while preparing this entry. Source/model,
compile01/run01 Host failure and all old artifacts remain unchanged. Parent
conditionally authorized one reference and one closed audit only after Aquinas's
exact entry NO_BLOCKER. No VCS follows automatically.

## Actual Inputs

Spike ELF is the sole fixed-flags compiled artifact:
`../compile01/run02/spike/program.elf`, SHA
`0ecbd714c95e1aed2b1a6586cebdd7953e090d2da6d8c6521ee1101c2aec9671`.
This entry does not relink it. `spec.json` is derived from its actual disassembly,
symbol table and ELF bytes; all code bytes match PT_LOAD bytes. Original helper
identity, tables and successful static cost were independently reviewed in
`fp_compare_unboxed_full17920_source_review01/COMPILED_REVIEW01.json`,
SHA `12b54242c48aa088ae3211ff902b125dcb49a99604ab4b64775bdc7377ddd753`.

The full source model is the existing original17920 candidate, not the265 prefix
and not alias-m8. All reviewed source/table/ELF/compiler outputs and direct
checker imports are bound by `input_pins.json`, including the external compressed
scalar decoder `verification/coverage/scoped_rv64c_memory.py`. No old checker is
edited or imported with a substituted global shape.

## Strict Scope

- Full17920 contiguous original call order:286720 result bits,35840 guards,
  17920 flags/vstarts;10 actual helpers,185 static encodings and326144 dynamic
  op-helper instructions plus the one3-instruction capacity window.
- Original fixed DK0 old bits`0x5b5b`, CAP16/e16/mf4/vtype14. Each result bit
  retains its exact original allowed set; legal agnostic tails are not forced to
  one golden payload. Original b[0] is delivered through LHU/FM V.D.X unchanged
  (actual mnemonic `fmv.d.x`); seeds0/16 are zero, other30 nonzero. All32 raw f0
  seed contexts must occur336 times each, including invalid NaN boxing.
- Every call:41 stores in actual PC/address/value/width order,8 actual input LD
  interleaved with its input SD,1 complete aligned output LWU. The checker requires
  exactly2240 oracle record LD events at original seed/op/length boundaries.
  No record or source freshness is manufactured from the final console marker.
- Full a/b/mask/output initial bytes, upper backing BSS, actual source vectors,
  mask and old destination; full two-byte vector result store and scalar oracle.
  Returned flags/vstart, packed status, saved fflags operand, caller s6 record
  preservation and actual record/sticky OR are checked.
- Every raw retirement must match actual ELF PC/code and actual branch/call/return
  flow; helpers/capacity are contiguous exact windows. All scalar memory accesses
  use actual effective addresses, widths, operands and initialized memory values.
  Unknown initial ABI spill values are allowed ONLY at exact initial s-register
  prologue SD PCs, recorded from raw stores, never assumed zero. Their restores
  are checked against the memory shadow. Business stores have no such exemption.
- Startup BSS is the exact ordered zero SD loop at`80000046`, including its full
  end boundary before main. Runtime console is ordered scalar SB, not arbitrary
  wide writes. Original DETAIL/failure markers veto immediately. The final exact
  full17920 console and actual HTIF success1 are both mandatory.
- Reset ROM prefix and side effects are exact. After HTIF, only the actual
  side-effect-free`8000007e:a001` park is permitted through EOF. Partial EOF cannot
  pass, and total raw rows may not exceed4M. Firmware to HTIF must be<=3M.

The parser recognizes horizontal spacing in x/f/v fields and the actual
`e16 mf4 lN` context prefix. It rejects unknown tokens rather than silently
dropping side effects. Only two first-match records from the old265 raw were
read to confirm vector memory-log syntax; no old semantic trace was reparsed.

## Short Checks

`host.log` contains22 passing synthetic unit tests, actual child wait0 in
`host.wait.json`. The prepare process itself also returned0 (tool session94424,
terminal chunk eae469). Tests cover valid setup/oracles across seeds/shapes,
VL0/active/tail/guards/flags/vstart errors, missing SH/inputLD/record group,
wrong input/record address, all32 raw scalar seeds, boxed/zero substitutions,
saved flags restore, wrong PC, partial EOF, nonpark post-exit and actual spaced
parser fields. These tests call checker components with short synthetic state;
they are not a simulated full firmware/reference run or hardware evidence.

## Fixed Execution Contract

`execute_once.py --review ACTUAL_REVIEW_JSON --review-sha256 ACTUAL_SHA` requires
the independent review to contain:

```json
{
  "status": "NO_BLOCKER_REFERENCE_ENTRY",
  "entry_sha256": "dc26b72f739b9170694379ccfc9bd525d309ed079faa5dd794380a600d65581a",
  "input_pins_sha256": "bc886117fb5959698301851fb5ab1bd8c8a799f28c071c8479e8f44727447710"
}
```

The actual independent file may include further review evidence. No fabricated
review or parent text is used in its place. The executor first fresh-checks all
pins, then creates exclusive `reference01/`; an existing directory prevents retry.
Debug commands are exactly `rs 4000000` then `quit`, no extra vector execution.
ISA`rv64gcv_zfh_zvfh_zvl1024b`, memory2MiB; child timeout120s and file ceiling768MiB.
Actual child numeric wait is persisted before any postcheck. Only actual rc0,
no timeout and a closed bounded raw file permit the sole `audit_once.py` child.
That child has600s, persists result/failure, and its actual parent wait is saved.
Pre/post raw hashes and all inputs must remain identical. Any failure stops without
reference retry, repeated semantic parse, increased bounds or automatic DUT.

## Entry Hashes

- ENTRY.json: `dc26b72f739b9170694379ccfc9bd525d309ed079faa5dd794380a600d65581a`
- input_pins.json: `bc886117fb5959698301851fb5ab1bd8c8a799f28c071c8479e8f44727447710`
- checker.py: `1533ae8fc44b0619bea67dde7427ef128630076155e5b1f9e1404084889e832e`
- spec.json: `c44ab425561d856f83f013bbf5bb489ca6ad9f73383b6480f934dcfe02a922b6`

README is explanatory and outside the executable pin set; frozen entry/scripts
must not change while independent review/execution uses these identities.
